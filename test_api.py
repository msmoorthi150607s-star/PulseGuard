#!/usr/bin/env python3
"""
PulseGuard API Test Script

Run this script to test all API endpoints:
- health, model-info, predictions (normal/warning/critical)
- invalid input handling
- auth enforcement (401 without token, 403 wrong role)
- new endpoints: machines, service-requests, maintenance-reports,
  exports (raw/clean), reports (admin/technical), downloads
"""

import sys
import os
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'flask_api'))
os.environ.setdefault('FLASK_DEBUG', '0')

from app import app, firebase_service  # noqa: E402


class PulseGuardAPITests(unittest.TestCase):
    """End-to-end API test suite."""

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    # --------------------------------------------------------
    # Public endpoints
    # --------------------------------------------------------
    def test_01_health(self):
        r = self.client.get('/api/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'healthy')

    def test_02_model_info(self):
        r = self.client.get('/api/model-info')
        self.assertEqual(r.status_code, 200)
        self.assertIn('method', r.get_json())

    def test_03_latest_reading(self):
        r = self.client.get('/api/latest')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('temperature', data)
        self.assertIn('prediction', data)

    def test_04_history(self):
        r = self.client.get('/api/history?limit=5')
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(r.get_json()['count'], 5)

    def test_05_root(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('endpoints', r.get_json())

    # --------------------------------------------------------
    # Predictions
    # --------------------------------------------------------
    def test_06_predict_normal(self):
        r = self.client.post('/api/predict',
                             json={'temperature': 34.0, 'vibration': 0.2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['prediction'], 'normal')

    def test_07_predict_warning(self):
        r = self.client.post('/api/predict',
                             json={'temperature': 39.0, 'vibration': 3.0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['prediction'], 'warning')

    def test_08_predict_critical(self):
        r = self.client.post('/api/predict',
                             json={'temperature': 45.0, 'vibration': 8.0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['prediction'], 'critical')

    def test_09_predict_invalid_type(self):
        r = self.client.post('/api/predict',
                             json={'temperature': 'hot', 'vibration': 0.2})
        self.assertEqual(r.status_code, 400)

    def test_10_predict_missing_field(self):
        r = self.client.post('/api/predict', json={'temperature': 34.0})
        self.assertEqual(r.status_code, 400)

    def test_11_predict_out_of_range(self):
        r = self.client.post('/api/predict',
                             json={'temperature': 150, 'vibration': 0.2})
        self.assertEqual(r.status_code, 400)

    def test_12_prediction_is_output_only(self):
        """Prediction records must use the minimal output-only schema."""
        r = self.client.post('/api/predict',
                             json={'temperature': 34.0, 'vibration': 0.2})
        data = r.get_json()
        self.assertTrue(data.get('firebase_saved'))
        preds = firebase_service.get_predictions(limit=1)
        self.assertTrue(preds)
        record = preds[0]
        for field in ('prediction_id', 'record_id', 'prediction', 'timestamp'):
            self.assertIn(field, record)

    # --------------------------------------------------------
    # Auth enforcement
    # --------------------------------------------------------
    def test_13_machines_require_auth(self):
        r = self.client.get('/api/machines')
        self.assertEqual(r.status_code, 401)

    def test_14_machine_registration_requires_technical(self):
        # No token at all -> 401
        r = self.client.post('/api/machines', json={})
        self.assertEqual(r.status_code, 401)

    def test_15_service_request_requires_admin(self):
        r = self.client.post('/api/service-requests', json={})
        self.assertEqual(r.status_code, 401)

    def test_16_export_requires_technical(self):
        r = self.client.get('/api/export/raw')
        self.assertEqual(r.status_code, 401)

    def test_17_reports_require_auth(self):
        r = self.client.get('/api/reports/admin')
        self.assertEqual(r.status_code, 401)

    def test_18_invalid_token_rejected(self):
        r = self.client.get(
            '/api/machines',
            headers={'Authorization': 'Bearer invalid-token-xyz'}
        )
        self.assertEqual(r.status_code, 401)

    # --------------------------------------------------------
    # Role-based flows with mocked verified users
    # --------------------------------------------------------
    def _auth_as(self, role):
        """
        Simulate a logged-in user of the given role:
        patches token verification and returns the header to send.
        """
        p1 = patch(
            'app._token_uid_role',
            return_value={'uid': f'test-uid-{role}', 'email': f'{role}@test.com'}
        )
        p2 = patch(
            'app.firebase_service.get_user',
            return_value={'name': f'Test {role.title()}',
                          'email': f'{role}@test.com', 'role': role}
        )
        headers = {'Authorization': 'Bearer mock-token-for-tests'}
        return p1, p2, headers

    def test_19_technical_can_register_machine(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post('/api/machines', headers=h, json={
                'machine_id': 'TEST-001',
                'machine_name': 'Test Motor',
                'machine_type': 'Rotating Motor',
                'location': 'Test Section',
                'device_id': 'ESP32_TEST'
            })
        self.assertEqual(r.status_code, 201, r.get_json())
        body = r.get_json()
        self.assertEqual(body['machine']['machine_id'], 'TEST-001')
        self.assertTrue(body['machine'].get('created_at'))
        self.assertTrue(body['machine'].get('created_by'))

    def test_20_admin_cannot_register_machine(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            r = self.client.post('/api/machines', headers=h, json={
                'machine_id': 'TEST-DENY', 'machine_name': 'x'
            })
        self.assertEqual(r.status_code, 403)

    def test_21_machine_registration_rejects_missing_fields(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post('/api/machines', headers=h,
                                 json={'machine_name': 'no id'})
        self.assertEqual(r.status_code, 400)

    def test_22_admin_creates_service_request(self):
        # Ensure the test machine exists
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            self.client.post('/api/machines', headers=h, json={
                'machine_id': 'TEST-001', 'machine_name': 'Test Motor'})

        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            r = self.client.post('/api/service-requests', headers=h, json={
                'machine_id': 'TEST-001',
                'issue': 'Strange noise from bearing'
            })
        self.assertEqual(r.status_code, 201, r.get_json())
        data = r.get_json()
        self.assertEqual(data['request']['status'], 'REQUESTED')
        type(self).request_id = data['request_id']

    def test_23_technical_cannot_create_service_request(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post('/api/service-requests', headers=h, json={
                'machine_id': 'TEST-001'})
        self.assertEqual(r.status_code, 403)

    def test_24_technical_accepts_service_request(self):
        request_id = getattr(type(self), 'request_id', None)
        if not request_id:
            self.skipTest('No request created')
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            with patch('app.email_service.send_service_accepted',
                       return_value={'success': True}):
                r = self.client.post(
                    f'/api/service-requests/{request_id}/accept', headers=h)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()['request']['status'], 'ACCEPTED')

    def test_25_double_accept_rejected(self):
        request_id = getattr(type(self), 'request_id', None)
        if not request_id:
            self.skipTest('No request created')
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post(f'/api/service-requests/{request_id}/accept',
                                 headers=h)
        self.assertEqual(r.status_code, 409)

    def test_26_technical_updates_status(self):
        request_id = getattr(type(self), 'request_id', None)
        if not request_id:
            self.skipTest('No request created')
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post(
                f'/api/service-requests/{request_id}/status', headers=h,
                json={'status': 'VISITED'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['request']['status'], 'VISITED')

    def test_27_invalid_status_rejected(self):
        request_id = getattr(type(self), 'request_id', None)
        if not request_id:
            self.skipTest('No request created')
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post(
                f'/api/service-requests/{request_id}/status', headers=h,
                json={'status': 'TELEPORTED'})
        self.assertEqual(r.status_code, 400)

    def test_28_technical_creates_maintenance_report(self):
        request_id = getattr(type(self), 'request_id', None)
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post('/api/maintenance-reports', headers=h, json={
                'request_id': request_id,
                'machine_id': 'TEST-001',
                'problem_found': 'Worn bearing',
                'action_taken': 'Bearing replaced',
                'parts_replaced': '6205 x1',
                'technician_notes': 'Monitor weekly'
            })
        self.assertEqual(r.status_code, 201, r.get_json())

        # Service request should now be COMPLETED
        if request_id:
            req = firebase_service.get_service_request(request_id)
            self.assertEqual(req['status'], 'COMPLETED')

    def test_29_maintenance_report_requires_fields(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.post('/api/maintenance-reports', headers=h,
                                 json={'machine_id': 'TEST-001'})
        self.assertEqual(r.status_code, 400)

    # --------------------------------------------------------
    # Data pipeline
    # --------------------------------------------------------
    def test_30_clean_pipeline_runs(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.get('/api/export/clean', headers=h)
        self.assertEqual(r.status_code, 200, r.get_json())
        data = r.get_json()
        self.assertIn('cleaning_report', data)
        report = data['cleaning_report']
        self.assertEqual(report['interpolated_values'], 0)
        self.assertGreaterEqual(report['output_rows'], 0)

    def test_31_admin_report_pdf_and_excel(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            r = self.client.get('/api/reports/admin', headers=h)
        self.assertEqual(r.status_code, 200, r.get_json())
        reports = r.get_json()['reports']
        self.assertTrue(reports.get('pdf', {}).get('success'))
        self.assertTrue(reports.get('excel', {}).get('success'))

    def test_32_technical_report_pdf_and_excel(self):
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.get('/api/reports/technical', headers=h)
        self.assertEqual(r.status_code, 200, r.get_json())
        reports = r.get_json()['reports']
        self.assertTrue(reports.get('pdf', {}).get('success'))
        self.assertTrue(reports.get('excel', {}).get('success'))

    def test_33_download_blocks_path_traversal(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            r = self.client.get('/api/download?file=..%2F..%2Fflask_api%2F.env',
                                headers=h)
            self.assertEqual(r.status_code, 400)
            r = self.client.get('/api/download?file=app.py', headers=h)
            self.assertIn(r.status_code, (400, 404))

    def test_34_404_handler(self):
        r = self.client.get('/api/nonexistent')
        self.assertEqual(r.status_code, 404)

    # --------------------------------------------------------
    # Login endpoint (config validation)
    # --------------------------------------------------------
    def test_35_login_without_api_key(self):
        import app as app_module
        with patch.object(app_module.os, 'getenv', return_value=''):
            r = self.client.post('/api/auth/login', json={
                'email': 'x@y.com', 'password': 'z'})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json().get('error'), 'not_configured')

    # --------------------------------------------------------
    # Email settings (Admin 'Set Up Your Mails')
    # --------------------------------------------------------
    def test_36_email_settings_admin_only(self):
        # No token -> 401
        self.assertEqual(
            self.client.get('/api/settings/email').status_code, 401)
        # Technical role -> 403
        p1, p2, h = self._auth_as('technical')
        with p1, p2:
            r = self.client.get('/api/settings/email', headers=h)
        self.assertEqual(r.status_code, 403)

    def test_37_email_settings_get_masks_password(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            with patch('app.firebase_service.get_email_settings',
                       return_value={'username': 'a@b.com',
                                     'password': 'secret-app-pass'}):
                r = self.client.get('/api/settings/email', headers=h)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertNotIn('password', data)  # never returned
        self.assertTrue(data['password_set'])

    def test_38_email_settings_save_and_validate(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            with patch('app.firebase_service.get_email_settings',
                       return_value={}), \
                 patch('app.firebase_service.save_email_settings',
                       return_value=True) as save_mock, \
                 patch('app.email_service.apply_overrides') as apply_mock:
                # Valid save
                r = self.client.post('/api/settings/email', headers=h, json={
                    'username': 'alerts@gmail.com',
                    'password': 'app-password-16',
                    'recipient': 'owner@gmail.com'})
                self.assertEqual(r.status_code, 200)
                stored = save_mock.call_args[0][0]
                self.assertEqual(stored['username'], 'alerts@gmail.com')
                self.assertIn('password', stored)
                apply_mock.assert_called_once()

                # Invalid email rejected
                r = self.client.post('/api/settings/email', headers=h,
                                     json={'recipient': 'broken-email'})
                self.assertEqual(r.status_code, 400)

                # Invalid port rejected
                r = self.client.post('/api/settings/email', headers=h,
                                     json={'smtp_port': '99999'})
                self.assertEqual(r.status_code, 400)

    def test_39_email_settings_blanks_keep_stored_values(self):
        p1, p2, h = self._auth_as('admin')
        existing = {'username': 'old@gmail.com', 'password': 'keep-me'}
        with p1, p2:
            with patch('app.firebase_service.get_email_settings',
                       return_value=existing), \
                 patch('app.firebase_service.save_email_settings',
                       return_value=True) as save_mock:
                # Save only a new recipient - username/password must survive
                r = self.client.post('/api/settings/email', headers=h,
                                     json={'recipient': 'new@gmail.com'})
        self.assertEqual(r.status_code, 200)
        stored = save_mock.call_args[0][0]
        self.assertEqual(stored['username'], 'old@gmail.com')
        self.assertEqual(stored['password'], 'keep-me')
        self.assertEqual(stored['recipient'], 'new@gmail.com')

    def test_40_email_test_endpoint(self):
        p1, p2, h = self._auth_as('admin')
        with p1, p2:
            with patch('app.email_service.test_connection',
                       return_value={'success': True, 'message': 'ok'}):
                r = self.client.post('/api/settings/email/test', headers=h,
                                     json={'send': False})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['success'])


def run_tests():
    print("=" * 60)
    print("PULSEGUARD API TEST SUITE")
    print("=" * 60)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(PulseGuardAPITests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
