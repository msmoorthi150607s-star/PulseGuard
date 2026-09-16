"""
Firebase Service for PulseGuard

Handles all Firebase Realtime Database operations.

Nodes managed:
- readings_only        : raw sensor input (READ ONLY here - never rewritten)
- prediction           : ML output ONLY (minimal schema, never training data)
- machines             : machine registry (created by Technical Team)
- users                : Firebase Auth user profiles (uid, name, email, role)
- service_requests     : admin-initiated maintenance workflow
- maintenance_reports  : post-service reports from Technical Team

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
    arrival time of a reading even when the device clock is unreliable.
    """
    try:
        ts = 0
        for ch in key[1:8]:
            ts = ts * 64 + _PUSH_CHARS.index(ch)
        return ts
    except (ValueError, IndexError):
        return 0


def normalize_timestamp_ms(ts: Any, key: str = '') -> int:
    """
    Convert any timestamp representation into epoch milliseconds.

    Handles (verified against live data):
    - epoch milliseconds (> 1e12)          -> as-is
    - epoch seconds (~1.7e9, current ESP32) -> x 1000
    - millis() uptime / missing            -> push-key creation time
    """
    key_ms = decode_push_key_timestamp(key) if key else 0
    if isinstance(ts, (int, float)) and ts > 0:
        if ts > 10**12:
            return int(ts)
        # Epoch seconds for any date >= 2020 (1.6e9)
        if ts >= 1.6e9:
            return int(ts * 1000)
    return key_ms


def _normalize_reading(key: str, reading: Dict) -> Dict:
    """
    Normalize a reading record pulled from Firebase.

    - Uses the push key as record_id when the device does not send one.
    - Normalizes the timestamp to epoch ms (see normalize_timestamp_ms),
      preserving the raw device value in sensor_ts_raw when it differs.
    """
    reading = dict(reading or {})
    reading.setdefault('record_id', key)
    reading['_key'] = key

    raw_ts = reading.get('timestamp')
    ms = normalize_timestamp_ms(raw_ts, key)
    if ms != raw_ts:
        reading['sensor_ts_raw'] = raw_ts
    reading['timestamp'] = ms
    return reading


class FirebaseService:
    """Service class for Firebase Realtime Database operations."""

    def __init__(self, firebase_url: str = None):
        """Initialize Firebase service."""
        self.base_url = firebase_url or FIREBASE_URL
        self.readings_path = "readings_only"
        self.prediction_path = "prediction"
        self.machines_path = "machines"
        self.users_path = "users"
        self.service_requests_path = "service_requests"
        self.maintenance_reports_path = "maintenance_reports"
        self.settings_path = "settings"
        logger.info(f"Firebase service initialized with URL: {self.base_url}")

    # ------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------
    def _get(self, path: str, timeout: int = 15) -> Optional[Dict]:
        """GET a JSON node. Returns None on error or empty node."""
        try:
            response = requests.get(f"{self.base_url}{path}.json", timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data if data else None
        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase GET {path} failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Firebase GET {path}: {e}")
            return None

    def _post(self, path: str, payload: Dict, timeout: int = 15) -> Optional[str]:
        """POST (push) a record. Returns the new push key or None."""
        try:
            response = requests.post(
                f"{self.base_url}{path}.json", json=payload, timeout=timeout
            )
            response.raise_for_status()
            return response.json().get('name')
        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase POST {path} failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Firebase POST {path}: {e}")
            return None

    def _put(self, path: str, payload: Dict, timeout: int = 15) -> bool:
        """PUT (set) a record at an explicit key."""
        try:
            response = requests.put(
                f"{self.base_url}{path}.json", json=payload, timeout=timeout
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase PUT {path} failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in Firebase PUT {path}: {e}")
            return False

    def _patch(self, path: str, payload: Dict, timeout: int = 15) -> bool:
        """PATCH (merge) fields into a record."""
        try:
            response = requests.patch(
                f"{self.base_url}{path}.json", json=payload, timeout=timeout
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase PATCH {path} failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in Firebase PATCH {path}: {e}")
            return False

    # ------------------------------------------------------------
    # Readings (raw sensor input - READ ONLY)
    # ------------------------------------------------------------
    def get_readings(self, limit: int = 100) -> List[Dict]:
        """
        Get the most recent sensor readings.

        Args:
            limit: Maximum number of readings to return

        Returns:
            List of reading records (newest first)
        """
        try:
            logger.info(f"Fetching readings from Firebase (limit: {limit})")
            response = requests.get(
                f"{self.base_url}{self.readings_path}.json",
                timeout=15
            )
            response.raise_for_status()

            data = response.json()
            if not data:
                return []

            # Sort by push key: Firebase push keys are chronological, so the
            # lexicographically largest key is the most recent reading.
            # (Sorting by the timestamp field is unreliable because devices
            # may send millis()-since-boot instead of epoch time.)
            items = sorted(data.items(), key=lambda kv: kv[0], reverse=True)

            readings = [_normalize_reading(k, v) for k, v in items[:limit]]
            return readings

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch readings: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching readings: {e}")
            return []

    def get_all_readings(self) -> List[Dict]:
        """
        Get ALL readings (chronological order) for export/cleaning.

        Used by the export service to produce the RAW Excel file.
        """
        data = self._get(self.readings_path, timeout=60)
        if not data:
            return []
        items = sorted(data.items(), key=lambda kv: kv[0])  # oldest first
        return [_normalize_reading(k, v) for k, v in items]

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

    # ------------------------------------------------------------
    # Predictions (OUTPUT ONLY - minimal schema, never training data)
    # ------------------------------------------------------------
    def save_prediction(self, prediction_data: Dict) -> bool:
        """
        Save a prediction to Firebase.

        Prediction records use the OUTPUT-ONLY schema:
            prediction_id, record_id, prediction, timestamp
        Temperature/vibration intentionally live only in readings_only;
        link back with record_id.
        """
        try:
            # Enforce output-only schema
            record = {
                'prediction_id': prediction_data.get('prediction_id'),
                'record_id': prediction_data.get('record_id'),
                'prediction': prediction_data.get('prediction'),
                'timestamp': prediction_data.get('timestamp'),
            }

            if not all([record['prediction_id'], record['record_id'],
                        record['prediction'], record['timestamp']]):
                logger.warning(f"Prediction record incomplete: {record}")
                return False

            new_key = self._post(self.prediction_path, record)
            if new_key:
                logger.info(f"Prediction saved: {record['prediction_id']} "
                            f"({record['prediction']}) for {record['record_id']}")
                return True
            return False

        except Exception as e:
            logger.error(f"Unexpected error saving prediction: {e}")
            return False

    def get_latest_prediction(self) -> Optional[Dict]:
        """
        Get the most recent prediction.
        """
        data = self._get(self.prediction_path)
        if not data:
            return None
        latest_key = max(data.keys())
        return data[latest_key]

    def get_predictions(self, limit: int = 50) -> List[Dict]:
        """
        Get prediction history (newest first).
        """
        data = self._get(self.prediction_path)
        if not data:
            return []
        items = sorted(data.items(), key=lambda kv: kv[0], reverse=True)
        result = []
        for k, v in items[:limit]:
            v = dict(v or {})
            v.setdefault('_key', k)
            result.append(v)
        return result

    # ------------------------------------------------------------
    # Machines
    # ------------------------------------------------------------
    def get_machines(self) -> List[Dict]:
        """Get all registered machines (sorted by machine_id)."""
        data = self._get(self.machines_path)
        if not data:
            return []
        machines = []
        for k, v in data.items():
            v = dict(v or {})
            v.setdefault('_key', k)
            machines.append(v)
        return sorted(machines, key=lambda m: str(m.get('machine_id', '')))

    def get_machine(self, machine_id: str) -> Optional[Dict]:
        """Get one machine by machine_id (the logical ID, e.g. TM-001)."""
        data = self._get(self.machines_path)
        if not data:
            return None
        for k, v in data.items():
            if isinstance(v, dict) and v.get('machine_id') == machine_id:
                v = dict(v)
                v['_key'] = k
                return v
        return None

    def save_machine(self, machine: Dict, created_by: str) -> bool:
        """
        Register or update a machine. created_by must be the acting
        technical user's Firebase UID (never hardcoded).
        """
        machine_id = machine.get('machine_id')
        if not machine_id:
            logger.error("Machine registration requires machine_id")
            return False
        existing = self.get_machine(machine_id)
        payload = {
            'machine_id': machine_id,
            'machine_name': machine.get('machine_name', machine_id),
            'machine_type': machine.get('machine_type', 'Rotating Motor'),
            'location': machine.get('location', ''),
            'device_id': machine.get('device_id', ''),
            'status': machine.get('status', 'OFF'),
            'current_health': machine.get('current_health', 'UNKNOWN'),
            'created_by': existing.get('created_by') if existing else created_by,
            'created_at': existing.get('created_at') if existing else int(
                __import__('time').time() * 1000
            ),
            'updated_at': int(__import__('time').time() * 1000),
            'updated_by': created_by,
        }
        # Store at a deterministic key derived from machine_id (safe chars)
        key = ''.join(c if c.isalnum() or c in '-_' else '_' for c in machine_id)
        return self._put(f"{self.machines_path}/{key}", payload)

    def update_machine_health(self, machine_id: str, health: str, status: str = None) -> bool:
        """Update only the live health/status fields of a machine."""
        machine = self.get_machine(machine_id)
        if not machine:
            return False
        patch = {'current_health': health}
        if status is not None:
            patch['status'] = status
        return self._patch(f"{self.machines_path}/{machine['_key']}", patch)

    # ------------------------------------------------------------
    # Users (profiles only - passwords live in Firebase Auth)
    # ------------------------------------------------------------
    def get_user(self, uid: str) -> Optional[Dict]:
        data = self._get(f"{self.users_path}/{uid}")
        return dict(data) if isinstance(data, dict) else None

    def save_user(self, uid: str, profile: Dict) -> bool:
        return self._put(f"{self.users_path}/{uid}", profile)

    # ------------------------------------------------------------
    # Service requests
    # ------------------------------------------------------------
    def create_service_request(self, request_data: Dict) -> Optional[str]:
        """Create a service request. Returns the new request_id."""
        request_data.setdefault('status', 'REQUESTED')
        request_data.setdefault('requested_at', int(__import__('time').time() * 1000))
        new_key = self._post(self.service_requests_path, request_data)
        if new_key:
            # Keep request_id inside the record too (spec requirement)
            self._patch(f"{self.service_requests_path}/{new_key}",
                        {'request_id': new_key})
            logger.info(f"Service request created: {new_key}")
        return new_key

    def get_service_requests(self, machine_id: str = None,
                             status: str = None, limit: int = 100) -> List[Dict]:
        """Get service requests (newest first), optionally filtered."""
        data = self._get(self.service_requests_path)
        if not data:
            return []
        items = sorted(data.items(), key=lambda kv: kv[0], reverse=True)
        result = []
        for k, v in items:
            v = dict(v or {})
            v.setdefault('request_id', k)
            v['_key'] = k
            if machine_id and v.get('machine_id') != machine_id:
                continue
            if status and v.get('status') != status:
                continue
            result.append(v)
            if len(result) >= limit:
                break
        return result

    def get_service_request(self, request_id: str) -> Optional[Dict]:
        data = self._get(f"{self.service_requests_path}/{request_id}")
        if isinstance(data, dict):
            data = dict(data)
            data.setdefault('request_id', request_id)
            data['_key'] = request_id
        return data

    def update_service_request(self, request_id: str, updates: Dict) -> bool:
        return self._patch(f"{self.service_requests_path}/{request_id}", updates)

    # ------------------------------------------------------------
    # Maintenance reports
    # ------------------------------------------------------------
    def save_maintenance_report(self, report: Dict) -> Optional[str]:
        """Save a maintenance report. Returns the new report key."""
        report.setdefault('completed_at', int(__import__('time').time() * 1000))
        new_key = self._post(self.maintenance_reports_path, report)
        if new_key:
            self._patch(f"{self.maintenance_reports_path}/{new_key}",
                        {'report_id': new_key})
            logger.info(f"Maintenance report saved: {new_key}")
        return new_key

    def get_maintenance_reports(self, machine_id: str = None,
                                limit: int = 100) -> List[Dict]:
        """Get maintenance reports (newest first), optionally filtered."""
        data = self._get(self.maintenance_reports_path)
        if not data:
            return []
        items = sorted(data.items(), key=lambda kv: kv[0], reverse=True)
        result = []
        for k, v in items:
            v = dict(v or {})
            v.setdefault('report_id', k)
            v['_key'] = k
            if machine_id and v.get('machine_id') != machine_id:
                continue
            result.append(v)
            if len(result) >= limit:
                break
        return result

    # ------------------------------------------------------------
    # Email settings (configured from the Admin dashboard)
    # ------------------------------------------------------------
    def get_email_settings(self) -> Optional[Dict]:
        """Get admin-configured email settings (settings/email node)."""
        data = self._get(f"{self.settings_path}/email")
        return dict(data) if isinstance(data, dict) else None

    def save_email_settings(self, settings: Dict) -> bool:
        """Save admin-configured email settings."""
        return self._put(f"{self.settings_path}/email", settings)

    def delete_email_settings(self) -> bool:
        """Clear stored email settings (falls back to .env values)."""
        try:
            response = requests.delete(
                f"{self.base_url}{self.settings_path}/email.json", timeout=15
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase DELETE settings/email failed: {e}")
            return False


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
