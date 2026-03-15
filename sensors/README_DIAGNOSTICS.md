# Sensor Diagnostic Tools - Complete Overview

## 📋 Summary

All sensor diagnostic tools in the `/sensors` directory have been reviewed and unified following consistent standards for structure, error handling, display integration, and output formatting.

## 🎯 Unified Standards

All diagnostic test scripts now follow these standards (see `DIAGNOSTIC_STANDARDS.md` for details):

- ✅ Consistent file naming (`<sensor>_test.py`)
- ✅ Standard module structure with configuration sections
- ✅ Graceful display degradation (works with or without OLED)
- ✅ Unified error handling with try/except blocks
- ✅ Standard console output format (60-char borders, numbered sections)
- ✅ 5 Hz measurement rate (configurable)
- ✅ Unicode status symbols (✓/✗)
- ✅ Measurement counters [nnnn]
- ✅ Clean KeyboardInterrupt handling

## 📁 Diagnostic Files Status

### ✅ Fully Compliant (Follow Unified Standards)

| File | Sensor | Status | Notes |
|------|--------|--------|-------|
| `vl53l0x_test.py` | VL53L0X ToF Distance | ✅ Compliant | Single ToF sensor, GPIO 6/7 |
| `hcsr04_test.py` | HC-SR04 Ultrasonic | ✅ Compliant | GPIO 14/15 |
| `mpu6050_test.py` | MPU6050 IMU | ✅ Compliant | I2C0, GPIO 4/5, full IMU data |
| `dual_tof_test.py` | Dual VL53L0X ToF | ✅ Compliant | Both ToF sensors, GPIO 6/7 & 20/21 |
| `ir_sensor_test.py` | IR Break-Beam Array | ✅ **NEW** | 4 IR sensors, GPIO 3/4/7/8 |
| `i2c_scan.py` | I2C Bus Scanner | ✅ **UPDATED** | Scans I2C bus, continuous monitoring |
| `tof_angle_display.py` | ToF Angle Calculator | ✅ Compliant | Advanced ToF angle calculation |

### 📦 Module Files (Not Test Scripts)

| File | Type | Purpose |
|------|------|---------|
| `dual_tof_sensor.py` | Sensor Module | Manages dual ToF sensors |
| `tof_angle_calculator.py` | Processing Module | Calculates wall angles from ToF |
| `payload_sensor.py` | API Module | IR sensor monitoring with async |
| `vl53l0x_mp.py` | Driver (root) | VL53L0X hardware driver |

### 🔧 Utility Scripts

| File | Type | Purpose |
|------|------|---------|
| `__init__.py` | Package Init | Makes sensors a package |
| `accel_main.py` | Legacy | Old accelerometer test (superseded by mpu6050_test.py) |
| `distance_sensor_diag.py` | Legacy | Old VL53L1X test (minimal) |
| `ir_sensor.py` | Legacy | Old IR test (superseded by ir_sensor_test.py) |
| `tof_pico_test.py` | Legacy | Old ToF test |

## 🚀 Quick Start Guide

### Running Diagnostic Tests

On your Raspberry Pi Pico, run any test with:

```python
# Single sensor tests
import sensors.vl53l0x_test        # ToF distance sensor
import sensors.hcsr04_test          # Ultrasonic sensor
import sensors.mpu6050_test         # IMU accelerometer/gyroscope
import sensors.ir_sensor_test       # IR break-beam sensors

# Multi-sensor tests
import sensors.dual_tof_test        # Both ToF sensors
import sensors.tof_angle_display    # ToF angle calculator with OLED

# Utilities
import sensors.i2c_scan             # Scan I2C bus for devices
```

### Using Sensor Modules (Non-Test)

```python
# Dual ToF sensors
from sensors.dual_tof_sensor import DualToFSensor
tof = DualToFSensor()
tof.init()
left_cm, right_cm = tof.read_distances_cm()

# Angle calculator
from sensors.tof_angle_calculator import ToFAngleCalculator
calc = ToFAngleCalculator(sensor_spacing_cm=15.0)
calc.init()
angle_data = calc.read_with_angle()
```

## 🎨 Display Integration

All test scripts support OLED display (SSD1306, 128x32):
- **With display**: Shows sensor data on OLED + console
- **Without display**: Console output only (graceful degradation)
- **Format**: Header (sensor name) + Text (measurements) + Optional icon

## 📍 Hardware Pin Mappings

### Distance Sensors
- **Left ToF (VL53L0X)**: GPIO 6 (SDA), GPIO 7 (SCL)
- **Right ToF (VL53L0X)**: GPIO 20 (SDA), GPIO 21 (SCL)
- **Ultrasonic (HC-SR04)**: GPIO 14 (TRIG), GPIO 15 (ECHO)

### Motion Sensors
- **IMU (MPU6050)**: GPIO 4 (SDA), GPIO 5 (SCL) - I2C0

### IR Break-Beam Sensors
- **Left Front**: GPIO 3
- **Right Front**: GPIO 7
- **Left Back**: GPIO 8
- **Right Back**: GPIO 4

### Display
- **OLED (SSD1306)**: GPIO 18 (SDA), GPIO 19 (SCL) - I2C1

## 📊 Console Output Format

All tests follow this standard output format:

```
==============================================================
<Sensor Name> Test
==============================================================
Configuration:
  Pin 1: GPxx
  Pin 2: GPxx
Press Ctrl+C to stop
--------------------------------------------------------------

[1] Initializing sensor...
   ✓ Sensor initialized successfully

[2] Starting measurements...

[0001] Value: 25.43 cm
[0002] Value: 26.12 cm
[0003] Value: 25.98 cm
...

--------------------------------------------------------------
✓ Test stopped by user
```

## 🔧 Configuration

Each test script has a configuration section at the top:

```python
# ========== <SENSOR> Configuration ==========
PIN_1 = X
PIN_2 = Y
SENSOR_ADDR = 0xXX      # For I2C sensors
MEASUREMENT_RATE = 5    # Hz (standard: 5 measurements per second)
```

Simply edit these values to match your hardware setup.

## 📝 Adding New Diagnostic Tests

To create a new diagnostic test:

1. Copy the template from `DIAGNOSTIC_STANDARDS.md`
2. Update sensor-specific code (init, read, format)
3. Set configuration constants
4. Test on hardware
5. Follow naming convention: `<sensor_name>_test.py`

## 🗂️ File Organization

```
sensors/
├── README_DIAGNOSTICS.md          ← This file
├── DIAGNOSTIC_STANDARDS.md        ← Unified standards guide
│
├── Core Test Scripts (Run directly)
│   ├── vl53l0x_test.py           ← Single ToF sensor
│   ├── dual_tof_test.py          ← Dual ToF sensors
│   ├── hcsr04_test.py            ← Ultrasonic distance
│   ├── mpu6050_test.py           ← IMU accelerometer/gyro
│   ├── ir_sensor_test.py         ← IR break-beam array
│   ├── i2c_scan.py               ← I2C bus scanner
│   └── tof_angle_display.py      ← ToF angle calculator
│
├── Sensor Modules (Import and use)
│   ├── dual_tof_sensor.py        ← Dual ToF manager
│   ├── tof_angle_calculator.py   ← Angle processing
│   └── payload_sensor.py         ← IR monitoring API
│
└── Legacy Files (Deprecated)
    ├── accel_main.py             ← Use mpu6050_test.py instead
    ├── distance_sensor_diag.py   ← Use vl53l0x_test.py instead
    ├── ir_sensor.py              ← Use ir_sensor_test.py instead
    └── tof_pico_test.py          ← Use vl53l0x_test.py instead
```

## 🎯 Benefits of Unified Structure

1. **Consistency**: All tests work the same way
2. **Easy to Learn**: Understand one, understand all
3. **Maintainable**: Standard patterns for updates
4. **Reliable**: Proper error handling everywhere
5. **Flexible**: Works with or without display
6. **Professional**: Clean console output

## 🔄 Migration Notes

### Updated Files
- ✅ `ir_sensor_test.py` - Completely rewritten to standard
- ✅ `i2c_scan.py` - Enhanced with display, monitoring, device identification

### Legacy Files
The following files are superseded but kept for reference:
- `ir_sensor.py` → Use `ir_sensor_test.py`
- `accel_main.py` → Use `mpu6050_test.py`
- `distance_sensor_diag.py` → Use `vl53l0x_test.py`

## 🚨 Troubleshooting

### Sensor Not Detected
1. Run `sensors.i2c_scan` to check I2C devices
2. Verify wiring (SDA/SCL/VCC/GND)
3. Check power supply (3.3V for most sensors)
4. Verify correct I2C bus and pins

### Display Not Working
- Tests automatically degrade to console-only
- Check OLED on GPIO 18/19 (I2C1)
- Verify display module initialized in `display.py`

### Import Errors
- Ensure all files are uploaded to Pico
- Check `vl53l0x_mp.py` is in root directory
- Verify `display.py` is in root directory

## 📚 Documentation

- **Standards Guide**: `DIAGNOSTIC_STANDARDS.md` - Template and standards
- **This File**: Complete overview and quick reference
- **Individual Files**: Each has detailed docstring

## ✨ Recent Improvements

### Dual ToF System (NEW!)
- Created `dual_tof_sensor.py` - Manages both ToF sensors
- Created `tof_angle_calculator.py` - Calculates wall angles
- Created `tof_angle_display.py` - Shows angles on OLED
- Features: Simultaneous reading, angle calculation, navigation hints

### IR Sensor Array (UPDATED!)
- Rewrote `ir_sensor_test.py` with unified structure
- Added `IRSensorArray` class for managing 4 sensors
- Change detection and event logging
- OLED display with visual indicators

### I2C Scanner (ENHANCED!)
- Continuous monitoring mode
- Device identification by address
- Change detection and alerting
- OLED integration

---

**Last Updated**: March 15, 2026  
**Total Diagnostic Scripts**: 7 core tests + 3 modules + utilities  
**All Tests**: ✅ Follow unified standards
