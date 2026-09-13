"""
Firebase Service for PulseGuard

Handles all Firebase Realtime Database operations.
Uses environment variables for configuration.
Never exposes credentials in code.
"""

import os
import logging
from typing import Dict, List, Optional, Any
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase configuration from environment
FIREBASE_URL = os.getenv(
    'FIREBASE_URL',
    'https://pulseguard-7ae33-default-rtdb.firebaseio.com/'
)

# Characters used in Firebase push keys (chronologically ordered)
_PUSH_CHARS = '-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'


def decode_push_key_timestamp(key: str) -> int:
    """
    Decode a Firebase push key into an epoch-milliseconds timestamp.

    Push keys start with a sign character followed by 7 characters that
    encode the creation time (48 bits). This lets us recover the real
    arrival time of a reading even when the ESP32 only sends millis().
    """
    try:
        ts = 0
        for ch in key[1:8]:
            ts = ts * 64 + _PUSH_CHARS.index(ch)
        return ts
    except (ValueError, IndexError):
        return 0


def _normalize_reading(key: str, reading: Dict) -> Dict:
    """
    Normalize a reading record pulled from Firebase.

    - Uses the push key as record_id when the device does not send one.
    - Replaces millis()-since-boot timestamps with the real epoch time
      decoded from the push key, keeping the uptime in sensor_uptime_ms.
    """
    reading = dict(reading or {})
    reading.setdefault('record_id', key)
    reading['_key'] = key

    ts = reading.get('timestamp')
    # Epoch milliseconds today are ~1.79e12; millis() uptime stays < 1e11.
    if not isinstance(ts, (int, float)) or ts < 10**11:
        if ts is not None:
            reading['sensor_uptime_ms'] = ts
        reading['timestamp'] = decode_push_key_timestamp(key)
    return reading


class FirebaseService:
    """Service class for Firebase Realtime Database operations."""
    
    def __init__(self, firebase_url: str = None):
        """Initialize Firebase service."""
        self.base_url = firebase_url or FIREBASE_URL
        self.readings_path = "readings_only"
        self.prediction_path = "prediction"
        logger.info(f"Firebase service initialized with URL: {self.base_url}")
    
    def get_readings(self, limit: int = 100) -> List[Dict]:
        """
        Get sensor readings from Firebase.
        
        Args:
            limit: Maximum number of readings to return (default: 100)
            
        Returns:
            List of reading records
        """
        try:
            logger.info(f"Fetching readings from Firebase (limit: {limit})")
            response = requests.get(
                f"{self.base_url}{self.readings_path}.json",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            if not data:
                return []
            
            # Sort by push key: Firebase push keys are chronological, so the
            # lexicographically largest key is the most recent reading.
            # (Sorting by the timestamp field is unreliable because the ESP32
            # stores millis()-since-boot, not epoch time.)
            items = sorted(data.items(), key=lambda kv: kv[0], reverse=True)
            
            readings = [_normalize_reading(k, v) for k, v in items[:limit]]
            return readings
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch readings: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching readings: {e}")
            return []
    
    def get_latest_reading(self) -> Optional[Dict]:
        """
        Get the most recent sensor reading.
        
        Returns:
            Latest reading record or None
        """
        readings = self.get_readings(limit=1)
        if readings:
            return readings[0]
        return None
    
    def save_prediction(self, prediction_data: Dict) -> bool:
        """
        Save a prediction to Firebase.
        
        Args:
            prediction_data: Prediction record to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Saving prediction to Firebase: {prediction_data.get('prediction_id')}")
            
            # Ensure required fields
            required_fields = ['prediction_id', 'record_id', 'prediction', 
                             'temperature', 'vibration', 'timestamp', 'message']
            
            for field in required_fields:
                if field not in prediction_data:
                    logger.warning(f"Missing required field: {field}")
                    prediction_data[field] = None
            
            response = requests.post(
                f"{self.base_url}{self.prediction_path}.json",
                json=prediction_data,
                timeout=10
            )
            response.raise_for_status()
            
            logger.info(f"Prediction saved successfully: {response.json()}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to save prediction: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving prediction: {e}")
            return False
    
    def get_latest_prediction(self) -> Optional[Dict]:
        """
        Get the most recent prediction.
        
        Returns:
            Latest prediction record or None
        """
        try:
            logger.info("Fetching latest prediction from Firebase")
            response = requests.get(
                f"{self.base_url}{self.prediction_path}.json",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            if not data:
                return None
            
            # Latest prediction = largest push key (see get_readings note)
            latest_key = max(data.keys())
            return data[latest_key] if latest_key in data else None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch predictions: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching predictions: {e}")
            return None
    
    def get_predictions(self, limit: int = 50) -> List[Dict]:
        """
        Get prediction history.
        
        Args:
            limit: Maximum number of predictions to return
            
        Returns:
            List of prediction records
        """
        try:
            logger.info(f"Fetching predictions from Firebase (limit: {limit})")
            response = requests.get(
                f"{self.base_url}{self.prediction_path}.json",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            if not data:
                return []
            
            predictions = sorted(
                data.values(),
                key=lambda x: str(x.get('prediction_id', '')),
                reverse=True
            )
            
            return predictions[:limit]
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch predictions: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching predictions: {e}")
            return []


# Singleton instance
_firebase_service = None


def get_firebase_service() -> FirebaseService:
    """Get or create singleton Firebase service instance."""
    global _firebase_service
    
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    
    return _firebase_service


# For backward compatibility
firebase_service = get_firebase_service()
