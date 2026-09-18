#!/usr/bin/env python3
"""
PulseGuard - one-time Firebase Auth bootstrap (completion script).

Run this AFTER Firebase Authentication has been initialized once in the
Firebase Console (Authentication > Get started). It then:

  1. Enables the Email/Password sign-in provider
  2. Creates the admin + technical user accounts (idempotent)
  3. Writes role profiles to users/{uid} in Realtime Database
  4. Verifies sign-in via the same REST endpoint the app uses

The Web API key is already fetched and stored in .env (done automatically
via the Firebase Management API). Secrets are never printed.

Run:  python bootstrap_auth.py
"""

import os
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

ADMIN_EMAIL = "admin@123gmail.com"
ADMIN_PASSWORD = "admin123"
TECH_EMAIL = "tech@123gmail.com"
TECH_PASSWORD = "tech123"

IDENTITY_API = "https://identitytoolkit.googleapis.com/v1/accounts"
PROJECT = "pulseguard-7ae33"


def read_env_key() -> str:
    """Read FIREBASE_WEB_API_KEY from .env (never print it)."""
    if not os.path.exists(ENV_PATH):
        sys.exit("[FAIL] flask_api/.env not found")
    for line in open(ENV_PATH, encoding="utf-8"):
        if line.startswith("FIREBASE_WEB_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    sys.exit(
        "[FAIL] FIREBASE_WEB_API_KEY is empty in .env.\n"
        "       Copy it from Firebase Console > Project settings > "
        "General > Web API Key."
    )


def init_admin_sdk():
    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(KEY_PATH),
            {"databaseURL": f"https://{PROJECT}-default-rtdb.firebaseio.com"},
        )
    cred = credentials.Certificate(KEY_PATH)
    return cred.get_access_token().access_token


def enable_email_provider(token: str) -> bool:
    url = (
        "https://identitytoolkit.googleapis.com/admin/v2/projects/"
        f"{PROJECT}/config"
    )
    r = requests.patch(
        url,
        params={"updateMask": "signIn.email.enabled,signIn.email.passwordRequired"},
        json={"signIn": {"email": {"enabled": True, "passwordRequired": True}}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code == 200:
        return True
    print(f"  [FAIL] Could not enable Email/Password provider "
          f"(HTTP {r.status_code}): {r.text[:150]}")
    if "CONFIGURATION_NOT_FOUND" in r.text:
        print("  -> Firebase Authentication is not initialized yet.")
        print("     Open https://console.firebase.google.com > your project")
        print("     > Build > Authentication > click 'Get started',")
        print("     then run this script again.")
    return False


def create_user(email: str, password: str) -> str:
    from firebase_admin import auth

    try:
        user = auth.get_user_by_email(email)
        print(f"  [OK] User already exists: {email}")
        return user.uid
    except auth.UserNotFoundError:
        user = auth.create_user(email=email, password=password,
                                email_verified=True)
        print(f"  [OK] Created user: {email}")
        return user.uid


def save_role(uid: str, email: str, role: str, name: str) -> None:
    from firebase_admin import db

    ref = db.reference(f"users/{uid}")
    profile = ref.get() or {}
    profile.update({
        "uid": uid,
        "email": email,
        "role": role,
        "name": name,
    })
    if "created_at" not in profile:
        profile["created_at"] = int(time.time() * 1000)
    ref.set(profile)
    print(f"  [OK] Role saved: {email} -> {role}")


def verify_login(api_key: str, email: str, password: str) -> bool:
    r = requests.post(
        f"{IDENTITY_API}:signInWithPassword?key={api_key}",
        json={"email": email, "password": password,
              "returnSecureToken": True},
        timeout=15,
    )
    if r.status_code == 200 and r.json().get("idToken"):
        print(f"  [OK] Sign-in verified: {email}")
        return True
    err = r.json().get("error", {}).get("message", "?")
    print(f"  [FAIL] Sign-in failed for {email}: {err}")
    return False


def main() -> None:
    print("=" * 60)
    print("PulseGuard Firebase Auth Bootstrap")
    print("=" * 60)

    if not os.path.exists(KEY_PATH):
        sys.exit(f"[FAIL] serviceAccountKey.json not found at {KEY_PATH}")

    api_key = read_env_key()
    print("[OK] Web API key present in .env")

    print("\n[1/4] Connecting with Admin SDK ...")
    token = init_admin_sdk()
    print("  [OK] Authenticated")

    print("\n[2/4] Enabling Email/Password sign-in ...")
    if not enable_email_provider(token):
        sys.exit(1)

    print("\n[3/4] Creating user accounts + roles ...")
    admin_uid = create_user(ADMIN_EMAIL, ADMIN_PASSWORD)
    tech_uid = create_user(TECH_EMAIL, TECH_PASSWORD)
    save_role(admin_uid, ADMIN_EMAIL, "admin", "Admin")
    save_role(tech_uid, TECH_EMAIL, "technical", "Technical Team")

    print("\n[4/4] Verifying sign-in ...")
    ok1 = verify_login(api_key, ADMIN_EMAIL, ADMIN_PASSWORD)
    ok2 = verify_login(api_key, TECH_EMAIL, TECH_PASSWORD)

    print("\n" + "=" * 60)
    print(f"Admin login:     {ADMIN_EMAIL} / {ADMIN_PASSWORD}  "
          f"{'VERIFIED' if ok1 else 'NOT VERIFIED'}")
    print(f"Technical login: {TECH_EMAIL} / {TECH_PASSWORD}  "
          f"{'VERIFIED' if ok2 else 'NOT VERIFIED'}")
    print("=" * 60)
    if ok1 and ok2:
        print("All done! Restart Flask, then log in at "
              "http://localhost:8000/login.html")
    sys.exit(0 if (ok1 and ok2) else 1)


if __name__ == "__main__":
    main()
