# Accelerometer Component for PiCar

## Overview

The accelerometer component provides real-time access to MPU-6050 sensor data through the PiCar API. It continuously monitors the sensor in the background and makes the data available via an HTTP endpoint.

## Hardware

- **Sensor**: MPU-6050 6-axis IMU (Accelerometer + Gyroscope)
- **Communication**: I2C (address 0x68)
- **Pins**: 
  - SDA: GP8
  - SCL: GP9
  - I2C Bus: I2C0
  - Frequency: 400 kHz

## Files Created/Modified

### New Files
1. **`sensors/accelerometer.py`** - Main accelerometer component
   - MPU6050 class for sensor communication
   - Async monitoring task
   - Cached state management
   - Self-test capability

2. **`test_accelerometer_api.py`** - API test script
   - Single reading test
   - Continuous reading test
   - Connection diagnostics

### Modified Files
1. **`main.py`** - Added accelerometer integration
   - Import: `from sensors import accelerometer`
   - Endpoint: `/api/accelerometer`
   - Task: `asyncio.create_task(accelerometer.monitor())`

## API Endpoint

### GET `/api/accelerometer`

Returns current accelerometer/gyroscope state.

#### Success Response (Sensor Available)
```json
{
  "success": true,
  "acceleration": {
    "x": 0.012,
    "y": 0.023,
    "z": 1.001
  },
  "gyroscope": {
    "x": 0.5,
    "y": -0.3,
    "z": 0.1
  },
  "tilt": {
    "pitch": 1.2,
    "roll": -0.8
  },
  "orientation": "level",
  "timestamp": 1234567890,
  "message": "P:+1° R:-1° level"
}
```

#### Error Response (Sensor Not Available)
```json
{
  "success": false,
  "message": "MPU-6050 sensor not available",
  "available": false
}
```

## Data Descriptions

### Acceleration (in g-force)
- **x**: Forward/backward tilt (positive = forward)
- **y**: Left/right tilt (positive = right)
- **z**: Up/down (typically ~1.0g when level)

### Gyroscope (in degrees/second)
- **x**: Rotation around X-axis
- **y**: Rotation around Y-axis
- **z**: Rotation around Z-axis

### Tilt Angles (in degrees)
- **pitch**: Forward/backward tilt (-90° to +90°)
- **roll**: Left/right tilt (-90° to +90°)

### Orientation
String indicating the robot's orientation:
- `"level"` - Robot is level (within ±15° threshold)
- `"forward"` - Tilted forward
- `"back"` - Tilted backward
- `"left"` - Tilted left
- `"right"` - Tilted right
- `"forward+left"` - Combined tilt
- `"error"` - Sensor read error

## Usage Examples

### 1. Test the Sensor Directly (on Pico)
```bash
# From Pico command line or Thonny
import asyncio
from sensors import accelerometer
asyncio.run(accelerometer._self_test())
```

### 2. Query via API (from your computer)
```bash
# Using curl
curl http://192.168.1.100:5000/api/accelerometer

# Using Python
python test_accelerometer_api.py  # (update IP address first)
```

### 3. Use in Client Code
```python
import requests

response = requests.get('http://192.168.1.100:5000/api/accelerometer')
data = response.json()

if data['success']:
    print(f"Tilt: Pitch={data['tilt']['pitch']}° Roll={data['tilt']['roll']}°")
    print(f"Orientation: {data['orientation']}")
```

### 4. JavaScript/Web Client
```javascript
fetch('http://192.168.1.100:5000/api/accelerometer')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log(`Pitch: ${data.tilt.pitch}°`);
      console.log(`Roll: ${data.tilt.roll}°`);
      console.log(`Orientation: ${data.orientation}`);
    }
  });
```

## Architecture

The accelerometer component follows the same pattern as the existing `payload_sensor` module:

1. **Background Monitoring**: Async task continuously reads sensor at 10 Hz
2. **Cached State**: Latest readings stored in `_state` dictionary
3. **Non-blocking**: API queries return cached data immediately
4. **Graceful Degradation**: Handles sensor errors without crashing

### Component Flow
```
main.py startup
    ↓
accelerometer.monitor() started as async task
    ↓
I2C initialized → MPU6050 sensor initialized
    ↓
Loop: Read sensor every 100ms
    ↓
Update _state dictionary
    ↓
API endpoint reads _state via get_state()
    ↓
Return JSON to client
```

## Troubleshooting

### Sensor Not Detected
**Symptom**: API returns `"available": false`

**Solutions**:
1. Check I2C connections (SDA=GP8, SCL=GP9)
2. Verify MPU-6050 power supply (3.3V)
3. Run I2C scan: `from sensors import i2c_scan; i2c_scan.main()`
4. Check for I2C address conflicts (should be 0x68)

### Reading Errors
**Symptom**: Console shows "Accelerometer monitor: read error"

**Solutions**:
1. Check for loose connections
2. Verify I2C pull-up resistors (usually built-in on MPU-6050 modules)
3. Reduce I2C frequency if errors persist (edit `I2C_FREQ` in accelerometer.py)

### Incorrect Readings
**Symptom**: Values seem wrong or unstable

**Solutions**:
1. MPU-6050 needs calibration when horizontal
2. Check sensor mounting orientation
3. Verify sensor is not damaged
4. Run standalone test: `python sensors/mpu6050_test.py`

## Performance

- **Update Rate**: 10 Hz (100ms interval)
- **API Response Time**: < 5ms (cached data)
- **Memory Usage**: ~2KB for module + state
- **CPU Impact**: Minimal (async I/O)

## Integration with Autonomous Navigation

The accelerometer data can be used for:
- **Tilt Detection**: Detect when climbing slopes
- **Stability Monitoring**: Prevent tipping over
- **Inertial Navigation**: Track movement between sensor readings
- **Collision Detection**: Detect sudden impacts
- **Terrain Analysis**: Classify surface types by vibration patterns

Example use case:
```python
# In autonomous navigation code
response = requests.get('http://picar:5000/api/accelerometer')
data = response.json()

if abs(data['tilt']['pitch']) > 30:
    print("WARNING: Steep slope detected!")
    # Reduce speed or stop

if data['orientation'] != 'level':
    print(f"Robot is tilted: {data['orientation']}")
    # Adjust navigation strategy
```

## Future Enhancements

Possible additions:
1. **Calibration API**: Zero-point calibration endpoint
2. **Threshold Alerts**: WebSocket notifications for extreme tilts
3. **Data Logging**: Store acceleration history for analysis
4. **Complementary Filter**: Combine accel + gyro for better orientation
5. **Gesture Detection**: Recognize tap, shake, freefall patterns

## References

- MPU-6050 Datasheet: https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Datasheet1.pdf
- I2C Protocol: https://www.nxp.com/docs/en/user-guide/UM10204.pdf
- MicroPython I2C: https://docs.micropython.org/en/latest/library/machine.I2C.html
