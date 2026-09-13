# PULSEGUARD - Machine Health Monitoring & Predictive Maintenance System

![PulseGuard](https://img.shields.io/badge/PulseGuard-Machine-Health-blue)
![ESP32](https://img.shields.io/badge/ESP32-IoT-orange)
![Firebase](https://img.shields.io/badge/Firebase-Realtime-green)
![Flask](https://img.shields.io/badge/Flask-API-light blue)
![ML](https://img.shields.io/badge/ML-Prediction-purple)

**A complete college project for machine health monitoring and predictive maintenance using IoT sensors, cloud database, machine learning, and web dashboard.**

---

## 📋 Project Overview

PulseGuard is an end-to-end machine health monitoring system that:

1. **Collects** temperature and vibration data from ESP32 sensors
2. **Displays** real-time readings on an I2C LCD
3. **Transmits** data to Firebase Realtime Database via Wi-Fi
4. **Analyzes** sensor data using machine learning / rule-based baseline
5. **Predicts** machine condition: NORMAL, WARNING, or CRITICAL
6. **Visualizes** data on a professional web dashboard
7. **Notifies** via email for critical conditions

### System Architecture

```
┌─────────────┐
│   ESP32     │
│  + DHT11    │
│  + Vib Sensor│
│  + LCD      │
└──────┬──────┘
       │ Wi-Fi
       ▼
┌──────────────────┐
│  Firebase RTDB   │
│  /readings_only  │
│  /prediction     │
└──────┬───────────┘
       │ REST API
       ▼
┌──────────────────┐
│  Flask API       │
│  + ML/Baseline   │
│  + Email Service │
└──────┬───────────┘
       │ HTTP
       ▼
┌──────────────────┐
│  Web Dashboard   │
│  Charts & Stats  │
│  Real-time View  │
└──────────────────┘
```

---

## ✨ Features

### Hardware Layer
- ✅ ESP32 microcontroller
- ✅ DHT11 temperature & humidity sensor
- ✅ Vibration sensor (analog)
- ✅ 16x2 I2C LCD display
- ✅ Wi-Fi connectivity

### Data Layer
- ✅ Firebase Realtime Database
- ✅ Real-time data storage
- ✅ Historical data retrieval
- ✅ Secure configuration (no hardcoded credentials)

### ML & Prediction Layer
- ✅ Rule-based baseline for demo (clearly labeled)
- ✅ ML pipeline ready for training with labeled data
- ✅ Three condition levels: NORMAL, WARNING, CRITICAL
- ✅ Transparent threshold documentation
- ✅ Model persistence with joblib/pickle

### API Layer
- ✅ RESTful Flask API
- ✅ Health check endpoint
- ✅ Latest reading endpoint
- ✅ History endpoint
- ✅ Prediction endpoint
- ✅ Model info endpoint
- ✅ Email test endpoint
- ✅ CORS support
- ✅ Input validation
- ✅ Error handling

### Web Dashboard
- ✅ Professional responsive design
- ✅ Live sensor readings
- ✅ Temperature chart
- ✅ Vibration chart
- ✅ Recent readings table
- ✅ Machine status display
- ✅ Prediction messages
- ✅ Alert notifications
- ✅ Auto-refresh (5 seconds)
- ✅ Mobile-friendly

### Notification Layer
- ✅ Email alerts for CRITICAL conditions
- ✅ SMTP configuration via environment variables
- ✅ Cooldown/debounce mechanism (prevents spam)
- ✅ Customizable recipient

---

## 🛠️ Hardware

### Components Required

| Component | Quantity | Notes |
|-----------|----------|-------|
| ESP32 Dev Module | 1 | Any ESP32 variant |
| DHT11 Sensor | 1 | Temperature & Humidity |
| Vibration Sensor | 1 | Analog output |
| 16x2 I2C LCD | 1 | With I2C backpack |
| Jumper Wires | - | Male-to-Male & Male-to-Female |
| Breadboard | 1 | For prototyping |
| USB Cable | 1 | For power & programming |

### Wiring Diagram

#### DHT11 Sensor
```
DHT11      →    ESP32
────────────────────────
VCC (3.3V) →    3.3V
GND         →    GND
DATA        →    GPIO 4
```

#### Vibration Sensor
```
Vibration Sensor    →    ESP32
──────────────────────────────────
VCC (3.3V)          →    3.3V
GND                  →    GND
OUT (Analog)         →    GPIO 34
```

#### I2C LCD 16x2
```
LCD Module    →    ESP32
──────────────────────────
VCC (5V)      →    5V
GND            →    GND
SDA            →    GPIO 21
SCL            →    GPIO 22
```

---

## 💻 Software Stack

| Layer | Technology |
|-------|------------|
| Microcontroller | ESP32 (Arduino Framework) |
| Sensors | DHT11, Analog Vibration |
| Display | I2C LCD 16x2 |
| Cloud Database | Firebase Realtime Database |
| Backend API | Flask (Python) |
| Machine Learning | Scikit-learn (ready) / Rule-based (current) |
| Frontend | HTML5, CSS3, JavaScript |
| Charts | Chart.js |
| Email | SMTP (Gmail/outlook/etc.) |

---

## 📁 Project Structure

```
PulseGuard/
│
├── esp32/
│   ├── pulseguard_esp32.ino      # ESP32 Arduino sketch
│   └── README.md                  # ESP32 setup guide
│
├── ml/
│   ├── train_model.py             # ML training pipeline
│   ├── model.pkl                  # Trained model or baseline info
│   ├── requirements.txt           # ML dependencies
│   ├── dataset/                   # Dataset directory (for future use)
│   └── notebooks/                 # Jupyter notebooks (for exploration)
│
├── flask_api/
│   ├── app.py                     # Main Flask application
│   ├── firebase_service.py        # Firebase operations
│   ├── model_service.py           # ML model service
│   ├── email_service.py           # Email notification service
│   ├── requirements.txt           # Flask dependencies
│   └── .env.example               # Environment variables template
│
├── web/
│   ├── index.html                 # Dashboard HTML
│   ├── style.css                  # Dashboard styles
│   └── script.js                  # Dashboard JavaScript
│
├── data/
│   ├── readings.json              # Exported Firebase readings
│   ├── predictions.json           # Exported predictions
│   └── README.md                  # Data documentation
│
├── docs/
│   └── (future documentation)
│
├── .gitignore                     # Git ignore rules
├── requirements.txt               # Root dependencies
├── LICENSE                        # MIT License
└── README.md                      # This file
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Arduino IDE (for ESP32)
- Firebase project (or use existing)
- Gmail account or SMTP server (for email notifications)

### Step 1: Clone Repository

```bash
git clone https://github.com/msmoorthi150607s-star/PulseGuard.git
cd PulseGuard
```

### Step 2: ESP32 Setup

1. Install Arduino IDE
2. Install ESP32 board support
3. Install libraries:
   - LiquidCrystal I2C
   - DHT sensor library
   - ArduinoJson
4. Update `esp32/pulseguard_esp32.ino`:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   ```
5. Upload to ESP32

### Step 3: Firebase Setup

1. Create Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Enable Realtime Database
3. Set security rules (for testing):
   ```json
   {
     "rules": {
       ".read": true,
       ".write": true
     }
   }
   ```
4. Copy database URL:
   ```
   https://your-project-id-default-rtdb.firebaseio.com/
   ```

### Step 4: Python Environment

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Step 5: Configure Environment

```bash
# Copy environment template
cd flask_api
copy .env.example .env  # Windows
# or
cp .env.example .env    # Linux/Mac

# Edit .env with your values
Notepad .env  # Windows
# or
nano .env     # Linux/Mac
```

Required environment variables:

```env
# Firebase
FIREBASE_URL=https://pulseguard-7ae33-default-rtdb.firebaseio.com/

# Flask
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key-change-in-production

# Email (for alerts)
MAIL_USERNAME=24uca143@anjaconline.org
MAIL_PASSWORD=YOUR_EMAIL_PASSWORD
MAIL_RECIPIENT=your-email@example.com

# SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### Step 6: Train/Run ML Model

```bash
cd ml

# Install ML dependencies
pip install -r requirements.txt

# Run training pipeline
python train_model.py
```

This will:
- Load data from `data/readings.json`
- Perform EDA
- Apply rule-based labels (since no real labels exist)
- Train models (if enough data)
- Save `model.pkl`

### Step 7: Start Flask API

```bash
cd flask_api

# Start API
python app.py
```

API will start at `http://127.0.0.1:5000`

### Step 8: Open Dashboard

Open `web/index.html` in a browser, or serve it:

```bash
# Using Python
cd web
python -m http.server 8000

# Open in browser
# http://localhost:8000
```

Or open `web/index.html` directly (may have CORS issues).

---

## 🔌 API Endpoints

### Base URL
`http://localhost:5000`

### Endpoints

#### Health Check
```
GET /api/health
```
**Response:**
```json
{
  "status": "healthy",
  "service": "PulseGuard API",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00",
  "components": {
    "firebase": true,
    "model": true,
    "email": true
  }
}
```

#### Latest Reading
```
GET /api/latest
```
**Response:**
```json
{
  "temperature": 36.5,
  "vibration": 0.42,
  "timestamp": 1725600000000,
  "record_id": "-Nabc123xyz"
}
```

#### Reading History
```
GET /api/history?limit=50
```
**Response:**
```json
{
  "readings": [
    {
      "record_id": "-Nabc123xyz",
      "temperature": 36.5,
      "vibration": 0.42,
      "timestamp": 1725600000000
    }
  ],
  "count": 50,
  "limit": 50
}
```

#### Latest Prediction
```
GET /api/prediction
```
**Response:**
```json
{
  "prediction_id": "pred_20240115_103000_123456",
  "record_id": "-Nabc123xyz",
  "prediction": "normal",
  "temperature": 36.5,
  "vibration": 0.42,
  "timestamp": 1725600005000,
  "message": "Your machine is operating normally..."
}
```

#### Make Prediction (Manual)
```
POST /api/predict
Content-Type: application/json

{
  "temperature": 36.5,
  "vibration": 0.42,
  "record_id": "optional-id"
}
```

**Note:** This endpoint is for manual predictions. The system also performs **automatic predictions** via background polling when new readings arrive in Firebase.

#### Polling Status
```
GET /api/polling-status
```

Returns background polling status:
```json
{
  "running": true,
  "interval_seconds": 10,
  "last_processed_timestamp": 1725600060000,
  "thread_name": "pulseguard-polling"
}
```
**Response:**
```json
{
  "prediction_id": "pred_20240115_103000_123456",
  "record_id": "optional-id",
  "prediction": "normal",
  "temperature": 36.5,
  "vibration": 0.42,
  "timestamp": 1725600005000,
  "message": "Your machine is operating normally...",
  "short_message": "Machine is operating normally with a healthy pattern.",
  "method": "rule_based",
  "confidence": 0.85,
  "firebase_saved": true
}
```

#### Model Info
```
GET /api/model-info
```
**Response:**
```json
{
  "model_path": "ml/model.pkl",
  "is_loaded": true,
  "is_rule_based": true,
  "method": "rule_based_baseline",
  "thresholds": {
    "normal": {"temp_max": 38.0, "vib_max": 2.0},
    "warning": {"temp_max": 40.0, "vib_max": 5.0},
    "critical": {"temp_max": Infinity, "vib_max": Infinity}
  },
  "model_exists": true,
  "disclaimer": "This model uses a rule-based baseline for demonstration...",
  "recommendation": "To train a real ML model..."
}
```

#### Test Email
```
POST /api/test-email
Content-Type: application/json

{
  "recipient": "test@example.com"
}
```
**Response:**
```json
{
  "success": true,
  "message": "Email connection test successful",
  "server": "smtp.gmail.com",
  "port": 587
}
```

---

## 📊 Firebase Database Structure

### Readings (`/readings_only`)

```json
{
  "readings_only": {
    "-Nabc123xyz": {
      "record_id": "-Nabc123xyz",
      "temperature": 36.5,
      "vibration": 0.42,
      "timestamp": 1725600000000
    }
  }
}
```

### Predictions (`/prediction`)

```json
{
  "prediction": {
    "-Npred001": {
      "prediction_id": "-Npred001",
      "record_id": "-Nabc123xyz",
      "prediction": "normal",
      "temperature": 36.5,
      "vibration": 0.42,
      "timestamp": 1725600005000,
      "message": "Your machine is operating normally..."
    }
  }
}
```

---

## 🤖 Machine Learning Pipeline

### Current Status

The project currently uses a **rule-based baseline** for demonstration because:

1. The dataset has **no labels** (normal/warning/critical)
2. Supervised ML requires labeled training data
3. The rule-based system is transparent and well-documented

### Rule-Based Thresholds

| Status | Temperature | Vibration |
|--------|-------------|-----------|
| **NORMAL** | < 38°C | < 2.0 |
| **WARNING** | 38-40°C OR 2.0-5.0 | - |
| **CRITICAL** | > 40°C OR > 5.0 | - |

### Training with Real Labels

When you have labeled data:

1. Add labels to your dataset:
   ```json
   {
     "temperature": 36.5,
     "vibration": 0.42,
     "label": "normal"  // or "warning", "critical"
   }
   ```

2. Place labeled data in `ml/dataset/`

3. Update `train_model.py` to load labeled data

4. Run training:
   ```bash
   cd ml
   python train_model.py
   ```

5. The trained model will be saved as `model.pkl`

### ML Pipeline Features

The training pipeline (`train_model.py`) includes:

- ✅ Data loading (JSON or Firebase)
- ✅ Exploratory Data Analysis (EDA)
- ✅ Feature engineering
- ✅ Multiple model training (Logistic Regression, Random Forest, Gradient Boosting)
- ✅ Cross-validation
- ✅ Model comparison
- ✅ Model evaluation (accuracy, precision, recall, F1)
- ✅ Model evaluation (accuracy, precision, recall, F1)
- ✅ Model persistence
- ✅ Reproducible training process

### ⚠️ Important: What 100% Accuracy Means

**The current model reports 100% accuracy, but this does NOT mean:**

- ❌ The model predicts real machine failures with 100% accuracy
- ❌ The rules used for labeling are validated as correct
- ❌ The model will work accurately in production

**What 100% accuracy actually means:**

- ✅ The model learned to replicate the rule-based labeling perfectly
- ✅ The model correctly identifies which rule-generated label applies
- ✅ The model is consistent with the threshold rules

**Why this happened:**

1. Dataset had NO human labels (no real normal/warning/critical labels)
2. Labels were generated using rule-based thresholds
3. ML model trained on these rule-generated labels
4. Model learned to reproduce the rules (essentially memorizing them)

**This is expected behavior** when training on rule-generated labels without real validation data.

**To get real predictive accuracy:**

1. Collect data with known machine conditions (human-labeled)
2. Include actual failure events with confirmed timestamps
3. Work with maintenance team to validate labels
4. Retrain model on validated labels
5. Test on held-out real failure data

**Current model is suitable for:**
- ✅ College demonstration
- ✅ Proof of concept
- ✅ Learning ML pipeline
- ❌ Production deployment without validation

### ⚠️ Important: What 100% Accuracy Means

**The current model reports 100% accuracy, but this does NOT mean:**

- ❌ The model predicts real machine failures with 100% accuracy
- ❌ The rules used for labeling are validated as correct
- ❌ The model will work accurately in production

**What 100% accuracy actually means:**

- ✅ The model learned to replicate the rule-based labeling perfectly
- ✅ The model correctly identifies which rule-generated label applies
- ✅ The model is consistent with the threshold rules

**Why this happened:**

1. Dataset had NO human labels (no real normal/warning/critical labels)
2. Labels were generated using rule-based thresholds
3. ML model trained on these rule-generated labels
4. Model learned to reproduce the rules (essentially memorizing them)

**This is expected behavior** when training on rule-generated labels without real validation data.

**To get real predictive accuracy:**

1. Collect data with known machine conditions (human-labeled)
2. Include actual failure events with confirmed timestamps
3. Work with maintenance team to validate labels
4. Retrain model on validated labels
5. Test on held-out real failure data

**Current model is suitable for:**
- ✅ College demonstration
- ✅ Proof of concept
- ✅ Learning ML pipeline
- ❌ Production deployment without validation

---

## 📈 Prediction System

### Status Levels

#### NORMAL
**Message:** "Your machine is operating normally. Based on the current temperature and vibration pattern, the machine appears to be in a healthy condition."

**Short:** "Machine is operating normally with a healthy pattern."

#### WARNING
**Message:** "Your machine may be developing an abnormal pattern. Based on the current temperature and vibration readings, a possible issue may occur if this trend continues. Monitor the machine closely."

**Short:** "Possible abnormality detected. Monitor the machine closely."

#### CRITICAL
**Message:** "Your machine may be experiencing a potentially abnormal condition. The current temperature and vibration pattern indicates a possible risk of damage. Please inspect the machine and consider sending it to the maintenance team."

**Short:** "Possible machine damage detected. Inspect the machine and contact the maintenance team."

---

## 📧 Email Notifications

### Configuration

Email notifications are sent when the machine status is **CRITICAL**.

Configure in `.env`:

```env
MAIL_USERNAME=24uca143@anjaconline.org
MAIL_PASSWORD=YOUR_EMAIL_PASSWORD
MAIL_RECIPIENT=your-email@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
ALERT_COOLDOWN_SECONDS=3600
```

### Cooldown

To prevent email spam, alerts are limited to once per hour (configurable).

### Example Email

**Subject:** `[PULSEGUARD] Critical Machine Condition Detected`

**Body:**
```
PulseGuard has detected a potentially abnormal machine condition.

Temperature: 41.2 °C
Vibration: 7.35
Status: CRITICAL

Please inspect the machine and consider contacting the maintenance team.

---
This is an automated message from PulseGuard Machine Health Monitoring System.
```

---

## 🧪 Testing

### Manual Testing

#### 1. Health Check
```bash
curl http://localhost:5000/api/health
```

#### 2. Latest Reading
```bash
curl http://localhost:5000/api/latest
```

#### 3. History
```bash
curl http://localhost:5000/api/history?limit=10
```

#### 4. Make Prediction
```bash
curl -X POST http://localhost:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"temperature": 36.5, "vibration": 0.42}'
```

#### 5. Model Info
```bash
curl http://localhost:5000/api/model-info
```

#### 6. Test Email
```bash
curl -X POST http://localhost:5000/api/test-email \
  -H "Content-Type: application/json" \
  -d '{"recipient": "test@example.com"}'
```

### Test Cases

| Component | Test |
|-----------|------|
| ESP32 sensor reading | Verify DHT11 and vibration sensor output |
| Firebase write | Check data appears in Firebase console |
| Firebase read | Verify API returns Firebase data |
| API health | GET /api/health returns 200 |
| API latest | GET /api/latest returns reading |
| API prediction | POST /api/predict returns prediction |
| ML model loading | Model loads without errors |
| Invalid input | API rejects invalid temperature/vibration |
| Missing data | API handles empty Firebase gracefully |
| Website API connection | Dashboard fetches data successfully |
| Prediction display | Dashboard shows NORMAL/WARNING/CRITICAL |
| Email notification | CRITICAL triggers email (if configured) |
| Email cooldown | Multiple CRITICAL readings don't spam email |

---

## 📝 Development

### Development Order

1. ✅ Inspect existing repository and Firebase data
2. ✅ Verify ESP32 → Firebase pipeline
3. ✅ Create/export dataset from Firebase
4. ✅ Analyze dataset
5. ✅ Determine ML validity (rule-based baseline chosen)
6. ✅ Train model (or create baseline)
7. ✅ Save model.pkl
8. ✅ Build Flask API
9. ✅ Connect Flask API to Firebase + ML model
10. ✅ Build web dashboard
11. ✅ Add email notification
12. ✅ Integrate everything
13. ⏳ Test end-to-end
14. ⏳ Clean GitHub repository
15. ⏳ Write final documentation

---

## 🔒 Security

### Best Practices Implemented

1. **No hardcoded credentials** - All secrets in environment variables
2. **.env not committed** - `.gitignore` excludes `.env`
3. **Firebase credentials protected** - Service account JSON not committed
4. **Input validation** - API validates all inputs
5. **Error handling** - Graceful error responses
6. **CORS controlled** - Appropriate CORS headers

### What NOT to Commit

- `.env` files
- `serviceAccountKey.json`
- WiFi passwords
- Email passwords
- API keys
- Secret keys

---

## ⚠️ Limitations & Disclaimers

### ML Limitations

- **Current model is rule-based**, not a trained ML model
- The system does NOT predict exact machine lifetime (no RUL data)
- Predictions are based on simple thresholds
- ML pipeline is ready for real training when labeled data is available

### Data Limitations

- Limited dataset (142 readings as of this writing)
- No labeled failure data
- Cannot train supervised ML models yet

### Production Readiness

- This is a **college project**, not production-grade software
- Security rules should be tightened for production
- Consider adding authentication for API
- Rate limiting recommended for production
- More robust error handling needed for production

### Hardware Limitations

- DHT11 has ±2°C accuracy
- Vibration sensor is basic analog type
- Calibration may be needed for specific machines

---

## 🌟 Future Improvements

- [ ] Collect labeled training data (normal/warning/critical)
- [ ] Train real ML model with proper evaluation
- [ ] Add more sensors (current, power, acoustic)
- [ ] Implement anomaly detection (unsupervised)
- [ ] Add remaining useful life (RUL) prediction if data supports it
- [ ] Mobile app for notifications
- [ ] User authentication for API
- [ ] Role-based access control
- [ ] Advanced dashboard with more analytics
- [ ] Data export (CSV, PDF reports)
- [ ] Multi-machine support
- [ ] Historical comparison views
- [ ] Maintenance scheduling integration
- [ ] Docker containerization
- [ ] Kubernetes deployment
- [ ] CI/CD pipeline
- [ ] Automated testing suite

---

## 📚 Documentation

- [ESP32 Setup Guide](esp32/README.md)
- [Firebase Setup](docs/firebase-setup.md) (future)
- [API Documentation](#api-endpoints)
- [ML Pipeline](ml/train_model.py)

---

## 🙏 Acknowledgments

This project was created as a college project demonstrating:

- IoT sensor integration
- Cloud database usage
- REST API development
- Machine learning pipeline
- Web dashboard creation
- Email notification system

Special thanks to the open-source communities for:
- ESP32 Arduino core
- Firebase
- Flask
- Scikit-learn
- Chart.js

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**PulseGuard Project**
College Project - Machine Health Monitoring System

For questions or contributions, please open an issue on GitHub.

---

## 🎯 Success Criteria Met

- ✅ ESP32 collects temperature and vibration
- ✅ LCD displays sensor values
- ✅ Wi-Fi connects ESP32 to network
- ✅ Firebase stores sensor readings
- ✅ Flask API serves data
- ✅ Prediction system (rule-based baseline)
- ✅ NORMAL/WARNING/CRITICAL classification
- ✅ Web dashboard displays live data
- ✅ Charts show historical trends
- ✅ Email notification for CRITICAL alerts
- ✅ Professional, clean code structure
- ✅ No hardcoded credentials
- ✅ Clear documentation

---

**PULSEGUARD** - Monitoring Machine Health, One Reading at a Time.
