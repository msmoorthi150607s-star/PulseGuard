#!/usr/bin/env python3
"""
PulseGuard Flask API

A REST API for machine health monitoring and predictive maintenance
of textile rotating machinery.

Public endpoints:
- GET  /api/health              - API health check
- GET  /api/latest              - Latest sensor reading + prediction
- GET  /api/history             - Reading history (joined with predictions)
- GET  /api/prediction          - Latest prediction
- POST /api/predict             - Prediction for given readings
- GET  /api/model-info          - ML model information
- GET  /api/polling-status      - Background live-prediction poller status
- POST /api/test-email          - Test email configuration
- POST /api/webhook             - Direct ESP32 ingestion (alternative path)

Auth (Firebase Authentication, roles: admin / technical):
- POST /api/auth/login          - Sign in, returns profile + role

Machines:
- GET  /api/machines            - List registered machines (any logged-in role)
- POST /api/machines            - Register machine        (technical only)
- PUT  /api/machines/<id>       - Edit machine            (technical only)

Data pipeline:
- GET  /api/export/raw          - Firebase -> RAW Excel   (technical only)
- GET  /api/export/clean        - RAW -> Clean Excel + report (technical only)

Service workflow (admin requests, technical progresses):
- GET  /api/service-requests    - List service requests
- POST /api/service-requests    - Create request          (admin only)
- POST /api/service-requests/<id>/accept   - Accept        (technical only)
- POST /api/service-requests/<id>/status   - Update status (technical only)

Maintenance reports:
- GET  /api/maintenance-reports - List reports
- POST /api/maintenance-reports - Create report           (technical only)

Exports / reports:
- GET  /api/reports/admin       - Admin PDF + Excel       (admin only)
- GET  /api/reports/technical   - Technical PDF + Excel   (technical only)

Environment Variables:
- FIREBASE_URL, FIREBASE_WEB_API_KEY, ADMIN_EMAILS
- FLASK_ENV, FLASK_DEBUG, SECRET_KEY, PORT, HOST
- SMTP_SERVER, SMTP_PORT, MAIL_USERNAME, MAIL_PASSWORD,
  MAIL_RECIPIENT, MAIL_TECH_RECIPIENT, ALERT_COOLDOWN_SECONDS

Author: PulseGuard Team
License: MIT
"""

import os
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from flask import (
    Flask,
    jsonify,
    request,
    send_file
)
from functools import wraps
from pathlib import Path

# Load environment variables from .env (if present)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Import services
from firebase_service import get_firebase_service, FirebaseService
from model_service import get_model_service, ModelService
from email_service import get_email_service, EmailService
from auth_service import get_auth_service, AuthService
from export_service import get_export_service, ExportService
from report_service import get_report_service, ReportService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Project root (for export/report file locations)
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create Flask app
app = Flask(__name__)

# Configuration from environment
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'pulseguard-dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# Service instances
firebase_service: FirebaseService = None
model_service: ModelService = None
email_service: EmailService = None
auth_service: AuthService = None
export_service: ExportService = None
report_service: ReportService = None

# Background polling control
_polling_thread = None
_stop_polling = threading.Event()
_last_processed_timestamp = 0
_polling_interval = int(os.getenv('POLLING_INTERVAL_SECONDS', '10'))


def initialize_services():
    """Initialize all services."""
    global firebase_service, model_service, email_service
    global auth_service, export_service, report_service

    logger.info("Initializing services...")

    firebase_service = get_firebase_service()
    model_service = get_model_service()
    email_service = get_email_service()
    auth_service = get_auth_service()
    export_service = get_export_service()
    report_service = get_report_service()

    logger.info("All services initialized")


# ============================================================
# Auth helpers
# ============================================================
def _token_uid_role(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Firebase ID token using Google's public token-info endpoint.
    Returns {uid, email} or None. Roles are read from users/{uid}.
    """
    import requests as _rq
    try:
        resp = _rq.post(
            'https://identitytoolkit.googleapis.com/v1/accounts:lookup',
            json={'idToken': id_token},
            timeout=10
        )
        data = resp.json()
        users = data.get('users')
        if resp.status_code == 200 and users:
            return {
                'uid': users[0]['localId'],
                'email': users[0].get('email', '')
            }
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
    return None


def require_auth(*roles):
    """Decorator: verify Firebase ID token; optionally restrict to roles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
            if not token:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Missing Authorization: Bearer <firebase_id_token>'
                }), 401

            info = _token_uid_role(token)
            if not info:
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Invalid or expired token'
                }), 401

            profile = firebase_service.get_user(info['uid']) or {}
            user_role = profile.get('role', 'technical')
            user = {
                'uid': info['uid'],
                'email': info['email'],
                'name': profile.get('name', ''),
                'role': user_role
            }

            if roles and user_role not in roles:
                return jsonify({
                    'error': 'forbidden',
                    'message': f'This action requires role: {", ".join(roles)}'
                }), 403

            return f(*args, user=user, **kwargs)
        return wrapper
    return decorator


# ============================================================
# Background live prediction polling
# ============================================================
def start_background_polling():
    """
    Start background thread that polls Firebase for new readings
    and automatically generates predictions.

    This enables the LIVE/automatic prediction flow:
    ESP32 -> Firebase /readings_only -> Flask polls -> model inference
          -> /prediction (OUTPUT ONLY)
    """
    global _polling_thread, _stop_polling

    logger.info(f"Starting background polling (interval: {_polling_interval}s)")

    def polling_loop():
        """Background polling loop."""
        global _last_processed_timestamp

        logger.info("Background polling thread started")

        while not _stop_polling.is_set():
            try:
                latest_reading = firebase_service.get_latest_reading()

                if latest_reading:
                    current_timestamp = latest_reading.get('timestamp', 0)

                    if current_timestamp > _last_processed_timestamp:
                        logger.info("=" * 60)
                        logger.info("NEW READING DETECTED - Running automatic prediction")
                        logger.info("=" * 60)

                        temp = latest_reading.get('temperature')
                        vib = latest_reading.get('vibration')
                        ts = latest_reading.get('timestamp')
                        record_id = latest_reading.get('record_id')

                        logger.info("Latest reading received:")
                        logger.info(f"  Record ID: {record_id}")
                        logger.info(f"  Temperature: {temp} C")
                        logger.info(f"  Vibration: {vib}")
                        logger.info(f"  Timestamp: {ts}")

                        logger.info("Running model inference...")
                        prediction_result = model_service.predict(temp, vib)

                        predicted_condition = prediction_result['prediction']
                        logger.info(f"Predicted condition: {predicted_condition.upper()}")
                        logger.info(f"Method: {prediction_result.get('method', 'unknown')}")
                        logger.info(f"Confidence: {prediction_result.get('confidence', 0):.2f}")

                        prediction_id = f"pred_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                        prediction_timestamp = int(time.time() * 1000)

                        # OUTPUT-ONLY schema (no duplicated sensor values)
                        prediction_record = {
                            'prediction_id': prediction_id,
                            'record_id': record_id,
                            'prediction': predicted_condition,
                            'timestamp': prediction_timestamp,
                        }

                        logger.info("Writing prediction to Firebase /prediction...")
                        saved = firebase_service.save_prediction(prediction_record)

                        if saved:
                            logger.info(f"Prediction saved to Firebase: {prediction_id}")
                            _last_processed_timestamp = current_timestamp
                            _update_machine_health_from_prediction(
                                latest_reading, predicted_condition
                            )
                        else:
                            logger.warning("Failed to save prediction - will retry")

                        # Email alert for critical conditions
                        if saved and predicted_condition == 'critical':
                            logger.info("CRITICAL condition - sending email alert...")
                            email_result = email_service.send_critical_alert(
                                temp, vib, 'critical'
                            )
                            if email_result.get('success'):
                                logger.info("Email alert sent successfully")
                            else:
                                logger.warning(
                                    f"Email alert not sent: {email_result.get('message')}"
                                )

                        logger.info("=" * 60)
                        logger.info("Automatic prediction complete")
                        logger.info("=" * 60)
                else:
                    logger.debug("No readings found in Firebase")

            except Exception as e:
                logger.error(f"Error in background polling: {e}")

            _stop_polling.wait(_polling_interval)

        logger.info("Background polling thread stopped")

    _polling_thread = threading.Thread(
        target=polling_loop,
        daemon=True,
        name='pulseguard-polling'
    )
    _polling_thread.start()

    logger.info("Background polling thread launched")


def _update_machine_health_from_prediction(reading: Dict, condition: str):
    """
    Reflect the latest predicted condition onto the registered machine(s).

    Matching rule (honest and simple):
    - If the reading carries a device_id, match machines by device_id.
    - Otherwise, if exactly ONE machine is registered, that machine is
      the data source (single-demo setup) and receives the update.
    - With multiple machines and no device_id, no guess is made.
    """
    try:
        machines = firebase_service.get_machines()
        if not machines:
            return

        device_id = reading.get('device_id')
        target = None
        if device_id:
            target = next(
                (m for m in machines if m.get('device_id') == device_id), None
            )
        elif len(machines) == 1:
            target = machines[0]

        if target:
            firebase_service.update_machine_health(
                target['machine_id'], condition.upper(), status='ON'
            )
            logger.info(
                f"Machine {target['machine_id']} health updated to "
                f"{condition.upper()}"
            )
    except Exception as e:
        logger.warning(f"Could not update machine health: {e}")


def stop_background_polling():
    """Stop the background polling thread."""
    global _stop_polling

    logger.info("Stopping background polling...")
    _stop_polling.set()

    if _polling_thread and _polling_thread.is_alive():
        _polling_thread.join(timeout=5)

    logger.info("Background polling stopped")


def add_cors_headers(response):
    """Add CORS headers to response."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,OPTIONS'
    return response


@app.after_request
def after_request(response):
    """Add CORS headers after each request."""
    return add_cors_headers(response)


# ============================================================
# Health & info endpoints
# ============================================================
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'PulseGuard API',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'components': {
            'firebase': firebase_service is not None,
            'model': model_service is not None and (
                model_service.model is not None or model_service.is_rule_based
            ),
            'email': email_service is not None and bool(os.getenv('MAIL_USERNAME')),
            'auth': bool(os.getenv('FIREBASE_WEB_API_KEY')),
            'excel_export': True,
            'pdf_report': report_service is not None and report_service.REPORTLAB_AVAILABLE,
        }
    })


def _attach_prediction(reading: Dict) -> Dict:
    """
    Attach a machine-condition prediction to a raw sensor reading.

    Prefers the stored prediction from Firebase /prediction (matched by
    record_id). If the reading predates automatic polling and has no
    stored prediction, runs the model on the fly for display only -
    nothing is written back to Firebase - and marks it as 'computed'.
    """
    record_id = reading.get('record_id')
    stored = _prediction_index.get(record_id)

    if stored:
        reading['prediction'] = stored.get('prediction')
        reading['prediction_source'] = 'stored'
    else:
        result = model_service.predict(
            reading.get('temperature'), reading.get('vibration')
        )
        reading['prediction'] = result.get('prediction') if result else None
        reading['prediction_source'] = 'computed'

    return reading


# Prediction index: record_id -> newest stored prediction for that record.
_prediction_index: Dict[str, Dict] = {}
_prediction_index_fetched_at = 0.0
_PREDICTION_INDEX_TTL = 5.0  # seconds


def _refresh_prediction_index(force: bool = False):
    """Rebuild the record_id -> prediction map if stale."""
    global _prediction_index, _prediction_index_fetched_at

    now = time.time()
    if not force and (now - _prediction_index_fetched_at) < _PREDICTION_INDEX_TTL:
        return

    try:
        predictions = firebase_service.get_predictions(limit=500) or []
        index: Dict[str, Dict] = {}
        for pred in predictions:  # newest-first
            rid = pred.get('record_id')
            if rid and rid not in index:
                index[rid] = pred
        _prediction_index = index
        _prediction_index_fetched_at = now
    except Exception as e:
        logger.warning(f"Could not refresh prediction index: {e}")


@app.route('/api/latest', methods=['GET'])
def get_latest_reading():
    """Get the latest sensor reading from Firebase, with its prediction."""
    try:
        reading = firebase_service.get_latest_reading()

        if not reading:
            return jsonify({
                'error': 'No readings found',
                'message': 'No sensor data available in Firebase'
            }), 404

        _refresh_prediction_index()
        reading = _attach_prediction(reading)

        return jsonify({
            'temperature': reading.get('temperature'),
            'vibration': reading.get('vibration'),
            'timestamp': reading.get('timestamp'),
            'record_id': reading.get('record_id'),
            'prediction': reading.get('prediction'),
            'prediction_source': reading.get('prediction_source'),
            'confidence': reading.get('confidence'),
            'method': reading.get('method'),
            'message': reading.get('message', ''),
            'short_message': reading.get('short_message', '')
        })

    except Exception as e:
        logger.error(f"Error fetching latest reading: {e}")
        return jsonify({
            'error': 'Failed to fetch reading',
            'message': str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    Get reading history from Firebase, joined with predictions.

    Query Parameters:
        limit (int): Maximum number of readings (default: 50, max: 500)
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(1, limit), 500)

        readings = firebase_service.get_readings(limit)

        if not readings:
            return jsonify({
                'readings': [],
                'count': 0,
                'message': 'No historical readings found'
            })

        _refresh_prediction_index()
        formatted = [_attach_prediction(r) for r in readings]

        return jsonify({
            'readings': formatted,
            'count': len(formatted),
            'limit': limit
        })

    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return jsonify({
            'error': 'Failed to fetch history',
            'message': str(e)
        }), 500


@app.route('/api/prediction', methods=['GET'])
def get_latest_prediction():
    """Get the latest prediction from Firebase."""
    try:
        prediction = firebase_service.get_latest_prediction()

        if not prediction:
            return jsonify({
                'error': 'No predictions found',
                'message': 'No prediction data available in Firebase'
            }), 404

        # Enrich with the human-readable message from the model rules
        result = model_service.predict(
            _lookup_reading_value(prediction.get('record_id'), 'temperature'),
            _lookup_reading_value(prediction.get('record_id'), 'vibration')
        )

        return jsonify({
            'prediction_id': prediction.get('prediction_id'),
            'record_id': prediction.get('record_id'),
            'prediction': prediction.get('prediction'),
            'timestamp': prediction.get('timestamp'),
            'message': result.get('message', ''),
            'short_message': result.get('short_message', '')
        })

    except Exception as e:
        logger.error(f"Error fetching latest prediction: {e}")
        return jsonify({
            'error': 'Failed to fetch prediction',
            'message': str(e)
        }), 500


def _reading_cache() -> Dict[str, Dict]:
    """Cache of recent readings keyed by record_id (5s TTL)."""
    global _reading_index, _reading_index_at
    now = time.time()
    if not hasattr(_reading_index, 'get') or (now - _reading_index_at) > 5:
        try:
            readings = firebase_service.get_readings(limit=100)
            _reading_index = {r.get('record_id'): r for r in readings}
        except Exception:
            _reading_index = {}
        _reading_index_at = now
    return _reading_index


_reading_index: Dict[str, Dict] = {}
_reading_index_at = 0.0


def _lookup_reading_value(record_id: str, field: str):
    r = _reading_cache().get(record_id)
    return r.get(field) if r else None


@app.route('/api/predict', methods=['POST'])
def make_prediction():
    """
    Make a prediction for sensor readings.

    Request Body (JSON):
        temperature (float): Temperature in Celsius (required)
        vibration (float): Vibration level (required)
        record_id (str): Optional record ID for tracking
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'error': 'Invalid request',
                'message': 'Request body must be JSON'
            }), 400

        temperature = data.get('temperature')
        vibration = data.get('vibration')

        if temperature is None or vibration is None:
            return jsonify({
                'error': 'Missing required fields',
                'message': 'temperature and vibration are required',
                'required_fields': ['temperature', 'vibration']
            }), 400

        try:
            temperature = float(temperature)
            vibration = float(vibration)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid input types',
                'message': 'temperature and vibration must be numeric'
            }), 400

        if temperature < -50 or temperature > 100:
            return jsonify({
                'error': 'Temperature out of range',
                'message': 'Temperature must be between -50 and 100 Celsius'
            }), 400

        if vibration < 0 or vibration > 100:
            return jsonify({
                'error': 'Vibration out of range',
                'message': 'Vibration must be between 0 and 100'
            }), 400

        prediction_result = model_service.predict(temperature, vibration)

        prediction_id = f"pred_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        record_id = data.get('record_id', f"manual_{prediction_id}")
        timestamp = int(time.time() * 1000)

        # Save OUTPUT-ONLY prediction record to Firebase
        prediction_record = {
            'prediction_id': prediction_id,
            'record_id': record_id,
            'prediction': prediction_result['prediction'],
            'timestamp': timestamp,
        }
        saved = firebase_service.save_prediction(prediction_record)

        # Email alert for critical conditions
        email_sent = None
        if prediction_result['prediction'] == 'critical':
            email_sent = email_service.send_critical_alert(
                temperature, vibration, 'critical'
            )

        response_data = {
            'prediction_id': prediction_id,
            'record_id': record_id,
            'prediction': prediction_result['prediction'],
            'temperature': temperature,
            'vibration': vibration,
            'timestamp': timestamp,
            'message': prediction_result.get('message', ''),
            'short_message': prediction_result.get('short_message', ''),
            'method': prediction_result.get('method', 'unknown'),
            'confidence': prediction_result.get('confidence', 0),
            'firebase_saved': saved,
            'thresholds': prediction_result.get('thresholds')
        }

        if 'probabilities' in prediction_result:
            response_data['probabilities'] = prediction_result['probabilities']

        if prediction_result['prediction'] == 'critical' and email_sent:
            response_data['email'] = {
                'sent': email_sent.get('success', False),
                'message': email_sent.get('message', '')
            }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error making prediction: {e}")
        return jsonify({
            'error': 'Prediction failed',
            'message': str(e)
        }), 500


@app.route('/api/model-info', methods=['GET'])
def get_model_info():
    """Get information about the current ML model."""
    try:
        info = model_service.get_model_info()

        if info['is_rule_based']:
            info['disclaimer'] = (
                "This model was trained on RULE-GENERATED labels "
                "(temperature/vibration thresholds). Reported accuracy is "
                "accuracy against those rule labels, NOT validated real-world "
                "predictive accuracy. Real validation requires human-labelled "
                "failure data."
            )

        return jsonify(info)

    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        return jsonify({
            'error': 'Failed to get model info',
            'message': str(e)
        }), 500


@app.route('/api/polling-status', methods=['GET'])
def get_polling_status():
    """Get background polling status."""
    return jsonify({
        'running': _polling_thread is not None and _polling_thread.is_alive(),
        'interval_seconds': _polling_interval,
        'last_processed_timestamp': _last_processed_timestamp,
        'thread_name': _polling_thread.name if _polling_thread else None
    })


@app.route('/api/test-email', methods=['POST'])
def test_email():
    """Test email configuration."""
    try:
        data = request.get_json() or {}
        test_recipient = data.get('recipient')

        if test_recipient:
            original = email_service.recipient
            email_service.recipient = test_recipient

        result = email_service.test_connection()

        if test_recipient:
            email_service.recipient = original

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error testing email: {e}")
        return jsonify({
            'error': 'Email test failed',
            'message': str(e)
        }), 500


@app.route('/api/webhook', methods=['POST'])
def webhook():
    """
    Webhook endpoint for ESP32 to send readings directly.
    (Alternative to direct Firebase writes; not used in the default flow.)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'error': 'Invalid request',
                'message': 'Request body must be JSON'
            }), 400

        temperature = data.get('temperature')
        vibration = data.get('vibration')

        if temperature is None or vibration is None:
            return jsonify({
                'error': 'Missing required fields',
                'message': 'temperature and vibration are required'
            }), 400

        prediction_result = model_service.predict(float(temperature), float(vibration))

        record_id = f"webhook_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        timestamp = int(time.time() * 1000)

        email_sent = None
        if prediction_result['prediction'] == 'critical':
            email_sent = email_service.send_critical_alert(
                float(temperature), float(vibration), 'critical'
            )

        return jsonify({
            'record_id': record_id,
            'timestamp': timestamp,
            'prediction': prediction_result['prediction'],
            'message': prediction_result.get('message', ''),
            'short_message': prediction_result.get('short_message', ''),
            'method': prediction_result.get('method', 'unknown'),
            'confidence': prediction_result.get('confidence', 0),
            'email_sent': email_sent.get('success', False) if email_sent else False
        })

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({
            'error': 'Webhook processing failed',
            'message': str(e)
        }), 500


# ============================================================
# Authentication
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """
    Sign in with email + password (Firebase Authentication).

    Request Body (JSON):
        email (str): account email
        password (str): account password

    Returns user profile with role (admin / technical) and an id_token
    that must be sent as 'Authorization: Bearer <id_token>' on protected
    endpoints.
    """
    try:
        data = request.get_json() or {}
        result = auth_service.login(
            data.get('email', ''), data.get('password', '')
        )
        status = 200 if result.get('success') else 401
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'Unexpected server error during login'
        }), 500


# ============================================================
# Machines
# ============================================================
@app.route('/api/machines', methods=['GET'])
@require_auth()
def list_machines(user):
    """List all registered machines."""
    machines = firebase_service.get_machines()
    return jsonify({'machines': machines, 'count': len(machines)})


@app.route('/api/machines', methods=['POST'])
@require_auth('technical')
def create_machine(user):
    """
    Register a machine (Technical Team only).

    Body: machine_id, machine_name, machine_type, location, device_id
    """
    data = request.get_json() or {}

    required = ['machine_id', 'machine_name']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            'error': 'Missing required fields',
            'message': f'Required: {", ".join(required)}',
            'missing': missing
        }), 400

    ok = firebase_service.save_machine(data, created_by=user['uid'])
    if not ok:
        return jsonify({
            'error': 'Save failed',
            'message': 'Could not write machine to Firebase'
        }), 500

    machine = firebase_service.get_machine(data['machine_id'])
    return jsonify({
        'success': True,
        'message': f"Machine {data['machine_id']} registered",
        'machine': machine
    }), 201


@app.route('/api/machines/<machine_id>', methods=['PUT'])
@require_auth('technical')
def edit_machine(machine_id, user):
    """Edit a machine (Technical Team only)."""
    data = request.get_json() or {}
    data['machine_id'] = machine_id

    existing = firebase_service.get_machine(machine_id)
    if not existing:
        return jsonify({
            'error': 'Not found',
            'message': f'Machine {machine_id} is not registered'
        }), 404

    ok = firebase_service.save_machine(data, created_by=user['uid'])
    if not ok:
        return jsonify({
            'error': 'Save failed',
            'message': 'Could not update machine in Firebase'
        }), 500

    return jsonify({
        'success': True,
        'message': f'Machine {machine_id} updated',
        'machine': firebase_service.get_machine(machine_id)
    })


# ============================================================
# Data pipeline exports (RAW / CLEAN Excel)
# ============================================================
@app.route('/api/export/raw', methods=['GET'])
@require_auth('technical')
def export_raw_excel(user):
    """Firebase readings_only -> RAW Excel (untouched sensor export)."""
    try:
        result = export_service.export_raw_excel()
        return send_file(
            result['file'],
            as_attachment=True,
            download_name='readings_raw.xlsx'
        )
    except Exception as e:
        logger.error(f"RAW export failed: {e}")
        return jsonify({
            'error': 'Export failed',
            'message': str(e)
        }), 500


@app.route('/api/export/clean', methods=['GET'])
@require_auth('technical')
def export_clean_excel(user):
    """RAW -> cleaning pipeline -> CLEAN Excel + cleaning report."""
    try:
        result = export_service.export_clean_excel()
        return jsonify({
            'success': True,
            'raw_file': result['raw']['file'],
            'raw_rows': result['raw']['rows'],
            'clean_file': result['clean']['file'],
            'clean_rows': result['clean']['rows'],
            'cleaning_report': result['report'],
            'report_file': result['report_file']
        })
    except Exception as e:
        logger.error(f"Clean export failed: {e}")
        return jsonify({
            'error': 'Cleaning failed',
            'message': str(e)
        }), 500


# ============================================================
# Service requests
# ============================================================
@app.route('/api/service-requests', methods=['GET'])
@require_auth()
def list_service_requests(user):
    """List service requests (optionally filter by machine_id / status)."""
    machine_id = request.args.get('machine_id')
    status = request.args.get('status')
    requests_list = firebase_service.get_service_requests(
        machine_id=machine_id, status=status, limit=200
    )
    return jsonify({
        'service_requests': requests_list,
        'count': len(requests_list)
    })


@app.route('/api/service-requests', methods=['POST'])
@require_auth('admin')
def create_service_request(user):
    """
    Create a service request (Admin/Owner decides - never automatic).

    Body: machine_id, issue, prediction (optional)
    """
    data = request.get_json() or {}

    if not data.get('machine_id'):
        return jsonify({
            'error': 'Missing required fields',
            'message': 'machine_id is required'
        }), 400

    if not firebase_service.get_machine(data['machine_id']):
        return jsonify({
            'error': 'Unknown machine',
            'message': f"Machine {data['machine_id']} is not registered"
        }), 404

    record = {
        'machine_id': data['machine_id'],
        'issue': data.get('issue', 'Not specified'),
        'prediction': data.get('prediction', ''),
        'status': 'REQUESTED',
        'requested_by': user['uid'],
        'requested_at': int(time.time() * 1000),
    }

    request_id = firebase_service.create_service_request(record)
    if not request_id:
        return jsonify({
            'error': 'Save failed',
            'message': 'Could not create service request'
        }), 500

    return jsonify({
        'success': True,
        'message': 'Service request created',
        'request_id': request_id,
        'request': firebase_service.get_service_request(request_id)
    }), 201


@app.route('/api/service-requests/<request_id>/accept', methods=['POST'])
@require_auth('technical')
def accept_service_request(request_id, user):
    """
    Accept a service request (Technical Team).
    Sends acceptance notification (with tracking link) to the Admin.
    """
    req = firebase_service.get_service_request(request_id)
    if not req:
        return jsonify({
            'error': 'Not found',
            'message': f'Service request {request_id} does not exist'
        }), 404

    if req.get('status') != 'REQUESTED':
        return jsonify({
            'error': 'Invalid state',
            'message': f"Request is already {req.get('status')}"
        }), 409

    updates = {
        'status': 'ACCEPTED',
        'accepted_at': int(time.time() * 1000),
        'accepted_by': user['uid'],
    }
    ok = firebase_service.update_service_request(request_id, updates)
    if not ok:
        return jsonify({
            'error': 'Update failed',
            'message': 'Could not update service request'
        }), 500

    # Notify the owner (non-fatal if email fails)
    email_result = email_service.send_service_accepted(
        {**req, **updates}, accepted_by=user.get('name') or user.get('email')
    )

    return jsonify({
        'success': True,
        'message': 'Service request accepted',
        'request': firebase_service.get_service_request(request_id),
        'owner_notified': email_result.get('success', False)
    })


@app.route('/api/service-requests/<request_id>/status', methods=['POST'])
@require_auth('technical')
def update_service_status(request_id, user):
    """
    Update service request status (Technical Team).

    Body: status - one of VISITED, IN_PROGRESS, FIXED, COMPLETED
    """
    data = request.get_json() or {}
    status = data.get('status', '').upper()

    allowed = {'VISITED', 'IN_PROGRESS', 'FIXED', 'COMPLETED'}
    if status not in allowed:
        return jsonify({
            'error': 'Invalid status',
            'message': f'status must be one of: {", ".join(sorted(allowed))}'
        }), 400

    req = firebase_service.get_service_request(request_id)
    if not req:
        return jsonify({
            'error': 'Not found',
            'message': f'Service request {request_id} does not exist'
        }), 404

    updates = {'status': status}
    now_ms = int(time.time() * 1000)
    if status == 'VISITED':
        updates['visited_at'] = now_ms
    elif status == 'COMPLETED':
        updates['completed_at'] = now_ms

    ok = firebase_service.update_service_request(request_id, updates)
    if not ok:
        return jsonify({
            'error': 'Update failed',
            'message': 'Could not update service request'
        }), 500

    return jsonify({
        'success': True,
        'message': f'Status updated to {status}',
        'request': firebase_service.get_service_request(request_id)
    })


# ============================================================
# Maintenance reports
# ============================================================
@app.route('/api/maintenance-reports', methods=['GET'])
@require_auth()
def list_maintenance_reports(user):
    """List maintenance reports (optionally filter by machine_id)."""
    machine_id = request.args.get('machine_id')
    reports = firebase_service.get_maintenance_reports(
        machine_id=machine_id, limit=200
    )
    return jsonify({'maintenance_reports': reports, 'count': len(reports)})


@app.route('/api/maintenance-reports', methods=['POST'])
@require_auth('technical')
def create_maintenance_report(user):
    """
    Create a maintenance report (Technical Team, after service completion).

    Body: request_id, machine_id, problem_found, action_taken,
          parts_replaced, technician_notes
    """
    data = request.get_json() or {}

    required = ['machine_id', 'problem_found', 'action_taken']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            'error': 'Missing required fields',
            'message': f'Required: {", ".join(required)}',
            'missing': missing
        }), 400

    request_id = data.get('request_id')
    if request_id:
        req = firebase_service.get_service_request(request_id)
        if not req:
            return jsonify({
                'error': 'Not found',
                'message': f'Service request {request_id} does not exist'
            }), 404

    record = {
        'request_id': request_id,
        'machine_id': data['machine_id'],
        'problem_found': data['problem_found'],
        'action_taken': data['action_taken'],
        'parts_replaced': data.get('parts_replaced', 'None'),
        'technician_notes': data.get('technician_notes', ''),
        'completed_by': user['uid'],
        'status': 'COMPLETED',
        'completed_at': int(time.time() * 1000),
    }

    report_key = firebase_service.save_maintenance_report(record)
    if not report_key:
        return jsonify({
            'error': 'Save failed',
            'message': 'Could not save maintenance report'
        }), 500

    # Mark the linked service request COMPLETED if provided
    if request_id:
        firebase_service.update_service_request(request_id, {
            'status': 'COMPLETED',
            'completed_at': record['completed_at']
        })

    return jsonify({
        'success': True,
        'message': 'Maintenance report saved',
        'report_id': report_key,
        'report': firebase_service.get_maintenance_reports(limit=1)
    }), 201


# ============================================================
# Report downloads (PDF / Excel)
# ============================================================
@app.route('/api/reports/admin', methods=['GET'])
@require_auth('admin')
def admin_reports(user):
    """Generate Admin report (PDF + Excel)."""
    fmt = request.args.get('format', 'both')
    results = {}

    if fmt in ('pdf', 'both'):
        results['pdf'] = report_service.generate_admin_pdf()
    if fmt in ('excel', 'both'):
        results['excel'] = report_service.generate_admin_excel()

    return jsonify({'success': True, 'reports': results})


@app.route('/api/reports/technical', methods=['GET'])
@require_auth('technical')
def technical_reports(user):
    """Generate Technical report (PDF + Excel). Optional: ?machine_id=TM-001"""
    fmt = request.args.get('format', 'both')
    machine_id = request.args.get('machine_id')
    results = {}

    if fmt in ('pdf', 'both'):
        results['pdf'] = report_service.generate_technical_pdf(machine_id)
    if fmt in ('excel', 'both'):
        results['excel'] = report_service.generate_technical_excel(machine_id)

    return jsonify({'success': True, 'reports': results})


# ============================================================
# Secured generated-file downloads (exports & reports only)
# ============================================================
_ALLOWED_EXPORT_DIRS = [
    (PROJECT_ROOT / "data" / "exports").resolve(),
    (PROJECT_ROOT / "data" / "raw").resolve(),
    (PROJECT_ROOT / "data" / "cleaned").resolve(),
]
_ALLOWED_EXTENSIONS = {'.xlsx', '.pdf', '.json'}


@app.route('/api/download', methods=['GET'])
@require_auth()
def download_generated_file(user):
    """
    Download a generated export/report file by name.

    Security: only files inside data/exports, data/raw or data/cleaned
    are served, only whitelisted extensions, and path traversal is blocked.
    """
    name = request.args.get('file', '')
    if not name or '/' in name or '\\' in name or '..' in name:
        return jsonify({'error': 'Invalid file name'}), 400

    ext = os.path.splitext(name)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({'error': 'File type not allowed'}), 400

    for directory in _ALLOWED_EXPORT_DIRS:
        candidate = directory / name
        try:
            candidate.resolve().relative_to(directory)
        except ValueError:
            continue
        if candidate.exists():
            return send_file(candidate, as_attachment=True, download_name=name)

    return jsonify({
        'error': 'Not found',
        'message': 'File not found - generate it first from the reports panel'
    }), 404


# ============================================================
# Misc
# ============================================================
@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API documentation."""
    return jsonify({
        'name': 'PulseGuard API',
        'version': '2.0.0',
        'description': (
            'Machine Health Monitoring and Predictive Maintenance API '
            'for textile rotating machinery'
        ),
        'endpoints': {
            'GET  /api/health': 'Health check',
            'GET  /api/latest': 'Latest sensor reading + prediction',
            'GET  /api/history?limit=50': 'Reading history',
            'GET  /api/prediction': 'Latest prediction',
            'POST /api/predict': 'Predict {temperature, vibration}',
            'GET  /api/model-info': 'Model information',
            'GET  /api/polling-status': 'Live-prediction poller status',
            'POST /api/auth/login': 'Login {email, password}',
            'GET  /api/machines': 'List machines (auth)',
            'POST /api/machines': 'Register machine (technical)',
            'PUT  /api/machines/<id>': 'Edit machine (technical)',
            'GET  /api/export/raw': 'RAW Excel (technical)',
            'GET  /api/export/clean': 'Clean Excel pipeline (technical)',
            'GET  /api/service-requests': 'List service requests (auth)',
            'POST /api/service-requests': 'Create request (admin)',
            'POST /api/service-requests/<id>/accept': 'Accept (technical)',
            'POST /api/service-requests/<id>/status': 'Update status (technical)',
            'GET  /api/maintenance-reports': 'List reports (auth)',
            'POST /api/maintenance-reports': 'Create report (technical)',
            'GET  /api/reports/admin': 'Admin PDF/Excel (admin)',
            'GET  /api/reports/technical': 'Technical PDF/Excel (technical)',
            'POST /api/test-email': 'Test email config',
            'POST /api/webhook': 'ESP32 direct ingestion (optional)'
        },
        'documentation': 'https://github.com/msmoorthi150607s-star/PulseGuard',
        'status': 'operational'
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500


# Initialize services when app starts
initialize_services()

# Guard against the Flask debug reloader running the polling thread in
# both the supervisor and the worker process (which would create
# duplicate predictions in Firebase).
_is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
_debug_reloader = os.getenv('FLASK_DEBUG', '1') == '1'

if not _debug_reloader or _is_reloader_child:
    start_background_polling()
else:
    logger.info("Debug reloader supervisor process - polling starts in worker")

# Register cleanup on shutdown
import atexit
atexit.register(stop_background_polling)


if __name__ == '__main__':
    flask_env = os.getenv('FLASK_ENV', 'development')
    debug = os.getenv('FLASK_DEBUG', '1' if flask_env == 'development' else '0')

    port = int(os.getenv('PORT', '5000'))
    host = os.getenv('HOST', '0.0.0.0' if flask_env == 'production' else '127.0.0.1')

    logger.info(f"Starting PulseGuard API on {host}:{port}")
    logger.info(f"Environment: {flask_env}")
    logger.info(f"Debug mode: {debug}")

    app.run(
        host=host,
        port=port,
        debug=debug == '1',
        threaded=True
    )
