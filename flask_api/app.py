#!/usr/bin/env python3
"""
PulseGuard Flask API

A REST API for machine health monitoring and predictive maintenance.

Endpoints:
- GET  /api/health              - API health check
- GET  /api/latest              - Get latest sensor reading
- GET  /api/history             - Get reading history
- GET  /api/prediction          - Get latest prediction
- POST /api/predict             - Make prediction for readings
- GET  /api/model-info          - Get model information
- POST /api/test-email          - Test email configuration

Environment Variables:
- FIREBASE_URL: Firebase Realtime Database URL
- FLASK_ENV: Environment (development/production)
- FLASK_DEBUG: Enable debug mode (0/1)
- SECRET_KEY: Flask secret key

Author: PulseGuard Team
License: MIT
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from flask import (
    Flask, 
    jsonify, 
    request, 
    make_response
)
from functools import wraps

# Import services
from firebase_service import get_firebase_service, FirebaseService
from model_service import get_model_service, ModelService
from email_service import get_email_service, EmailService

# Configurelogging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Configuration from environment
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'pulseguard-dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# Service instances
firebase_service: FirebaseService = None
model_service: ModelService = None
email_service: EmailService = None


def initialize_services():
    """Initialize all services."""
    global firebase_service, model_service, email_service
    
    logger.info("Initializing services...")
    
    firebase_service = get_firebase_service()
    model_service = get_model_service()
    email_service = get_email_service()
    
    logger.info("All services initialized")


def add_cors_headers(response):
    """Add CORS headers to response."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response


@app.after_request
def after_request(response):
    """Add CORS headers after each request."""
    return add_cors_headers(response)


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    
    Returns:
        API health status with version and timestamp
    """
    return jsonify({
        'status': 'healthy',
        'service': 'PulseGuard API',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'components': {
            'firebase': firebase_service is not None,
            'model': model_service is not None and model_service.model is not None,
            'email': email_service is not None and bool(os.getenv('MAIL_USERNAME'))
        }
    })


@app.route('/api/latest', methods=['GET'])
def get_latest_reading():
    """
    Get the latest sensor reading from Firebase.
    
    Returns:
        Latest reading with temperature, vibration, and timestamp
    """
    try:
        reading = firebase_service.get_latest_reading()
        
        if not reading:
            return jsonify({
                'error': 'No readings found',
                'message': 'No sensor data available in Firebase'
            }), 404
        
        return jsonify({
            'temperature': reading.get('temperature'),
            'vibration': reading.get('vibration'),
            'timestamp': reading.get('timestamp'),
            'record_id': reading.get('record_id')
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
    Get reading history from Firebase.
    
    Query Parameters:
        limit (int): Maximum number of readings (default: 50, max: 500)
    
    Returns:
        List of historical readings
    """
    try:
        # Get limit from query params
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(1, limit), 500)  # Clamp between 1 and 500
        
        readings = firebase_service.get_readings(limit)
        
        if not readings:
            return jsonify({
                'readings': [],
                'count': 0,
                'message': 'No historical readings found'
            })
        
        # Format readings
        formatted_readings = []
        for reading in readings:
            formatted_readings.append({
                'record_id': reading.get('record_id'),
                'temperature': reading.get('temperature'),
                'vibration': reading.get('vibration'),
                'timestamp': reading.get('timestamp')
            })
        
        return jsonify({
            'readings': formatted_readings,
            'count': len(formatted_readings),
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
    """
    Get the latest prediction from Firebase.
    
    Returns:
        Latest prediction with status, message, and reading data
    """
    try:
        prediction = firebase_service.get_latest_prediction()
        
        if not prediction:
            return jsonify({
                'error': 'No predictions found',
                'message': 'No prediction data available in Firebase'
            }), 404
        
        return jsonify({
            'prediction_id': prediction.get('prediction_id'),
            'record_id': prediction.get('record_id'),
            'prediction': prediction.get('prediction'),
            'temperature': prediction.get('temperature'),
            'vibration': prediction.get('vibration'),
            'timestamp': prediction.get('timestamp'),
            'message': prediction.get('message')
        })
        
    except Exception as e:
        logger.error(f"Error fetching latest prediction: {e}")
        return jsonify({
            'error': 'Failed to fetch prediction',
            'message': str(e)
        }), 500


@app.route('/api/predict', methods=['POST'])
def make_prediction():
    """
    Make a prediction for sensor readings.
    
    Request Body (JSON):
        temperature (float): Temperature in Celsius (required)
        vibration (float): Vibration level (required)
        record_id (str): Optional record ID for tracking
    
    Returns:
        Prediction result with status, message, and details
    """
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'Invalid request',
                'message': 'Request body must be JSON'
            }), 400
        
        # Validate required fields
        temperature = data.get('temperature')
        vibration = data.get('vibration')
        
        if temperature is None or vibration is None:
            return jsonify({
                'error': 'Missing required fields',
                'message': 'temperature and vibration are required',
                'required_fields': ['temperature', 'vibration']
            }), 400
        
        # Convert to float
        try:
            temperature = float(temperature)
            vibration = float(vibration)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid input types',
                'message': 'temperature and vibration must be numeric'
            }), 400
        
        # Validate ranges
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
        
        # Make prediction
        prediction_result = model_service.predict(temperature, vibration)
        
        # Generate prediction ID
        prediction_id = f"pred_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        record_id = data.get('record_id', f"rec_{prediction_id}")
        timestamp = data.get('timestamp', int(datetime.now().timestamp() * 1000))
        
        # Prepare prediction record for Firebase
        prediction_record = {
            'prediction_id': prediction_id,
            'record_id': record_id,
            'prediction': prediction_result['prediction'],
            'temperature': temperature,
            'vibration': vibration,
            'timestamp': timestamp,
            'message': prediction_result.get('message', ''),
            'method': prediction_result.get('method', 'unknown'),
            'confidence': prediction_result.get('confidence', 0)
        }
        
        # Save to Firebase
        saved = firebase_service.save_prediction(prediction_record)
        
        # Send email alert for critical conditions
        email_sent = None
        if prediction_result['prediction'] == 'critical':
            email_result = email_service.send_critical_alert(
                temperature, vibration, 'critical'
            )
            email_sent = email_result
        
        # Build response
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
        
        # Add probabilities if available
        if 'probabilities' in prediction_result:
            response_data['probabilities'] = prediction_result['probabilities']
        
        # Add email status if critical
        if prediction_result['prediction'] == 'critical':
            response_data['email'] = {
                'sent': email_sent.get('success', False) if email_sent else False,
                'message': email_sent.get('message', '') if email_sent else ''
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
    """
    Get information about the current ML model.
    
    Returns:
        Model information including type, status, and configuration
    """
    try:
        info = model_service.get_model_info()
        
        # Add disclaimer for rule-based models
        if info['is_rule_based']:
            info['disclaimer'] = (
                "This model uses a rule-based baseline for demonstration. "
                "It is NOT a trained ML model. Rules are based on temperature and "
                "vibration thresholds. The ML pipeline is ready for training when "
                "labelled data becomes available."
            )
            info['recommendation'] = (
                "To train a real ML model, collect labeled data with known "
                "normal/warning/critical conditions and run ml/train_model.py"
            )
        
        return jsonify(info)
        
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        return jsonify({
            'error': 'Failed to get model info',
            'message': str(e)
        }), 500


@app.route('/api/test-email', methods=['POST'])
def test_email():
    """
    Test email configuration.
    
    Request Body (JSON, optional):
        recipient (str): Test recipient email (optional, uses MAIL_RECIPIENT)
    
    Returns:
        Email connection test result
    """
    try:
        data = request.get_json() or {}
        test_recipient = data.get('recipient')
        
        if test_recipient:
            # Temporarily override recipient for test
            original_recipient = email_service.recipient
            email_service.recipient = test_recipient
        
        result = email_service.test_connection()
        
        if test_recipient:
            email_service.recipient = original_recipient
        
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
    
    This is an alternative to ESP32 writing directly to Firebase.
    Useful for bypassing Firebase security rules during development.
    
    Request Body (JSON):
        temperature (float): Temperature in Celsius
        vibration (float): Vibration level
        humidity (float, optional): Humidity percentage
    
    Returns:
        Prediction result and confirmation
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
        
        # Make prediction
        prediction_result = model_service.predict(float(temperature), float(vibration))
        
        # Generate record ID
        record_id = f"webhook_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        timestamp = int(datetime.now().timestamp() * 1000)
        
        # Save reading to Firebase
        reading_record = {
            'record_id': record_id,
            'temperature': float(temperature),
            'vibration': float(vibration),
            'timestamp': timestamp,
            'humidity': data.get('humidity')
        }
        
        # Note: For webhook, we'd need to add a save_reading method to FirebaseService
        # For now, just return the prediction
        
        # Send email if critical
        email_sent = None
        if prediction_result['prediction'] == 'critical':
            email_result = email_service.send_critical_alert(
                float(temperature), float(vibration), 'critical'
            )
            email_sent = email_result
        
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


@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API documentation."""
    return jsonify({
        'name': 'PulseGuard API',
        'version': '1.0.0',
        'description': 'Machine Health Monitoring and Predictive Maintenance API',
        'endpoints': {
            'GET /api/health': 'Health check',
            'GET /api/latest': 'Get latest sensor reading',
            'GET /api/history': 'Get reading history (limit=50)',
            'GET /api/prediction': 'Get latest prediction',
            'POST /api/predict': 'Make prediction (body: {temperature, vibration, record_id?})',
            'GET /api/model-info': 'Get model information',
            'POST /api/test-email': 'Test email configuration',
            'POST /api/webhook': 'ESP32 webhook endpoint'
        },
        'documentation': 'https://github.com/msmoorthi150607s-star/PulseGuard',
        'status': 'operational'
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested endpoint does not exist',
        'available_endpoints': [
            '/api/health',
            '/api/latest',
            '/api/history',
            '/api/prediction',
            '/api/predict',
            '/api/model-info',
            '/api/test-email',
            '/api/webhook'
        ]
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


if __name__ == '__main__':
    # Get configuration from environment
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
