#!/usr/bin/env python3
"""
PulseGuard API Test Script

Run this script to test all API endpoints.
"""

import sys
import json
sys.path.insert(0, 'flask_api')

from app import app


def run_tests():
    """Run all API tests."""
    client = app.test_client()
    tests_passed = 0
    tests_failed = 0
    
    print("=" * 60)
    print("PULSEGUARD API TEST SUITE")
    print("=" * 60)
    print()
    
    # Test 1: Health endpoint
    print("TEST 1: GET /api/health")
    try:
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'PulseGuard API'
        print("  ✅ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 2: Model info endpoint
    print("TEST 2: GET /api/model-info")
    try:
        response = client.get('/api/model-info')
        assert response.status_code == 200
        data = response.get_json()
        assert 'method' in data
        print(f"  ✅ PASSED (method: {data['method']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 3: Prediction - Normal
    print("TEST 3: POST /api/predict (normal conditions)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 36.5, 'vibration': 0.42})
        assert response.status_code == 200
        data = response.get_json()
        assert data['prediction'] == 'normal'
        assert 'message' in data
        print(f"  ✅ PASSED (prediction: {data['prediction']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 4: Prediction - Warning
    print("TEST 4: POST /api/predict (warning conditions)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 39.0, 'vibration': 3.0})
        assert response.status_code == 200
        data = response.get_json()
        assert data['prediction'] == 'warning'
        print(f"  ✅ PASSED (prediction: {data['prediction']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 5: Prediction - Critical
    print("TEST 5: POST /api/predict (critical conditions)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 42.0, 'vibration': 8.0})
        assert response.status_code == 200
        data = response.get_json()
        assert data['prediction'] == 'critical'
        print(f"  ✅ PASSED (prediction: {data['prediction']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 6: Invalid input - wrong type
    print("TEST 6: POST /api/predict (invalid input - wrong type)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 'invalid', 'vibration': 0.42})
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        print(f"  ✅ PASSED (error: {data['error']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 7: Missing fields
    print("TEST 7: POST /api/predict (missing fields)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 36.5})
        assert response.status_code == 400
        data = response.get_json()
        assert 'required_fields' in data
        print(f"  ✅ PASSED (missing: {data['required_fields']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 8: Temperature out of range
    print("TEST 8: POST /api/predict (temperature out of range)")
    try:
        response = client.post('/api/predict',
            json={'temperature': 150, 'vibration': 0.42})
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        print(f"  ✅ PASSED (error: {data['error']})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Test 9: Root endpoint
    print("TEST 9: GET / (root)")
    try:
        response = client.get('/')
        assert response.status_code == 200
        data = response.get_json()
        assert 'endpoints' in data
        print(f"  ✅ PASSED (endpoints: {len(data['endpoints'])})")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        tests_failed += 1
    print()
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    print(f"Total:  {tests_passed + tests_failed}")
    print()
    
    if tests_failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed.")
        return 1


if __name__ == '__main__':
    sys.exit(run_tests())
