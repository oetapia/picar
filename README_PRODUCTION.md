# Raspberry Pi Pico - Production Code

This branch contains the production-ready code for the Raspberry Pi Pico car with WiFi API endpoints, sensors, servo, motor control, and OLED display.

## 🚗 Features

- **WiFi API Server**: HTTP REST API endpoints for remote control
- **Motor Control**: Forward/reverse movement with PWM speed control
- **Servo Control**: Steering mechanism (0-180 degrees)
- **Sensors**:
  - MPU-6050 Accelerometer/Gyroscope (tilt, acceleration, orientation)
  - Dual VL53L0X ToF sensors (front left/right distance measurement with angle calculation)
  - HC-SR04 Ultrasonic sensor (rear obstacle detection)
- **OLED Display**: Real-time status display (128x32 SSD1306)
- **LED Indicators**: Front and back lights
- **CORS Support**: Cross-origin resource sharing for web clients

## 📁 File Structure

```
picar/
├── main.py                    # Main application entry point with API server
├── wifi.py                    # WiFi connection management
├── motor.py                   # Motor control module
├── servo.py                   # Servo control module
├── display.py                 # OLED display management
├── lights.py                  # LED light control
├── icons.py                   # Icon loader for OLED display
├── icons.json                 # Icon definitions
├── vl53l0x_mp.py             # VL53L0X ToF sensor driver
├── secrets-template.py        # WiFi credentials template (copy to secrets.py)
├── .gitignore                 # Git ignore patterns
│
├── microdot/                  # Lightweight web framework
│   ├── __init__.py
│   ├── microdot.py
│   └── websocket.py
│
└── sensors/                   # Sensor modules
    ├── __init__.py
    ├── accelerometer.py       # MPU-6050 async monitor
    ├── dual_tof.py           # Dual VL53L0X ToF async monitor
    └── hcsr04.py             # HC-SR04 ultrasonic async monitor
```

## 🔌 Hardware Connections

### Motor Control
- AIN1: GP11
- AIN2: GP12
- PWMA: GP10
- STBY: GP13

### Servo
- PWM: GP22

### Lights
- Front LED: GP5
- Back LED: GP2

### OLED Display (SSD1306)
- SDA: GP18
- SCL: GP19
- I2C Bus: I2C1

### MPU-6050 Accelerometer/Gyroscope
- SDA: GP8
- SCL: GP9
- I2C Bus: I2C0
- Address: 0x68

### Dual VL53L0X ToF Sensors
- Left Sensor:
  - SDA: GP6
  - SCL: GP7
- Right Sensor:
  - SDA: GP20
  - SCL: GP21
- Address: 0x29 (each on separate I2C bus)
- Spacing: 15cm (configurable in dual_tof.py)

### HC-SR04 Ultrasonic Sensor
- Trigger: GP14
- Echo: GP15

### Onboard LED
- LED: GP25 (Pico onboard LED)

## 📡 API Endpoints

### Motor Control
- `GET /api/motor/<speed>` - Set motor speed (-100 to 100)
  - Negative values = reverse
  - Positive values = forward
  - -5 to 5 = stop

### Servo Control
- `GET /api/servo/<angle>` - Set servo angle (0-180 degrees)
  - 0 = full left
  - 90 = center
  - 180 = full right

### Display Control
- `POST /api/text` - Display custom text and icon
  ```json
  {
    "text": "Hello World",
    "icon": "robot"
  }
  ```

### Sensor Data
- `GET /api/accelerometer` - Get MPU-6050 data (acceleration, gyroscope, tilt, orientation)
- `GET /api/tof` - Get dual ToF sensor data (distances, angle, orientation)
- `GET /api/ultrasonic` - Get HC-SR04 rear distance

### Status
- `GET /api/status` - Get current motor speed and servo angle
- `GET /api/icons` - Get list of available icons
- `GET /api/test` - Test CORS connectivity

## 🚀 Setup Instructions

### 1. Install MicroPython on Raspberry Pi Pico

1. Download the latest MicroPython firmware from [micropython.org](https://micropython.org/download/RPI_PICO/)
2. Hold BOOTSEL button while connecting Pico to computer
3. Drag and drop the `.uf2` file to the RPI-RP2 drive

### 2. Create secrets.py

Copy the template file and add your WiFi credentials:

```bash
# Copy the template
cp secrets-template.py secrets.py

# Edit secrets.py with your credentials
# Replace YOUR_WIFI_SSID with your network name
# Replace YOUR_WIFI_PASSWORD with your WiFi password
```

Or create `secrets.py` manually in the root directory:

```python
ssid = "YOUR_WIFI_SSID"
password = "YOUR_WIFI_PASSWORD"
```

**Important**: `secrets.py` is in `.gitignore` and will not be committed to git. The `secrets-template.py` file is a safe template you can commit.

### 3. Upload Files to Pico

Upload all files from this branch to your Raspberry Pi Pico:

- Use Thonny IDE, rshell, ampy, or your preferred tool
- Make sure to preserve the directory structure
- Upload all files including the `microdot/` and `sensors/` directories

### 4. Required Libraries

The following libraries are included in this repository:
- `microdot` - Lightweight web framework (included)
- `ssd1306` - OLED display driver (built into MicroPython)
- `vl53l0x_mp` - VL53L0X ToF sensor driver (included)

### 5. Run the Application

1. Connect to the Pico via serial console
2. Run `main.py` or set it to auto-run on boot
3. The Pico will:
   - Connect to WiFi
   - Initialize all sensors
   - Start the HTTP server on port 5000
   - Display the IP address on the OLED

## 🔧 Configuration

### WiFi Settings
Edit `wifi.py` to customize WiFi connection behavior.

### Sensor Settings
Each sensor module has configuration constants at the top:
- `sensors/accelerometer.py` - I2C pins, address, scales
- `sensors/dual_tof.py` - I2C pins, sensor spacing
- `sensors/hcsr04.py` - Trigger/echo pins, max distance

### Motor & Servo
- `motor.py` - PWM frequency, duty cycle ranges
- `servo.py` - PWM frequency, pulse width ranges

## 🧪 Testing

### Test Individual Components

You can test components individually by running their self-test:

```python
# Test accelerometer
import sensors.accelerometer
import uasyncio
uasyncio.run(sensors.accelerometer._self_test())

# Test dual ToF sensors
import sensors.dual_tof
import uasyncio
uasyncio.run(sensors.dual_tof._self_test())

# Test ultrasonic sensor
import sensors.hcsr04
import uasyncio
uasyncio.run(sensors.hcsr04._self_test())
```

### Test API Endpoints

Once the server is running, test from your computer:

```bash
# Get status
curl http://<PICO_IP>:5000/api/status

# Set motor speed to 50%
curl http://<PICO_IP>:5000/api/motor/50

# Center servo
curl http://<PICO_IP>:5000/api/servo/90

# Get sensor data
curl http://<PICO_IP>:5000/api/accelerometer
curl http://<PICO_IP>:5000/api/tof
curl http://<PICO_IP>:5000/api/ultrasonic
```

## 📊 Sensor Details

### MPU-6050 Accelerometer/Gyroscope
- **Update Rate**: 10 Hz (100ms intervals)
- **Range**: ±2g (acceleration), ±250°/s (gyroscope)
- **Provides**: 3-axis acceleration, 3-axis gyroscope, pitch/roll angles, orientation classification

### Dual VL53L0X ToF Sensors
- **Update Rate**: 5 Hz (200ms intervals)
- **Range**: 30-1200mm (typical), up to 2000mm
- **Provides**: Left/right distances, wall angle calculation, orientation relative to wall

### HC-SR04 Ultrasonic Sensor
- **Update Rate**: 5 Hz (200ms intervals)
- **Range**: 2-400 cm
- **Provides**: Rear obstacle detection distance

## 🎯 Production vs Development

This branch (`production-pico`) contains **only** the files needed to run on the Raspberry Pi Pico:

**Removed from production:**
- Test files (`test_*.py`, `*_test.py`)
- Documentation files (sensor-specific READMEs)
- Client applications (`client/` directory)
- Image assets (`images/` directory)
- Development tools (`screen/`, `utemplate/`, `source/`)
- Utility scripts (`image_to_icon.py`, etc.)

**Kept for production:**
- Core application files
- Sensor drivers and monitors
- Web server framework (microdot)
- Display management
- Motor and servo control

## 🛠️ Troubleshooting

### WiFi Connection Issues
- Check `secrets.py` credentials
- Ensure 2.4GHz WiFi (Pico W doesn't support 5GHz)
- Check WiFi signal strength

### Sensor Not Detected
- Verify I2C connections (SDA/SCL)
- Check power supply (3.3V for I2C devices)
- Run I2C scan to detect devices
- Check I2C pull-up resistors (usually built-in)

### Display Not Working
- Verify I2C1 connections (GP18/GP19)
- Check display address (usually 0x3C)
- Verify 128x32 resolution

### Motor/Servo Issues
- Check power supply (motors need sufficient current)
- Verify PWM pin connections
- Check STBY pin (must be HIGH for motor operation)

## 📝 Notes

- All sensor monitors run asynchronously using `uasyncio`
- Sensor states are cached and updated in background tasks
- API endpoints return cached values for fast response times
- CORS is enabled for all endpoints
- The onboard LED blinks during API requests
- Display shows idle timeout after 5 seconds of no commands

## 🔗 Git Branches

- `main` - Development branch with test files and utilities
- `production-pico` - This branch - production code only

To switch branches:
```bash
git checkout main              # Switch to development
git checkout production-pico   # Switch to production
```

## 📄 License

This project is for educational and personal use.

---

**Built for Raspberry Pi Pico W with MicroPython**
