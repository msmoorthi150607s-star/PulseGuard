"""
Authentication Service for PulseGuard

Handles Firebase Authentication (email/password) via Google's public REST
API (identitytoolkit). No secrets are stored in this repo - the Web API key
is read from the FIREBASE_WEB_API_KEY environment variable.

Roles (stored under users/{uid}.role in Realtime Database):
- admin      : owner / operator - simple monitoring + service requests
- technical  : maintenance team - machine mgmt, exports, reports, services

NOTE: The REST API here performs SIGN-IN verification (signInWithPassword).
Realtime Database rules must be configured in the Firebase console to
enforce permissions server-side for direct client writes.
"""

import os
import logging
import requests
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Firebase Identity Toolkit endpoint
IDENTITY_API = "https://identitytoolkit.googleapis.com/v1/accounts"

# Default web API key - override with FIREBASE_WEB_API_KEY env var
FIREBASE_WEB_API_KEY = os.getenv('FIREBASE_WEB_API_KEY', '')


class AuthService:
    """Service class for Firebase Authentication operations."""

    def __init__(self, firebase_service=None):
        from firebase_service import get_firebase_service
        self.firebase = firebase_service or get_firebase_service()
        self.api_key = FIREBASE_WEB_API_KEY

    def _api_key(self) -> str:
        return self.api_key or os.getenv('FIREBASE_WEB_API_KEY', '')

    # ------------------------------------------------------------
    # Sign-in / sign-up
    # ------------------------------------------------------------
    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against Firebase Auth.

        Returns:
            {success, user: {uid, email, name, role}, id_token, error, message}
        """
        if not email or not password:
            return {
                'success': False,
                'error': 'invalid_input',
                'message': 'Email and password are required'
            }

        key = self._api_key()
        if not key:
            return {
                'success': False,
                'error': 'not_configured',
                'message': (
                    'FIREBASE_WEB_API_KEY is not set. Add it to flask_api/.env '
                    '(Firebase console > Project settings > Web API key).'
                )
            }

        try:
            response = requests.post(
                f"{IDENTITY_API}:signInWithPassword?key={key}",
                json={
                    'email': email,
                    'password': password,
                    'returnSecureToken': True
                },
                timeout=15
            )
            data = response.json()

            if response.status_code != 200:
                error_msg = data.get('error', {}).get('message', 'UNKNOWN')
                friendly = {
                    'EMAIL_NOT_FOUND': 'No account exists with this email',
                    'INVALID_PASSWORD': 'Incorrect password',
                    'INVALID_LOGIN_CREDENTIALS': 'Invalid email or password',
                    'USER_DISABLED': 'This account has been disabled',
                    'TOO_MANY_ATTEMPTS_TRY_LATER': 'Too many attempts. Try again later.',
                }.get(error_msg, f'Login failed: {error_msg}')
                logger.warning(f"Login failed for {email}: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'message': friendly
                }

            uid = data['localId']
            id_token = data['idToken']

            # Load (or lazily create) the user profile with a role
            profile = self.firebase.get_user(uid)
            if not profile:
                # First login: create a profile. Role defaults to admin
                # only if explicitly listed in ADMIN_EMAILS, else technical.
                admin_emails = [
                    e.strip().lower() for e in os.getenv(
                        'ADMIN_EMAILS', ''
                    ).split(',') if e.strip()
                ]
                role = 'admin' if email.lower() in admin_emails else 'technical'
                profile = {
                    'name': data.get('displayName') or email.split('@')[0],
                    'email': data.get('email', email),
                    'role': role,
                    'created_at': int(__import__('time').time() * 1000),
                }
                self.firebase.save_user(uid, profile)
                logger.info(f"Created user profile for {email} with role={role}")

            logger.info(f"Login successful: {email} (role={profile.get('role')})")
            return {
                'success': True,
                'user': {
                    'uid': uid,
                    'email': profile.get('email', email),
                    'name': profile.get('name', ''),
                    'role': profile.get('role', 'technical')
                },
                'id_token': id_token,
                'refresh_token': data.get('refreshToken'),
                'expires_in': data.get('expiresIn', '3600')
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Firebase Auth request failed: {e}")
            return {
                'success': False,
                'error': 'network_error',
                'message': 'Could not reach authentication service. Check internet.'
            }
        except Exception as e:
            logger.error(f"Unexpected login error: {e}")
            return {
                'success': False,
                'error': 'internal_error',
                'message': 'An unexpected error occurred during login'
            }

    def get_user_profile(self, uid: str) -> Optional[Dict]:
        """Get a user profile by UID."""
        return self.firebase.get_user(uid)

    def list_users(self) -> Dict[str, Dict]:
        """List all user profiles (admin/technical use)."""
        data = self.firebase._get(self.firebase.users_path)
        return data or {}


# Singleton instance
_auth_service = None


def get_auth_service() -> AuthService:
    """Get or create singleton auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
