/**
 * PULSEGUARD - ESP32 Machine Health Monitor
 * 
 * Collects temperature (DHT11) and vibration data,
 * displays on I2C LCD, and sends to Firebase Realtime Database.
 * 
 * Hardware:
 * - ESP32
 * - DHT11 (GPIO 4)
 * - Vibration sensor
 * - 16x2 I2C LCD
 * 
 * Architecture:
 * ESP32 → DHT11 + Vibration → LCD → Wi-Fi → Firebase
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ============================================
// WiFi Configuration
// IMPORTANT: Do NOT commit actual credentials to GitHub!
// Use a separate secrets file or environment variables in production.
// For this demo, edit these values directly (they are placeholders).
// ============================================
const char* WIFI_SSID = "YOUR_WIFI_SSID";        // Replace with your WiFi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"; // Replace with your WiFi password

// ============================================
// Firebase Configuration
// ============================================
const char* FIREBASE_URL = "https://pulseguard-7ae33-default-rtdb.firebaseio.com/";

// ============================================
// Sensor Pins
// ============================================
#define DHTPIN 4          // DHT11 data pin
#define DHTTYPE DHT11     // DHT 11 sensor
#define VIBRATION_PIN 34  // Vibration sensor analog pin (GPIO 34)

// ============================================
// LCD Configuration (I2C)
// ============================================
// Adjust I2C address if needed (common: 0x27, 0x3F)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ============================================
// Global Objects
// ============================================
DHT dht(DHTPIN, DHTTYPE);

// ============================================
// Timing Configuration
// ============================================
const unsigned long SEND_INTERVAL = 5000;  // Send to Firebase every 5 seconds
const unsigned long LCD_UPDATE_INTERVAL = 1000;  // Update LCD every 1 second

unsigned long lastSendTime = 0;
unsigned long lastLCDUpdateTime = 0;

// ============================================
// Vibration calibration
// ============================================
// Typical vibration sensor resting value (adjust based on your sensor)
const int VIBRATION_THRESHOLD = 100;  // Analog threshold for vibration detection

void setup() {
  Serial.begin(115200);
  Serial.println("\n========================================");
  Serial.println("PULSEGUARD - Machine Health Monitor");
  Serial.println("========================================");
  
  // Initialize DHT sensor
  dht.begin();
  Serial.println("✓ DHT11 initialized");
  
  // Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("PULSEGUARD");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
  Serial.println("✓ LCD initialized");
  
  // Initialize vibration pin
  pinMode(VIBRATION_PIN, INPUT);
  Serial.println("✓ Vibration sensor initialized");
  
  // Connect to WiFi
  connectToWiFi();
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connected!");
  lcd.setCursor(0, 1);
  lcd.print("Monitoring...");
  delay(2000);
  lcd.clear();
  
  Serial.println("\n========================================");
  Serial.println("System Ready");
  Serial.println("========================================");
}

void loop() {
  unsigned long currentTime = millis();
  
  // Read sensors
  float temperature = readTemperature();
  float humidity = readHumidity();
  int vibrationRaw = readVibration();
  float vibration = calculateVibration(vibrationRaw);
  
  // Update LCD (every 1 second)
  if (currentTime - lastLCDUpdateTime >= LCD_UPDATE_INTERVAL) {
    updateLCD(temperature, humidity, vibration);
    lastLCDUpdateTime = currentTime;
  }
  
  // Send to Firebase (every 5 seconds)
  if (currentTime - lastSendTime >= SEND_INTERVAL) {
    sendToFirebase(temperature, vibration);
    lastSendTime = currentTime;
  }
  
  // Debug output (every 5 seconds)
  if (currentTime - lastSendTime >= SEND_INTERVAL) {
    Serial.print("Temp: ");
    Serial.print(temperature);
    Serial.print("°C | Humidity: ");
    Serial.print(humidity);
    Serial.print("% | Vibration: ");
    Serial.print(vibration, 2);
    Serial.println(" | Sending to Firebase...");
  }
  
  delay(100);  // Small delay to prevent watchdog issues
}

// ============================================
// WiFi Connection
// ============================================
void connectToWiFi() {
  Serial.print("Connecting to WiFi");
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi..");
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi connected!");
    Serial.print("  IP Address: ");
    Serial.println(WiFi.localIP());
    lcd.setCursor(0, 1);
    lcd.print("WiFi: Connected");
    delay(1500);
  } else {
    Serial.println("\n✗ WiFi connection failed!");
    lcd.setCursor(0, 1);
    lcd.print("WiFi: Failed");
    delay(3000);
  }
}

// ============================================
// Sensor Reading Functions
// ============================================
float readTemperature() {
  float t = dht.readTemperature();
  if (isnan(t)) {
    Serial.println("Failed to read temperature from DHT sensor!");
    return 0.0;
  }
  return t;
}

float readHumidity() {
  float h = dht.readHumidity();
  if (isnan(h)) {
    Serial.println("Failed to read humidity from DHT sensor!");
    return 0.0;
  }
  return h;
}

int readVibration() {
  return analogRead(VIBRATION_PIN);
}

float calculateVibration(int rawValue) {
  // Normalize vibration to a 0-10+ scale for consistency
  // Adjust the divisor based on your sensor's max value
  // Common ADC max for ESP32 is 4095
  float normalized = (float)rawValue / 4095.0 * 10.0;
  
  // Clamp to reasonable range
  if (normalized < 0) normalized = 0;
  if (normalized > 20) normalized = 20;
  
  return normalized;
}

// ============================================
// LCD Display
// ============================================
void updateLCD(float temp, float humidity, float vibration) {
  lcd.clear();
  
  // Line 1: Temperature & Humidity
  lcd.setCursor(0, 0);
  lcd.print("Temp:");
  lcd.print(temp, 1);
  lcd.print((char)223);  // Degree symbol
  lcd.print("C Hum:");
  lcd.print(humidity, 0);
  lcd.print("%");
  
  // Line 2: Vibration & Status
  lcd.setCursor(0, 1);
  lcd.print("Vib:");
  lcd.print(vibration, 2);
  
  // Show status indicator
  if (vibration > 5.0 || temp > 40.0) {
    lcd.print(" !CRIT");
  } else if (vibration > 2.0 || temp > 38.0) {
    lcd.print(" !!WARN");
  } else {
    lcd.print(" OK");
  }
}

// ============================================
// Firebase Communication
// ============================================
void sendToFirebase(float temperature, float vibration) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected, skipping Firebase send");
    return;
  }
  
  HTTPClient http;
  
  // Build JSON payload
  StaticJsonDocument<256> doc;
  doc["temperature"] = temperature;
  doc["vibration"] = vibration;
  doc["timestamp"] = millis();  // Using millis for simplicity; can use epoch time
  
  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer);
  
  // Send to Firebase
  String url = String(FIREBASE_URL) + "readings_only.json";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  int httpResponseCode = http.POST(jsonBuffer);
  
  if (httpResponseCode > 0) {
    Serial.print("✓ Firebase update successful: ");
    Serial.println(httpResponseCode);
    
    // Get the record ID from response
    String response = http.getString();
    Serial.print("  Response: ");
    Serial.println(response);
  } else {
    Serial.print("✗ Firebase update failed: ");
    Serial.println(httpResponseCode);
    Serial.println(http.errorToString(httpResponseCode));
  }
  
  http.end();
}
