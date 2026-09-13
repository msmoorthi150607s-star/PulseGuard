# ESP32 Setup - PulseGuard

## Hardware Connections

### DHT11 Temperature/Humidity Sensor
| DHT11 Pin | ESP32 Pin |
|-----------|-----------|
| VCC       | 3.3V      |
| GND       | GND       |
| DATA      | GPIO 4    |

### Vibration Sensor
| Sensor Pin | ESP32 Pin |
|------------|-----------|
| VCC        | 3.3V      |
| GND        | GND       |
| OUT        | GPIO 34   |

### I2C LCD 16x2
| LCD Pin | ESP32 Pin |
|---------|-----------|
| VCC     | 5V        |
| GND     | GND       |
| SDA     | GPIO 21  |
| SCL     | GPIO 22  |

## Library Dependencies

Install these libraries via Arduino Library Manager:

1. **LiquidCrystal I2C** by Frank de Brabander
2. **DHT sensor library** by Adafruit
3. **ArduinoJson** by Benoit Blanchon (version 6.x)

## Configuration

Edit the following in `pulseguard_esp32.ino`:

```cpp
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
```

## I2C LCD Address

If the LCD doesn't display, try changing the I2C address:
- Common addresses: `0x27`, `0x3F`, `0x20`

## Upload Instructions

1. Connect ESP32 via USB
2. Open Arduino IDE
3. Select Board: "ESP32 Dev Module"
4. Select correct COM port
5. Upload the sketch

## Serial Monitor

Open Serial Monitor at 115200 baud to see debug output.

## Troubleshooting

### LCD not working
1. Run I2C scanner sketch to find address
2. Adjust contrast potentiometer on LCD
3. Check SDA/SCL connections

### DHT11 not reading
1. Check GPIO 4 connection
2. Ensure 3.3V power (not 5V)
3. Add 10K pull-up resistor if needed

### WiFi connection fails
1. Verify SSID and password
2. Check ESP32 is within range
3. Restart ESP32 after 30 seconds
