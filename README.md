# PULSEGUARD — Machine Health Monitoring & Predictive Maintenance System
### For Rotating Machinery in the Textile Manufacturing Industry

![PulseGuard](https://img.shields.io/badge/PulseGuard-Textile-Machinery-blue)
![ESP32](https://img.shields.io/badge/ESP32-IoT-orange)
![Firebase](https://img.shields.io/badge/Firebase-Realtime-green)
![Flask](https://img.shields.io/badge/Flask-API-lightgrey)
![ML](https://img.shields.io/badge/ML-Condition_Classification-purple)

**A college project demonstrating end-to-end condition monitoring and
predictive-maintenance support for a rotating motor (textile machinery),
using IoT sensors, a cloud database, a documented data pipeline, machine
learning, and role-based dashboards.**

---

## 1. Project Overview

### Domain

| Item | Value |
|---|---|
| Industry | Textile manufacturing |
| Application | Predictive maintenance / condition monitoring |
| Machine | Rotating machinery (demo: rotating motor) |
| Sensors | Temperature (DHT11) + Vibration (analog) only |
| Controller | ESP32 |
| Database | Firebase Realtime Database |

### Problem Statement

In textile mills, rotating motors run continuously. Overheating bearings
and excessive vibration develop gradually, and failures usually appear
without warning, causing unplanned downtime across the production line.
Small mills rarely have instrumentation that warns them early.

### Objectives

1. Continuously collect **temperature** and **vibration** from a rotating machine.
2. Transmit readings to the cloud over Wi-Fi.
3. Classify machine condition as **NORMAL / WARNING / CRITICAL**.
4. Give the **owner** a one-glance answer: *is my machine okay?*
5. Give the **technical team** tools: machine registry, data exports, service workflow, reports.
6. Alert by email on critical conditions.
7. Support the maintenance workflow from service request to maintenance report.

### System Architecture

```
TEXTILE ROTATING MACHINE (demo: rotating motor)
        |
        v
Temperature sensor (DHT11)  +  Vibration sensor
        |
        v
      ESP32  (GPIO 4 = DHT11, GPIO 34 = vibration)
        |
        v  Wi-Fi
FIREBASE REALTIME DATABASE
        |-- readings_only   (raw sensor INPUT, never modified)
        |-- prediction      (ML OUTPUT only - minimal schema)
        |-- machines        (registry, created by Technical Team)
        |-- users           (Firebase Auth profiles: admin / technical)
        |-- service_requests (owner-initiated workflow)
        |-- maintenance_reports (post-service reports)
        |
        v
FLASK API  (port 5000)
        |-- live prediction poller (new reading -> model -> /prediction)
        |-- auth + roles (admin / technical)
        |-- data pipeline: RAW Excel -> cleaning -> CLEAN Excel
        |-- PDF / Excel reports
        |
        v
WEB DASHBOARDS
        |-- /            public live monitor (industrial dark theme)
        |-- /login.html  role-based sign-in
        |-- /admin/      owner dashboard  ("IS MY MACHINE OKAY?")
        |-- /technical/  technical dashboard (detailed)
```

---

## 2. Hardware

| Component | Quantity | Notes |
|-----------|----------|-------|
| ESP32 Dev Module | 1 | Wi-Fi microcontroller |
| DHT11 | 1 | Temperature (humidity is read for LCD only, NOT stored) |
| Vibration sensor | 1 | Analog output |
| 16x2 I2C LCD | 1 | Local display at the machine |

### Wiring

| Sensor | Pin | ESP32 |
|---|---|---|
| DHT11 | DATA | GPIO 4 |
| Vibration | OUT | GPIO 34 (ADC) |
| LCD I2C | SDA / SCL | GPIO 21 / GPIO 22 |

Full setup instructions: [`esp32/README.md`](esp32/README.md)

> The stored cloud data contains **only** temperature, vibration, and a
> timestamp — exactly matching the hardware actually deployed.

---

## 3. Firebase Structure (Data Integrity Rules)

```
PulseGuard
├── users/{uid}                  # name, email, role (admin | technical)
│                                # passwords live ONLY in Firebase Auth
├── machines/{machine_id}
│     machine_id, machine_name, machine_type, location, device_id,
│     status, current_health, created_at, created_by, updated_at
├── readings_only/{push_key}     # RAW SENSOR INPUT - source of truth
│     temperature, vibration, timestamp
├── prediction/{push_key}        # OUTPUT ONLY - minimal schema:
│     prediction_id, record_id, prediction, timestamp
│     (record_id links back to readings_only; sensor values are
│      NEVER duplicated here and predictions are NEVER used as
│      training data)
├── service_requests/{id}
│     request_id, machine_id, issue, prediction, status,
│     requested_at, accepted_at, accepted_by, visited_at, completed_at
│     status: REQUESTED -> ACCEPTED -> VISITED -> IN_PROGRESS -> FIXED -> COMPLETED
└── maintenance_reports/{id}
      report_id, request_id, machine_id, problem_found, action_taken,
      parts_replaced, technician_notes, completed_at, status
```

**Data-integrity guarantees implemented in code:**

- `readings_only` is never rewritten or cleaned in place.
- `prediction` records are written by `firebase_service.save_prediction()`
  with a **fixed minimal schema** (extra fields are stripped).
- Training scripts read **only** `/readings_only`, never `/prediction`.
- RAW Excel, CLEAN Excel, and reports are stored separately (see below).

---

## 4. Data Pipeline (RAW Excel → Clean Excel)

```
Firebase /readings_only
    ->  data/raw/readings_raw.xlsx        (untouched export)
    ->  documented cleaning
    ->  data/cleaned/readings_clean.xlsx  (+ cleaning_report.json)
```

Cleaning rules (all documented in `cleaning_report.json`):

1. Drop rows with missing / non-numeric temperature or vibration.
2. Drop duplicates (same `record_id`, or identical temp+vibration+timestamp).
3. **Flag but preserve** out-of-range values (`excluded_out_of_range` column).
4. Normalize timestamps to epoch ms (device uptime values are replaced by
   the Firebase push-key creation time).
5. Sort chronologically.
6. **No interpolation / gap-filling** — the honest choice for sensor logs.

Run it:

```cmd
:: from the Technical dashboard (one click), or:
cd flask_api
python -c "from export_service import get_export_service; print(get_export_service().export_clean_excel())"
```

Latest verified run on real data: **482 raw rows → 482 clean rows,
5 rows flagged out-of-range (preserved), 0 interpolated.**

---

## 5. Machine Learning (Honest Documentation)

### What the model is

- **Algorithm:** Random Forest Classifier (compared against Logistic
  Regression and Gradient Boosting on the real dataset; Random Forest
  had the best cross-validated F1).
- **Features:** `temperature`, `vibration` (real sensor inputs only).
- **Classes:** NORMAL / WARNING / CRITICAL.

### How training data was labelled — READ THIS

The collected real data contains **no human-labelled failure events**.
Labels were **generated by rules**:

- NORMAL: temp < 38 °C AND vibration < 2.0
- WARNING: temp 38–40 °C OR vibration 2.0–5.0
- CRITICAL: temp > 40 °C OR vibration > 5.0

### What the reported accuracy actually means

Training reports ~99–100 % accuracy. That number means **"the model
learned to reproduce the rule thresholds"** — it is accuracy against
rule-generated labels, **NOT** proof of real-world predictive accuracy.
It does not validate that the thresholds correctly identify real machine
failures. This is stated in the API (`/api/model-info` disclaimer), in the
training code, and in every evaluation output.

### Current real dataset (evaluated on actual Firebase data)

| Item | Value |
|---|---|
| Records | 482 (real ESP32 readings) |
| Class distribution (rule labels) | normal 54 %, warning 16 %, critical 30 % |
| Models compared | Logistic Regression, Random Forest, Gradient Boosting |
| Selected | Random Forest (test F1 = 1.00 vs rules; LR = 0.958) |
| Caveat | Labels are rule-generated; see above |

### Path to genuine ML

When real incidents occur, have an engineer tag those readings
(`label` field, or a separate labels file). The pipeline then retrains on
human labels and evaluation becomes meaningful. Until then PulseGuard is
correctly described as **"machine condition classification with a
transparent rule-informed model"**, not "failure prediction".

---

## 6. Roles & Workflows

### Admin / Owner (non-technical)

- Sees a single big answer: **MACHINE NORMAL / MACHINE ATTENTION / MACHINE PROBLEM**
- Simple temperature/vibration readouts + last-update time
- Views machines, service requests, maintenance history
- **Decides** whether to request service (nothing is automatic)
- Downloads a simple maintenance report (PDF + Excel)

### Technical Team

- Registers / edits machines (machine_id, name, type, location, device_id)
- Live monitoring: temperature, vibration, prediction, sensor health, poller status
- Downloads RAW Excel, runs the cleaning pipeline
- Sees prediction history and full service-request queue
- Accepts requests (owner is notified by email with a tracking link),
  progresses status, and files the maintenance report when done
- Generates detailed technical reports (PDF + Excel)

### Service Workflow

```
ALERT (owner sees WARNING/CRITICAL)
  -> OWNER clicks "Request Service"
  -> service_requests (REQUESTED)
  -> TECHNICAL accepts (ACCEPTED, owner notified by email)
  -> VISITED -> IN_PROGRESS -> FIXED
  -> maintenance report filed -> COMPLETED
```

---

## 7. Installation

### Prerequisites

- Python 3.10+
- Arduino IDE (for the ESP32)
- A Firebase project with Realtime Database

### Python setup

```cmd
cd PulseGuard
pip install -r requirements.txt
```

### Configuration

Copy `flask_api/.env.example` to `flask_api/.env` and fill in:

| Variable | Purpose |
|---|---|
| `FIREBASE_URL` | Realtime Database URL |
| `FIREBASE_WEB_API_KEY` | Firebase Web API key (enables login) |
| `ADMIN_EMAILS` | Comma-separated emails that get the admin role on first login |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | Sender account (Gmail: use an **App Password**) |
| `MAIL_RECIPIENT` | Owner email (critical alerts) |
| `MAIL_TECH_RECIPIENT` | Technical team email (critical alerts) |

**Never commit `.env`** — it is git-ignored, and no credentials exist in
the source code.

### User accounts

Create users in **Firebase Console → Authentication → Users**
(email + password). Roles are assigned automatically on first login:
emails listed in `ADMIN_EMAILS` become `admin`, everyone else `technical`.
Profiles are stored under `users/{uid}`.

### ESP32 setup

1. Open `esp32/pulseguard_esp32.ino` in Arduino IDE.
2. Install libraries: **LiquidCrystal I2C**, **DHT sensor library**, **ArduinoJson**.
3. Set your Wi-Fi credentials (kept out of Git).
4. Upload, open Serial Monitor at 115200.

---

## 8. Running

```cmd
:: Window 1 - Flask API
cd flask_api
python app.py

:: Window 2 - Web dashboard
cd web
python -m http.server 8000
```

Or double-click `run_pulseguard.bat`.

| URL | Page |
|---|---|
| http://localhost:8000 | Public live monitor |
| http://localhost:8000/login.html | Role-based login |
| http://localhost:8000/admin/ | Admin dashboard |
| http://localhost:8000/technical/ | Technical dashboard |
| http://localhost:5000/ | API documentation (JSON) |

---

## 9. API Endpoints

Public:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check + component status |
| `GET /api/latest` | Latest reading + prediction |
| `GET /api/history?limit=50` | Reading history (joined with predictions) |
| `GET /api/prediction` | Latest stored prediction |
| `POST /api/predict` | Predict `{temperature, vibration}` |
| `GET /api/model-info` | Model info + honest disclaimer |
| `GET /api/polling-status` | Live-prediction poller status |

Authenticated (`Authorization: Bearer <firebase_id_token>`):

| Endpoint | Role | Description |
|---|---|---|
| `POST /api/auth/login` | - | Sign in, returns role |
| `GET /api/machines` | any | List machines |
| `POST /api/machines` | technical | Register machine |
| `PUT /api/machines/<id>` | technical | Edit machine |
| `GET /api/export/raw` | technical | RAW Excel download |
| `GET /api/export/clean` | technical | Run cleaning, get CLEAN Excel + report |
| `POST /api/service-requests` | admin | Create service request |
| `GET /api/service-requests` | any | List service requests |
| `POST /api/service-requests/<id>/accept` | technical | Accept (emails owner) |
| `POST /api/service-requests/<id>/status` | technical | VISITED / IN_PROGRESS / FIXED / COMPLETED |
| `GET /api/maintenance-reports` | any | List reports |
| `POST /api/maintenance-reports` | technical | File maintenance report |
| `GET /api/reports/admin` | admin | Admin PDF + Excel |
| `GET /api/reports/technical` | technical | Technical PDF + Excel |
| `GET /api/download?file=` | any | Secured download of generated files |

---

## 10. Testing

```cmd
python test_api.py
```

**35 tests** cover: health, model info, live readings, history,
prediction (normal/warning/critical), invalid inputs, output-only
prediction schema, auth enforcement (401/403), role-restricted machine
registration, the full service workflow (create → accept → double-accept
rejection → status updates → invalid status rejection), maintenance
report creation + automatic request completion, the cleaning pipeline,
admin/technical report generation, path-traversal protection, 404
handling, and login configuration handling.

Last full run: **Ran 35 tests … OK** (verified against live Firebase data).

---

## 11. Project Structure

```
PulseGuard/
├── esp32/                 # ESP32 sketch + wiring guide
├── ml/                    # training pipeline + retrain-from-Firebase script
├── flask_api/             # Flask API + services (auth, firebase, model,
│                          # email, export, report)
├── web/
│   ├── index.html         # public live monitor (dark industrial theme)
│   ├── login.html         # role-based login
│   ├── common.js/.css     # shared helpers/theme
│   ├── admin/             # owner dashboard
│   └── technical/         # technical dashboard
├── data/
│   ├── raw/               # readings_raw.xlsx   (untouched)
│   ├── cleaned/           # readings_clean.xlsx + cleaning_report.json
│   └── exports/           # generated PDF/Excel reports
├── docs/USER_MANUAL.md    # beginner-friendly run guide
└── test_api.py            # 35-test API suite
```

---

## 12. Limitations (Stated Honestly)

1. **Labels are rule-generated.** Accuracy figures measure rule
   reproduction, not validated failure prediction.
2. **Single demo machine.** Health updates auto-map to a machine only
   when one machine is registered or `device_id` matches.
3. **No RUL claims.** Remaining-useful-life estimation is NOT attempted —
   the data does not support it.
4. **Humidity is displayed on the LCD only** and never stored/used in ML,
   matching the declared sensor inputs.
5. **Vibration spike outliers** (>20 on the 0–20 ADC scale, 5 rows in the
   current dataset) are preserved and flagged, not removed.
6. **Token expiry:** Firebase ID tokens last 1 hour; the dashboards
   require re-login after expiry.

## 13. Future Enhancements

- Engineer-labelled failure data → genuine supervised evaluation
- Spectrum features from a proper accelerometer (if hardware changes)
- Firebase Security Rules for direct client writes
- SMS/WhatsApp alerts, multi-tenant mill support
- Time-window features (rolling std/trend) for earlier anomaly warning

---

## License

MIT — see [LICENSE](LICENSE).

*This is a college project. PulseGuard provides condition-monitoring
support and early warnings; it is not a certified industrial safety system.*
