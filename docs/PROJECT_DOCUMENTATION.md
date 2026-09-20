# PULSEGUARD — Complete Project Documentation (Reverse-Engineered)

> **What this document is:** a faithful description of what is *actually implemented* inside the
> PulseGuard project, based on a file-by-file inspection of the source code — for project
> presentation, viva preparation, debugging, and future maintenance.
>
> Everything here is taken from the real code. Where something is **not** implemented, it is
> explicitly marked. Nothing was invented, and no files were modified to produce this document.

**Stack in one line:** ESP32 (C++) → Firebase Realtime DB → Flask REST API (Python) with Random
Forest model → 3 web dashboards (HTML/CSS/JS) → Gmail SMTP alerts.

---

## Table of Contents

1. [Actual System Architecture](#1--2-actual-system-architecture-as-implemented)
2. [Firebase Structure](#3--4-firebase-structure-reconstructed-from-code)
3. [Sensor Data](#5-sensor-data-from-the-ino-line-by-line)
4. [Data Pipeline](#6-data-pipeline-file--function--input--output)
5. [Machine Learning](#7-machine-learning--the-honest-truth)
6. [Model Input → Output](#8-model-input--output)
7. [Backend / API](#9-backend--api--every-endpoint)
8. [Authentication & Roles](#10-authentication--roles)
9. [Dashboards](#11-dashboards)
10. [Alert / Email System](#12-alert--email-system)
11. [Service Request Workflow](#13-service-request-workflow-as-implemented)
12. [Maintenance Report](#14-maintenance-report)
13. [Excel Data Flow](#15-excel-data-flow)
14. [Report Generation](#16-report-generation)
15. [Security Audit](#17-security-audit)
16. [Folder Architecture](#18-folder-architecture)
17. [Dependencies](#19-dependencies-as-actually-used)
18. [End-to-End Live Flow](#20-end-to-end-live-flow-the-demo-path)
19. [Beginner Explanation](#21-beginner-explanation)
20. [Viva Questions](#22-viva-questions-30-answered-only-from-your-code)
21. [Actual vs Planned](#23-actual-vs-planned)
22. ["My Project in 2 Minutes"](#24-my-project-in-2-minutes-speak-this)
23. [Master Tables](#25-master-tables)
24. [What I Should Learn for Viva](#what-i-should-learn-for-viva-the-12-essentials)

---

## 1 & 2. Actual System Architecture (as implemented)

```
┌──────────────────────────────┐
│ Textile rotating motor (demo)│
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│ DHT11 (GPIO 4)  temperature  │   ← ACTUAL sensor inputs: temperature + vibration ONLY
│ Vibration sensor (GPIO 34)   │     (humidity is read for the LCD but NOT sent to Firebase)
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│ ESP32 firmware               │  esp32/pulseguard_esp32.ino
│ - reads sensors (1s LCD / 5s)│
│ - shows values + OK/WARN/CRIT│
│ - POST every 5s over Wi-Fi   │
└──────────────┬───────────────┘
               ↓ HTTPS POST /readings_only.json
┌──────────────────────────────┐
│ Firebase Realtime Database   │  readings_only · prediction · machines · users ·
│                              │  service_requests · maintenance_reports · settings/email
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│ Flask API (flask_api/app.py) │  22+ REST endpoints, CORS, background poller thread (10s)
│ firebase_service.py  (DB I/O)│  poller: latest reading → model → /prediction →
│ model_service.py     (ML)    │         email on CRITICAL (1h cooldown)
│ auth_service.py      (login) │
│ export/report/email services │
└──────┬───────────┬───────────┘
       ↓           ↓
┌────────────┐ ┌────────────────────────────────────────┐
│ ML model   │ │ Web dashboards (served on port 8000)   │
│ model.pkl  │ │ /            public live monitor       │
│ (Random    │ │ /login.html  Firebase Auth login       │
│  Forest)   │ │ /admin/      Owner dashboard           │
└────────────┘ │ /technical/  Technical dashboard       │
               └────────────────────────────────────────┘
               ↓
     Service request → Accept → Visit → Repair → Maintenance report → PDF/Excel reports
```

**NOT IMPLEMENTED (so you never claim them in viva):**

- Remaining Useful Life (RUL) / "machine will fail in X days" — absent everywhere.
- MPU6050 / accelerometer / gyro — **not used**; a simple analog vibration sensor on GPIO 34 is used.
- Humidity in the cloud pipeline — read for LCD only, never uploaded.
- Auto-creating service requests from warnings — deliberately not automatic; the owner clicks.
- User management UI (create/delete users) — users are created in Firebase Console / bootstrap script.

---

## 3 & 4. Firebase Structure (reconstructed from `firebase_service.py` + `app.py`)

```
readings_only/                 ← INPUT, written only by ESP32, never modified by backend
  └── <Firebase push key>      e.g. -OxQ7...
        ├── temperature : number   (°C, e.g. 36.9)
        ├── vibration   : number   (0–20 normalized, e.g. 0.42)
        └── timestamp   : number   (ESP32 millis(), NOT epoch!)

prediction/                    ← OUTPUT ONLY (minimal schema; never training data)
  └── <push key>
        ├── prediction_id : string  (same as the key)
        ├── record_id     : string  (push key of the source reading)
        ├── prediction    : string  "normal" | "warning" | "critical"
        └── timestamp     : number  (true epoch milliseconds, server-generated)

machines/                      ← created by Technical Team via dashboard
  └── TM-001
        ├── machine_id, machine_name, machine_type
        ├── location, device_id (maps ESP32, e.g. "ESP32_001")
        ├── status          : "ON" | "OFF"     (power toggle, technical-only)
        ├── current_health  : "NORMAL"/"WARNING"/"CRITICAL" (auto-updated by poller)
        └── created_at, created_by (real values, not hardcoded)

users/
  └── <Firebase Auth UID>
        ├── name  : string
        ├── email : string
        └── role  : "admin" | "technical"

service_requests/
  └── <push key>
        ├── request_id, machine_id, issue, prediction
        ├── status : REQUESTED → ACCEPTED → VISITED → IN_PROGRESS → FIXED → COMPLETED
        └── requested_at, accepted_at, accepted_by, visited_at, completed_at

maintenance_reports/
  └── <push key>
        ├── report_id, request_id, machine_id
        ├── problem_found, action_taken, parts_replaced, technician_notes
        └── completed_at, status

settings/email                 ← admin panel "Set Up Your Mails"
        ├── username, password (write-only, never returned by API)
        ├── recipient, tech_recipient
        └── smtp_server, smtp_port
```

### Node ownership summary

| Node | Created by | Read by | Updated by | Deleted by |
|---|---|---|---|---|
| `readings_only` | ESP32 | Flask (poller/API/training/exports) | **nobody** (immutable input) | nobody |
| `prediction` | Flask poller / `/api/predict` | dashboards, `/api/latest` | nobody (append-only) | nobody |
| `machines` | Technical dashboard | both dashboards | technical (edit/toggle), poller (`current_health`) | nobody |
| `users` | auth_service on first login | auth checks on every request | auth_service | nobody |
| `service_requests` | Admin dashboard | both dashboards, reports | technical (status workflow) | nobody |
| `maintenance_reports` | Technical dashboard | both dashboards, reports | nobody after creation | nobody |
| `settings/email` | Admin panel | email_service | admin panel | nobody |

**Timestamp honesty point (important for viva):** the ESP32 sends `millis()` as timestamp
(device uptime, not wall-clock). The backend solves this in
`firebase_service.decode_push_key_timestamp()` — Firebase push keys encode creation time, so
real epoch ms are recovered from the key. That's why `prediction.timestamp` is a real date but
`readings_only.timestamp` is not.

---

## 5. Sensor Data (from the `.ino`, line by line)

| Item | Actual value |
|---|---|
| Sensors | DHT11 (temperature; humidity for LCD only) + analog vibration sensor |
| Pins | DHT11 → **GPIO 4**; Vibration → **GPIO 34** (ADC); LCD I2C addr **0x27**, SDA 21 / SCL 22 |
| Reading rate | LCD update every **1 s**; Firebase send every **5 s** (`SEND_INTERVAL = 5000`) |
| Fields sent | `{temperature, vibration, timestamp}` — POST to `readings_only.json` |
| Vibration scale | `raw / 4095 × 10`, clamped 0–20 |
| Timestamp format | `millis()` (uptime ms) — real time recovered from push key server-side |
| Wi-Fi | Credentials are **placeholders** in the sketch (`YOUR_WIFI_SSID`), edited locally, never committed |
| Reconnect | 30 × 500 ms attempts at boot; if Wi-Fi drops mid-run, sends are skipped until reconnected |
| Sensor failure | `isnan()` → logs error and **returns 0.0** (a 0.0 reading still gets uploaded) |
| LCD behavior | Line 1: temp + humidity; Line 2: vibration + `OK` / `!!WARN` / `!CRIT` using the same 38 °C/2.0 and 40 °C/5.0 thresholds as the model rules |

**ACTUAL SENSOR INPUTS: temperature, vibration. Nothing else reaches the database.**

---

## 6. Data Pipeline (file → function → input → output)

| Step | File / Function | Input | Output & where stored |
|---|---|---|---|
| 1. Collect | `pulseguard_esp32.ino` `loop()` / `sendToFirebase()` | analog+digital pins | JSON → Firebase `readings_only` |
| 2. Retrieve | `firebase_service.py` `get_latest_reading()`, `get_readings()`, `decode_push_key_timestamp()` | `readings_only` | in-memory dicts to API/poller |
| 3. Export RAW | `export_service.py` → `GET /api/export/raw` | all readings | `data/raw/readings_raw.xlsx` (untouched) |
| 4. Clean | `export_service.py` → `GET /api/export/clean` | RAW Excel | `data/cleaned/readings_clean.xlsx` + `cleaning_report.json`; removes missing/invalid rows & duplicates, **flags** out-of-range (never deletes them), **zero interpolation by design** |
| 5. Train | `ml/train_model.py` `run_training_pipeline()` (also `ml/retrain_from_firebase.py` for live retrain) | Firebase readings | `ml/model.pkl` → copied to `flask_api/model.pkl` |
| 6. Predict live | `app.py` background poller thread (10 s) | latest reading | prediction → Firebase `prediction`; email if CRITICAL |
| 7. Serve | 22+ endpoints in `app.py` | DB + model | JSON to dashboards |
| 8. Display | `web/script.js` (3 s poll), `admin.js`, `technical.js` | `/api/latest`, `/api/history` | DOM + Chart.js graphs |

Verified cleaning run (real numbers from your data, 482 readings):
**0 rows removed, 5 out-of-range flagged (preserved), 0 duplicates, 0 interpolated.**

---

## 7. Machine Learning — the honest truth

1. **Algorithm:** Random Forest (`RandomForestClassifier(n_estimators=100, max_depth=5)`) inside
   a scikit-learn `Pipeline` with `StandardScaler` — `ml/train_model.py`.
2. **Training file:** `ml/train_model.py`; retrain script: `ml/retrain_from_firebase.py`
   (pulls ALL of `readings_only`, retrains, copies model to `flask_api/model.pkl`).
3. **Features actually fed to the model:** `temperature`, `vibration` only
   (`feature_columns = ['temperature','vibration']`). The engineered features (hour, rolling
   means, temp×vib product, etc.) are computed in `engineer_features()` but **not** used as
   model inputs.
4. **Target:** `rule_based_label` ∈ {normal, warning, critical}.
5. **Records used:** real Firebase data — 482 readings at the last verified run.
6. **Labels:** **rule-generated** —
   - NORMAL: temp < 38 °C **and** vib < 2.0
   - WARNING: temp 38–40 °C **or** vib 2.0–5.0
   - CRITICAL: temp > 40 °C **or** vib > 5.0
   (`apply_rule_based_labels()`). Real label distribution was ≈ 53 % / 17 % / 30 %.
7. **Split:** 80/20, `random_state=42`, stratified.
8. **Preprocessing:** `StandardScaler` inside the pipeline (saved together with the model — a
   single `model.pkl`).
9. **Serialization:** Python `pickle` → `model.pkl`.
10. **Model comparison:** Logistic Regression, Random Forest, Gradient Boosting trained and
    compared; **best-by-F1 wins** (RF won; LR F1 0.958). 5-fold cross-validation also computed.
11. **Inference:** `model_service.py` → `predict()` with probability/confidence; falls back to
    the same rule thresholds if the model file is missing.
12. **Classes:** normal / warning / critical.
13. **Reported accuracy:** 1.00 on the test split.
14. **What that means:** ⚠️ **These are rule-generated labels, so the reported accuracy measures
    how faithfully the model reproduces those rules — NOT real-world predictive accuracy.**
    The code itself prints this warning, `retrain_from_firebase.py` repeats it, README documents
    it, and `/api/model-info` returns a disclaimer. Below 50 samples the script refuses to train
    and stores a rule-based baseline descriptor instead.
15. **Limitations (real):** no genuine failure labels; thresholds are engineering guesses; a
    single-machine dataset; `millis()` timestamps; 0.0 sentinel on sensor failure is uploaded
    as data.

---

## 8. Model Input → Output

| Input | Source | Used By | Output |
|---|---|---|---|
| temperature (°C) | DHT11 via `readings_only` | model.pkl inference | prediction ∈ {normal, warning, critical} |
| vibration (0–20) | analog sensor via `readings_only` | model.pkl inference | + confidence (max class probability) |

**Code-supported examples (from `train_model.py` test cases):**

- temperature 41.0, vibration 7.0 → rules/model → **critical**
- temperature 38.5, vibration 2.5 → **warning**
- temperature 36.5, vibration 0.42 → **normal**

In the live poller the same two values flow: latest reading → `model_service.predict()` →
`prediction/push` write + optional CRITICAL email.

---

## 9. Backend / API — every endpoint

| Method | Endpoint | Purpose | Auth | Who uses it |
|---|---|---|---|---|
| GET | `/api/health` | component health check | none | all pages, tests |
| GET | `/api/latest` | latest reading + prediction (+`prediction_source: stored\|computed`) | none | all dashboards |
| GET | `/api/history?limit=N` | readings joined with stored predictions | none | charts, prediction history |
| GET | `/api/prediction` | latest stored prediction | none | monitor page |
| POST | `/api/predict` | predict for supplied `{temperature, vibration}` | none | testing/manual |
| GET | `/api/model-info` | model metadata + ML disclaimer | none | viva demo |
| GET | `/api/polling-status` | background poller state | none | diagnostics |
| POST | `/api/test-email` | test email from `.env` config | none | setup |
| POST | `/api/webhook` | alternative direct ESP32 ingestion | none | optional |
| POST | `/api/auth/login` | email+password → Firebase ID token + profile + role | none | login page |
| GET/POST | `/api/machines` | list / register machine | any role / **technical** | both dashboards |
| PUT | `/api/machines/<id>` | edit machine — **partial merge** (power toggle uses this) | **technical** | tech dashboard |
| GET | `/api/export/raw` | RAW Excel download | **technical** | tech dashboard |
| GET | `/api/export/clean` | run cleaning pipeline + CLEAN Excel | **technical** | tech dashboard |
| GET/POST | `/api/service-requests` | list / create request | any role / **admin** | both dashboards |
| POST | `/api/service-requests/<id>/accept` | accept request + email owner | **technical** | tech dashboard |
| POST | `/api/service-requests/<id>/status` | VISITED / IN_PROGRESS / FIXED | **technical** | tech dashboard |
| GET/POST | `/api/maintenance-reports` | list / file report (auto-completes request) | any role / **technical** | both dashboards |
| GET | `/api/reports/admin` | simple PDF+Excel report | **admin** | owner dashboard |
| GET | `/api/reports/technical` | detailed PDF+Excel report | **technical** | tech dashboard |
| GET | `/api/download?file=` | secured file download (path-traversal protected) | any role | report/export links |
| GET/POST | `/api/settings/email` | load / save SMTP settings | **admin** | owner panel |
| POST | `/api/settings/email/test` | verify SMTP or send real test email | **admin** | owner panel |

**Background job:** one daemon thread started at boot (`app.py`) — polls `readings_only` every
**10 s**, dedupes by `record_id`, runs the model, writes `prediction`, updates
`machines/{id}/current_health`, and emails **CRITICAL** alerts with a **1-hour cooldown**
(`ALERT_COOLDOWN_SECONDS`). Errors are logged, never crash the server.

---

## 10. Authentication & Roles

- **System:** Firebase Authentication (Email/Password provider). Passwords live only with
  Google — never in the Realtime DB or code.
- **Login flow:** `login.html` → `POST /api/auth/login` → `auth_service.login()` calls Google's
  Identity Toolkit `accounts:signInWithPassword` → returns ID token + profile; on first login a
  `users/{uid}` profile is created and the role auto-assigned (emails listed in `ADMIN_EMAILS`
  in `.env` → admin; everyone else → technical).
- **Token verification:** every protected endpoint requires `Authorization: Bearer <token>`;
  the server verifies via Google `accounts:lookup?key=API_KEY`.
- **Enforcement:** role checks per endpoint; verified live — admin toggling power gets **403**,
  no token gets **401**.
- **Accounts that exist (created via `bootstrap_auth.py`, verified sign-ins):**
  `admin@123gmail.com` (admin role) and `tech@123gmail.com` (technical role).
  Passwords are simple demo ones — change after the demonstration.

---

## 11. Dashboards

| Page | Role | Shows | Poll | Actions |
|---|---|---|---|---|
| `index.html` | public | big TEMP/VIB readouts, machine-state badge with message, Chart.js temperature & vibration trend charts, recent-readings table, maintenance-status banner, last-updated, API connection dot | 3 s | view only; login link |
| `login.html` | — | email/password form via API | — | login → role-based redirect |
| `admin/index.html` | **Owner** | giant health banner: **MACHINE NORMAL / MACHINE ATTENTION / MACHINE PROBLEM**, simple readouts, My Machines table (health + read-only **Power ON/OFF** column), Request Service form, Service Requests table, Maintenance History, "My Reports" (PDF+Excel), **Set Up Your Mails** panel | 10 s | request service, generate report, save/verify/test email |
| `technical/index.html` | **Technical** | Live Monitoring (temp, vib, prediction, reading timestamp, **sensor-health freshness: OK/STALE/NO DATA**), Machine Registration form, machines table with **ON/OFF power toggle buttons**, Data Pipeline panel (RAW download, Run Cleaning), Service Requests with Accept/status buttons, Prediction History, Complete Service (maintenance report form), Technical Report button | 5 s live / 15 s lists | register machine, toggle power, exports, accept/progress requests, file report, generate report |

**On each state:**

- **NORMAL** → green "Everything looks good."
- **WARNING** → amber "MACHINE ATTENTION — Please check the machine." No email, no automatic request.
- **CRITICAL** → red "MACHINE PROBLEM — Immediate attention required." + automatic email to both
  recipients (1 h cooldown).

The machine-power toggle is *declared* by the tech team (not read from hardware) — the admin
sees it read-only.

---

## 12. Alert / Email System

- **Trigger:** poller sees a **CRITICAL** prediction → `email_service.send_critical_alert()`;
  also an owner-notification email when technical **accepts** a request.
- **Recipients:** owner (`recipient`) + technical team (`tech_recipient`) — configured in the
  admin panel, stored in `settings/email`, overriding `.env` without restart.
- **Library/config:** Python `smtplib` + `ssl`, SMTP `smtp.gmail.com:587` STARTTLS; credentials
  only from panel/`.env`.
- **Cooldown:** 1 hour between CRITICAL emails (duplicate prevention).
- **Failure handling:** SMTP errors are caught and logged; poller and API keep running; the
  admin panel surfaces the raw SMTP error (e.g. the 535 BadCredentials case).
- **Verified:** real test emails were sent successfully through SMTP with a Gmail App Password.
  The password field is write-only (the API never returns it).

---

## 13. Service Request Workflow (as implemented)

| Step | UI | Endpoint | DB write | Status |
|---|---|---|---|---|
| 1. Owner requests | admin → Request Service | `POST /api/service-requests` | `service_requests` | `REQUESTED` |
| 2. Tech accepts | technical → Accept button | `POST .../accept` | `accepted_at`, `accepted_by` | `ACCEPTED` + owner email |
| 3. Visit | technical → Visited | `POST .../status` | `visited_at` | `VISITED` |
| 4. Repair | technical → In Progress / Fixed | `POST .../status` | — | `IN_PROGRESS` / `FIXED` |
| 5. Report | technical → Complete Service form | `POST /api/maintenance-reports` | `maintenance_reports` + request `completed_at` | `COMPLETED` |

Nothing is auto-created — warnings never open a request by themselves (stated in the UI and
enforced in code: only admin can POST a request).

---

## 14. Maintenance Report

- **Created by:** technical team, via the "Complete Service" form.
- **Fields:** `report_id, request_id, machine_id, problem_found, action_taken, parts_replaced,
  technician_notes, completed_at, status`.
- **Stored:** `maintenance_reports/{id}`; the linked request auto-completes.
- **Viewed by:** admin (Maintenance History table) and technical.
- **PDF/Excel:** both generated via `report_service.py` (reportlab / openpyxl) through the admin
  and technical report buttons.

---

## 15. Excel Data Flow

- **RAW:** `data/raw/readings_raw.xlsx` — columns `record_id, temperature, vibration, timestamp`;
  written first, never modified afterwards.
- **CLEAN:** `data/cleaned/readings_clean.xlsx` + `cleaning_report.json` — invalid rows removed,
  duplicates dropped, out-of-range **flagged not deleted**, no interpolation, timestamps
  normalized to epoch ms (via push-key decode).
- **Derived features:** computed only inside training (rolling means, diffs, time features) —
  used for EDA, not as final model inputs.
- **Separation enforced in code:** RAW ≠ CLEAN ≠ predictions ≠ reports. `/prediction` is never
  read as training data (explicit in `retrain_from_firebase.py` docstring and logic).

---

## 16. Report Generation

| Report | Format | User | Data source | Method |
|---|---|---|---|---|
| Admin maintenance report | PDF + Excel | admin | machines, requests, maintenance history | `report_service.py` → `/api/reports/admin` |
| Technical report | PDF + Excel | technical | readings, predictions, alerts, requests, timeline, technician notes | `report_service.py` → `/api/reports/technical` |

Both are fully implemented, tested (40/40 tests pass), and downloadable via the protected
`/api/download` endpoint. **RAW Excel is a separate thing** — the untouched sensor export.

---

## 17. Security Audit

- `flask_api/.env` holds: `FIREBASE_URL`, `FIREBASE_WEB_API_KEY`, `ADMIN_EMAILS`, SMTP/MAIL
  values, `SECRET_KEY`, `PORT` — **git-ignored, verified**.
- `flask_api/serviceAccountKey.json` exists locally — **SECRET FOUND — REDACTED — git-ignored
  and confirmed uncommittable. Rotate it after the demo** (it was shared in chat).
- Wi-Fi credentials: placeholders in the committed `.ino`; real values entered only on the device.
- Email App Password: stored in Firebase `settings/email` (write-only) / `.env` — never
  committed; **also shared in chat — regenerate after the demo**.
- The frontend never contains secrets; CORS is open (fine for localhost demo, would be locked
  down in production).
- `.gitignore` covers `.env`, `*.env` (except `.env.example`), `serviceAccountKey*.json`,
  `__pycache__`, venvs, data outputs, `node_modules`, `.DS_Store`.

---

## 18. Folder Architecture

```
PulseGuard/
├── esp32/pulseguard_esp32.ino      → firmware: sensor reads, LCD, Wi-Fi, Firebase POST
├── ml/
│   ├── train_model.py              → full pipeline: EDA → features → rule labels → 3 models → save best
│   ├── retrain_from_firebase.py    → one-command retrain from live data → copies model.pkl
│   └── requirements.txt
├── flask_api/
│   ├── app.py                (1497 lines) → routes, CORS, background poller thread
│   ├── firebase_service.py   (492)        → all DB I/O, push-key time decode
│   ├── model_service.py                   → model load/predict + rule fallback + disclaimer
│   ├── auth_service.py                    → Firebase Auth REST: login, verify, roles
│   ├── email_service.py                   → SMTP alerts, cooldown, settings override
│   ├── export_service.py                  → RAW Excel → cleaning → CLEAN Excel + report
│   ├── report_service.py                  → PDF (reportlab) + Excel (openpyxl) reports
│   ├── bootstrap_auth.py                  → creates demo users (no secrets inside)
│   ├── model.pkl                          → deployed Random Forest
│   └── .env / .env.example / requirements.txt / serviceAccountKey.json (ignored)
├── web/
│   ├── index.html / style.css / script.js → public monitor (Chart.js, 3 s polling)
│   ├── common.js / common.css             → AuthStore, pgFetch, tokens, shared styling
│   ├── login.html                         → login page
│   ├── admin/  (index.html, admin.js)     → owner dashboard
│   └── technical/ (index.html, technical.js) → tech dashboard
├── data/ (raw/ cleaned/ exports/ + README)
├── docs/USER_MANUAL.md  ·  docs/PROJECT_DOCUMENTATION.md (this file)
├── test_api.py                            → 40 tests (Flask test client, mocked Firebase/SMTP)
├── README.md · requirements.txt · .gitignore · run scripts
```

---

## 19. Dependencies (as actually used)

- **ESP32:** `Wire`, `LiquidCrystal_I2C`, `WiFi`, `HTTPClient`, `ArduinoJson`, `DHT` (Arduino IDE libraries).
- **Backend:** Flask, flask-cors, python-dotenv, requests, firebase-admin (bootstrap only).
- **ML:** scikit-learn, pandas, numpy, pickle.
- **Reporting:** reportlab (PDF), openpyxl (Excel).
- **Email:** smtplib/ssl (Python standard library).
- **Frontend:** vanilla HTML/CSS/JS, Chart.js 4.4 (CDN), Google Fonts (Inter, JetBrains Mono),
  Font Awesome 6.5.1 (CDN). **No frameworks — no React/Vue.**
- **Tests:** Python standard-library test client style (40 tests).

---

## 20. End-to-End Live Flow (the demo path)

```
Motor on → ESP32 reads temp+vib → LCD shows values + OK/WARN/CRIT
   → POST {temperature, vibration, timestamp} every 5 s → Firebase readings_only
   → Flask poller (every 10 s) fetches latest reading
   → model.pkl predicts normal/warning/critical
   → writes prediction/{id} + updates machines/{id}/current_health
   → if CRITICAL → emails owner + tech team (1 h cooldown)
   → dashboards poll /api/latest (3 s public, 5 s technical, 10 s admin)
   → owner sees MACHINE PROBLEM banner → clicks Request Service
   → tech accepts (owner emailed) → Visited → Repaired → files maintenance report
   → completed; admin/technical PDF+Excel reports available; RAW/CLEAN Excel exports anytime
```

---

## 21. Beginner Explanation

**When you switch ON the motor:** the DHT11 and vibration sensor feed the ESP32. Every second
the LCD refreshes; every 5 seconds the ESP32 posts one JSON record to Firebase over your phone
hotspot. Within 10 seconds the Flask background poller picks that record up, feeds the two
numbers to the saved Random Forest model, and writes the verdict (normal / warning / critical)
into the `prediction` node. Your web pages — which quietly poll the API every 3–10 seconds —
then show the new numbers and the colored status banner without you touching anything.

**WARNING detected:** banner turns amber, "MACHINE ATTENTION — Please check the machine."
No email, no automatic request — you just watch.

**CRITICAL detected:** banner turns red, "MACHINE PROBLEM — Immediate attention required," and
one email goes to the owner and the technical team (maximum one per hour). The machine's health
chip in both dashboards shows CRITICAL.

**When maintenance is requested:** the owner selects the machine and clicks Request Service →
status REQUESTED. The technical dashboard shows it; the technician clicks Accept (the owner
gets an email), then Visited → In Progress → Fixed, and finally files the maintenance report
(problem found, action taken, parts, notes). The request becomes COMPLETED and appears in the
owner's Maintenance History and reports.

---

## 22. Viva Questions (30+, answered only from your code)

1. **Why ESP32?** Built-in Wi-Fi + ADC; one chip reads sensors, drives the LCD, and uploads to
   Firebase over HTTPS REST — no extra module.
2. **Why DHT11?** Cheap digital temperature sensor, adequate for machine-heat monitoring; GPIO 4.
3. **Why MPU6050?** *Not used.* We use a simple analog vibration sensor on GPIO 34 — sufficient
   for magnitude-based condition monitoring. (Say this confidently.)
4. **Why Firebase?** Free, real-time, no server needed on the hardware side — the ESP32 POSTs
   JSON directly; all later layers read from it.
5. **Why Flask?** Lightweight Python REST API that connects Firebase, the ML model, and the web
   dashboards; easy to demo locally.
6. **Why Random Forest?** Best F1 among the three candidates compared (Logistic Regression,
   Random Forest, Gradient Boosting) on our real data; robust on small tabular data.
7. **ML inputs?** Temperature and vibration — the only two model features.
8. **Output?** One of three classes: normal / warning / critical (plus a confidence value).
9. **Training dataset?** Real readings exported from Firebase `readings_only` (482 at last run).
10. **How are labels created?** Rule thresholds (38 °C / 2.0, 40 °C / 5.0) — **rule-generated
    labels**, not human-verified failures.
11. **What does the accuracy mean?** Agreement with those rules — *not* proven real-world
    predictive accuracy. The project states this in code, README, and `/api/model-info`.
12. **Limitations?** No genuine failure labels; threshold-dependent; single machine; `millis()`
    timestamps (real time recovered from push keys); sensor failure uploads 0.0.
13. **If Wi-Fi fails?** ESP32 skips Firebase sends until reconnect; at boot it retries 30 × 0.5 s
    and shows "WiFi: Failed" on the LCD.
14. **If sensor fails?** `isnan()` → logs error, sends 0.0; the technical dashboard's Sensor
    Health shows STALE/NO DATA if readings stop arriving.
15. **How is prediction generated automatically?** A background thread in `app.py` polls every
    10 s, dedupes by record ID, calls the model, writes to `/prediction`.
16. **How does the alert work?** CRITICAL prediction → SMTP email to owner + tech team, 1-hour
    cooldown.
17. **How does the maintenance workflow work?** Owner requests → technical accepts → Visited →
    In Progress → Fixed → maintenance report filed → COMPLETED.
18. **What is predictive maintenance?** Monitoring condition indicators (temperature, vibration)
    to catch abnormal patterns early and schedule service before breakdown — *condition
    classification*, not exact failure-time prediction.
19. **Why textile industry?** Rotating machinery (motors, spindles) in textile plants runs
    continuously; heat and vibration are practical early indicators.
20. **Future improvements?** Genuine labelled failure data for supervised training, real epoch
    timestamps on ESP32 (NTP), multiple machines per model, user management UI, locked-down CORS.
21. **Where do predictions get stored?** `prediction` node — output only, minimal schema, linked
    to readings via `record_id`; never used as training data.
22. **How does login work?** Firebase Authentication email/password; Flask verifies the ID token;
    roles stored in `users/{uid}/role`; first-login auto-role from `ADMIN_EMAILS`.
23. **What does the cleaning pipeline do?** Removes invalid/missing rows and duplicates, flags
    out-of-range values (never deletes them), no interpolation; writes `cleaning_report.json`.
24. **What is RAW Excel vs Technical Excel report?** RAW = untouched sensor export; technical
    report = structured PDF/Excel summary of service history.
25. **What if the model file is missing?** `model_service` falls back to the same documented
    rule thresholds and labels the source accordingly.
26. **How often do dashboards refresh?** Public 3 s, technical 5 s/15 s, admin 10 s.
27. **How is duplicate prediction prevented?** The poller tracks the last processed `record_id`.
28. **How is the owner protected from technical mistakes?** Role checks: only technical edits
    machines; only admin requests service / changes mail settings (verified 403 on violation).
29. **What is the vibration scale?** ADC reading (0–4095) normalized to 0–20, clamped.
30. **Where is the accuracy documented?** README "ML honesty" section, `/api/model-info`
    disclaimer, training-script warnings.
31. **What happens with no data?** Dashboards show NO DATA / "Awaiting data", `/api/latest`
    returns an error JSON, nothing crashes.
32. **How do reports download?** Through `/api/download?file=` with path-traversal protection.

---

## 23. Actual vs Planned

| Feature | Implemented? | Evidence |
|---|---|---|
| Sensor collection (temp+vibration) | ✅ | `pulseguard_esp32.ino` |
| LCD display with status | ✅ | same file (`updateLCD`) |
| Firebase ingestion | ✅ | `sendToFirebase()` — verified 482 live readings |
| Background auto-prediction | ✅ | poller thread in `app.py` (10 s) |
| ML training + comparison | ✅ | `train_model.py` (LR/RF/GB, CV) |
| Honest ML documentation | ✅ | README, `/api/model-info`, script warnings |
| RAW→CLEAN Excel pipeline | ✅ | `export_service.py`, tested (482→482, 5 flagged) |
| Firebase Auth + roles | ✅ | `auth_service.py`, two verified logins |
| Public monitor with charts | ✅ | `index.html`/`script.js`/Chart.js |
| Admin (owner) dashboard | ✅ | `web/admin/` |
| Technical dashboard | ✅ | `web/technical/` |
| Machine registration + power toggle | ✅ | machines endpoints + UI, tested live |
| Email alerts + cooldown + UI setup | ✅ | `email_service.py`, live test email sent |
| Service request workflow | ✅ | 5-step flow, endpoints + both UIs |
| Maintenance reports | ✅ | node + form + auto-complete |
| PDF/Excel reports | ✅ | `report_service.py`, 40/40 tests |
| Secured downloads | ✅ | `/api/download` with traversal guard |
| RUL / lifetime prediction | ❌ NOT IMPLEMENTED (intentionally) | — |
| MPU6050 / extra sensors | ❌ NOT IMPLEMENTED | — |
| User management UI | ❌ (Console/bootstrap only) | — |
| Production hosting/HTTPS | ❌ (localhost demo) | — |

---

## 24. "My Project in 2 Minutes" (speak this)

> "PulseGuard is an IoT condition-monitoring system for rotating machinery in textile plants.
> Motors generate heat and vibration long before they fail, so I monitor exactly those two
> signals. An ESP32 reads a DHT11 temperature sensor and an analog vibration sensor, shows the
> values and a health indicator on a 16×2 LCD, and every five seconds pushes a reading over
> Wi-Fi into Firebase Realtime Database. A Flask backend polls Firebase every ten seconds, feeds
> the latest temperature and vibration into a Random Forest classifier, and writes the result —
> normal, warning, or critical — back to Firebase. The model was trained on real collected data;
> since genuine failure labels weren't available, labels came from transparent engineering
> thresholds, so the measured accuracy shows the model reproduces those rules — the project
> documents this honestly rather than claiming real-world failure prediction. Three web
> dashboards consume the API: a public monitor with live charts, an owner dashboard that answers
> 'is my machine okay?' in one glance, and a technical dashboard for machine registration,
> power control, data exports, and the service workflow. When the condition is critical, the
> system emails the owner and the technical team automatically, with cooldown to prevent spam.
> The owner can request service with one click; the technical team accepts, tracks the visit,
> repairs, and files a maintenance report — which flows into downloadable PDF and Excel reports.
> The raw sensor data is preserved untouched and a documented cleaning pipeline produces the ML
> dataset. Limitations: no genuine failure labels yet, single demo machine, and localhost
> deployment — the code is structured so real labelled data can retrain the model without
> redesign."

---

## 25. Master Tables

### Complete Project Component Table

| Layer | Component | Technology | File | Input | Output | Purpose |
|---|---|---|---|---|---|---|
| Hardware | Sensors | DHT11 + analog vib | `.ino` | physical signals | temp °C, vib 0–20 | condition indicators |
| Firmware | ESP32 program | C++/Arduino | `pulseguard_esp32.ino` | pins | Firebase POSTs | collect + display + upload |
| Database | Realtime DB | Firebase | — | JSON | JSON | single source of truth |
| Backend | REST API | Flask | `flask_api/app.py` | HTTP + DB + model | JSON | integration layer |
| Backend | DB service | requests | `firebase_service.py` | nodes | dicts | all DB I/O |
| Backend | ML service | sklearn/pickle | `model_service.py` | temp+vib | class+confidence | inference |
| Backend | Auth | Firebase Auth REST | `auth_service.py` | email/password | token+role | access control |
| Backend | Email | smtplib | `email_service.py` | CRITICAL event | email | alerting |
| Backend | Exports | pandas/openpyxl | `export_service.py` | readings | RAW/CLEAN xlsx | data pipeline |
| Backend | Reports | reportlab/openpyxl | `report_service.py` | DB entities | PDF+Excel | documentation |
| ML | Training | scikit-learn | `ml/train_model.py` | Firebase data | `model.pkl` | model building |
| Frontend | Monitor | HTML/JS/Chart.js | `web/index.*` | `/api/latest·history` | live UI | public visibility |
| Frontend | Owner | HTML/JS | `web/admin/` | APIs | simple UI | decisions |
| Frontend | Technical | HTML/JS | `web/technical/` | APIs | detailed UI | operations |

### Complete Database Field Dictionary

| Node | Field | Type | Required | Example | Created By | Read By | Updated By |
|---|---|---|---|---|---|---|---|
| readings_only | temperature | number | ✅ | 36.9 | ESP32 | poller, API, training, exports | nobody |
| readings_only | vibration | number | ✅ | 0.42 | ESP32 | same | nobody |
| readings_only | timestamp | number | ✅ | millis() ms | ESP32 | backend (push key gives real time) | nobody |
| prediction | prediction_id | string | ✅ | push key | poller / `/api/predict` | dashboards, `/api/latest` | nobody |
| prediction | record_id | string | ✅ | reading push key | poller | dashboards, joins | nobody |
| prediction | prediction | string | ✅ | "warning" | poller | all UIs | nobody |
| prediction | timestamp | number | ✅ | epoch ms | poller | UIs | nobody |
| machines | machine_id/name/type/location/device_id | string | ✅/✅/opt/opt/opt | TM-001… | technical UI | both dashboards | technical (partial merge) |
| machines | status | "ON"/"OFF" | ✅ | "ON" | technical toggle | admin dashboard | technical |
| machines | current_health | string | ✅ | "CRITICAL" | poller | both dashboards | poller |
| machines | created_at / created_by | number/string | ✅ | real values | POST /api/machines | — | — |
| users | name/email/role | string | ✅ | "admin" | auth_service first login | auth checks | auth_service |
| service_requests | request_id, machine_id, issue, prediction | string | ✅ | — | admin | both | — |
| service_requests | status | enum | ✅ | "ACCEPTED" | admin→tech | both | technical |
| service_requests | requested_at/accepted_at/accepted_by/visited_at/completed_at | mixed | per stage | epoch ms | workflow | reports | workflow |
| maintenance_reports | report_id, request_id, machine_id | string | ✅ | — | technical | both, reports | nobody |
| maintenance_reports | problem_found, action_taken, parts_replaced, technician_notes | string | ✅ | free text | technical | both, reports | nobody |
| maintenance_reports | completed_at, status | mixed | ✅ | epoch ms, COMPLETED | technical | reports | nobody |
| settings/email | username, recipient, tech_recipient, smtp_server, smtp_port | string/number | opt | smtp.gmail.com/587 | admin panel | email_service | admin panel |
| settings/email | password | string | opt | (write-only) | admin panel | email_service | admin panel |

---

## WHAT I SHOULD LEARN FOR VIVA (the 12 essentials)

1. The **exact data rule**: `readings_only` = input (never rewritten), `prediction` = output
   (never trained on).
2. Why accuracy here means **agreement with rule labels** — and say it before the examiner asks.
3. The **three thresholds**: 38 °C / 2.0 → warning; 40 °C / 5.0 → critical.
4. Random Forest **beat LR and GB on F1**; features = temperature + vibration only.
5. The **10-second poller** is what makes the system "live" — not the web page.
6. **Push-key timestamp decoding** explains how real times exist despite `millis()`.
7. Firebase Auth flow: sign-in → ID token → server verify → role from `users/{uid}`.
8. Service-request status chain: REQUESTED → ACCEPTED → VISITED → IN_PROGRESS → FIXED → COMPLETED.
9. Email: SMTP App Password, **1-hour cooldown**, write-only storage.
10. RAW vs CLEAN Excel: untouched original vs documented cleaning (flag, don't delete; no
    interpolation).
11. Failure behavior: Wi-Fi down → skip sends; sensor NaN → 0.0; model missing → rule fallback;
    nothing crashes the API.
12. Why "condition classification / early warning" is the correct term — **never** "exact
    failure prediction" or RUL.

---

*Generated from a full source-code inspection of the PulseGuard repository. No source files
were modified to produce this document.*
