# PiCar Python Client

## Overview

The PiCar Python Client provides a comprehensive interface to control your PiCar robot over WiFi. It includes automatic light control based on movement direction and full access to all onboard sensors.

## Features

### ✨ New Features in This Update

- **🚨 Automatic Lights Control**: Front lights turn on when moving forward, back lights when reversing
- **💡 Manual Lights Control**: Full control over front and back lights independently
- **📡 Comprehensive Sensor Access**: Query all sensors (accelerometer, ToF, ultrasonic)
- **📊 Formatted Sensor Display**: Human-readable sensor output with visual indicators
- **🎮 Enhanced Interactive Terminal**: Extended keyboard controls for all features

## Hardware Overview

### Sensors Available

1. **MPU-6050 Accelerometer/Gyroscope** (Front)
   - 6-axis IMU providing tilt and orientation data
   - I2C address: 0x68
   - Pins: SDA=GP8, SCL=GP9
   - Update rate: 10 Hz
   - Use cases: Tilt detection, stability monitoring, terrain analysis

2. **Dual VL53L0X Time-of-Flight Sensors** (Front Left & Right)
   - Laser distance sensors (3-200cm range)
   - Separate I2C buses for parallel operation
   - Left: SDA=GP6, SCL=GP7
   - Right: SDA=GP20, SCL=GP21
   - Update rate: 5 Hz
   - Use cases: Wall following, obstacle detection, angle calculation

3. **HC-SR04 Ultrasonic Sensor** (Rear)
   - Ultrasonic distance sensor (2-400cm range)
   - Pins: TRIG=GP14, ECHO=GP15
   - Update rate: 5 Hz
   - Use cases: Reverse parking, rear collision avoidance

### Lights

- **Front Light**: GP5 (turns on when moving forward)
- **Back Light**: GP2 (turns on when moving backward)
- **Auto Mode**: Default enabled - lights follow movement direction

## Installation

```bash
# Install required package
pip install requests

# Verify connection
python client/picar_client.py
```

## Quick Start

### Basic Usage

```python
from client.picar_client import PicarClient

# Connect to your PiCar (update IP address)
client = PicarClient(base_url="http://192.168.1.100:5000")

# Move forward (front lights turn on automatically)
client.set_motor(75)

# Stop (lights turn off automatically)
client.stop()

# Move backward (back lights turn on automatically)
client.set_motor(-75)

# Centre steering
client.centre()
```

### Interactive Terminal Control

Run the interactive terminal:

```bash
python client/picar_client.py
```

## PicarClient API Reference

### Movement Control

#### `set_motor(speed: int) -> dict`
Set motor speed with automatic light control.

```python
client.set_motor(75)   # Forward at 75% speed (front lights ON)
client.set_motor(-50)  # Reverse at 50% speed (back lights ON)
client.set_motor(0)    # Stop (lights OFF)
```

- **Range**: -100 (full reverse) to 100 (full forward)
- **Auto lights**: Enabled by default (set `client.auto_lights = False` to disable)

#### `set_servo(angle: int) -> dict`
Control steering servo.

```python
client.set_servo(45)   # Hard left
client.set_servo(90)   # Centre (straight)
client.set_servo(135)  # Hard right
```

- **Range**: 0 to 180 degrees
- **Centre**: 90 degrees

#### `stop() -> dict`
Emergency stop - immediately stops motor and turns off lights.

```python
client.stop()
```

#### `centre() -> dict`
Centre the steering servo.

```python
client.centre()
```

### Lights Control

#### `get_lights() -> dict`
Get current light status.

```python
status = client.get_lights()
print(f"Front: {status['front']}, Back: {status['back']}")
print(f"Status: {status['status']}")  # 'off', 'front', 'back', or 'both'
```

#### `set_lights(status: str) -> dict`
Control lights manually.

```python
client.set_lights("front")  # Front lights only
client.set_lights("back")   # Back lights only
client.set_lights("both")   # Both lights on
client.set_lights("off")    # All lights off
```

#### Convenience Methods

```python
client.lights_front()  # Turn on front lights
client.lights_back()   # Turn on back lights
client.lights_both()   # Turn on both lights
client.lights_off()    # Turn off all lights
```

#### Auto Lights Mode

```python
# Enable automatic light control (default)
client.auto_lights = True

# Disable automatic light control
client.auto_lights = False

# When auto_lights is True:
client.set_motor(50)   # Automatically turns on front lights
client.set_motor(-50)  # Automatically switches to back lights
client.set_motor(0)    # Automatically turns off all lights
```

### Sensor Access

#### `get_accelerometer() -> dict`
Get MPU-6050 accelerometer/gyroscope data.

```python
data = client.get_accelerometer()

if data['success']:
    # Tilt angles
    pitch = data['tilt']['pitch']  # Forward/backward tilt (-90 to +90)
    roll = data['tilt']['roll']    # Left/right tilt (-90 to +90)
    
    # Orientation
    orientation = data['orientation']  # 'level', 'forward', 'back', 'left', 'right'
    
    # Raw acceleration (in g-force)
    accel = data['acceleration']  # {'x': 0.0, 'y': 0.0, 'z': 1.0}
    
    # Gyroscope (degrees/second)
    gyro = data['gyroscope']  # {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    print(f"Tilt: Pitch={pitch:.1f}° Roll={roll:.1f}° [{orientation}]")
```

**Use Cases:**
- Detect when climbing slopes
- Monitor stability (prevent tipping)
- Collision detection (sudden impacts)
- Terrain analysis (vibration patterns)

#### `get_tof() -> dict`
Get dual VL53L0X Time-of-Flight sensor data (front sensors).

```python
data = client.get_tof()

if data['success']:
    # Distance measurements
    left_cm = data['left_distance_cm']   # Left sensor distance
    right_cm = data['right_distance_cm']  # Right sensor distance
    
    # Angle calculation (when both sensors available)
    if data.get('angle'):
        angle_deg = data['angle']['angle_degrees']  # +/- angle
        orientation = data['angle']['orientation']  # 'straight', 'angled_left', 'angled_right'
        wall_distance = data['angle']['wall_distance_cm']  # Perpendicular distance
        
        print(f"Wall angle: {angle_deg:+.1f}° ({orientation})")
```

**Use Cases:**
- Wall following navigation
- Obstacle detection (20-200cm range)
- Corner detection
- Corridor centering

**Angle Interpretation:**
- Positive angle: Wall angled to the right (left sensor closer)
- Negative angle: Wall angled to the left (right sensor closer)
- ~0°: Wall is straight/perpendicular

#### `get_ultrasonic() -> dict`
Get HC-SR04 ultrasonic sensor data (rear sensor).

```python
data = client.get_ultrasonic()

if data['success']:
    if data['in_range']:
        distance = data['distance_cm']
        print(f"Rear obstacle at {distance:.1f}cm")
        
        if distance < 30:
            print("WARNING: Too close!")
    else:
        print("All clear behind")
```

**Use Cases:**
- Reverse parking assistance
- Rear collision avoidance
- Parking space detection

#### `get_all_sensors() -> dict`
Query all sensors in one call.

```python
sensors = client.get_all_sensors()

accel = sensors['accelerometer']
tof = sensors['tof']
ultrasonic = sensors['ultrasonic']

# Each sensor dict has 'success' or 'available' flag
if accel.get('success'):
    print(f"Tilt: {accel['tilt']['pitch']:.1f}°")

if tof.get('success'):
    print(f"Front: L={tof['left_distance_cm']}cm R={tof['right_distance_cm']}cm")

if ultrasonic.get('success') and ultrasonic.get('in_range'):
    print(f"Rear: {ultrasonic['distance_cm']:.1f}cm")
```

### Display Control

#### `send_text(text: str) -> dict`
Display message on OLED screen.

```python
client.send_text("Hello PiCar!")
```

#### `clear_display() -> dict`
Clear the OLED display.

```python
client.clear_display()
```

### Status

#### `status() -> dict`
Get current motor speed and servo angle.

```python
status = client.status()
print(f"Motor: {status['motor_speed']}, Servo: {status['servo_angle']}°")
```

## Interactive Terminal Commands

When you run `python client/picar_client.py`, you get an interactive terminal with these commands:

### Movement
- **W** - Move forward (75% speed, front lights ON)
- **S** - Move backward (75% speed, back lights ON)
- **A** - Steer left (45°)
- **D** - Steer right (135°)
- **C** - Centre steering (90°)
- **SPACE** - Stop (lights OFF)

### Lights
- **F** - Front lights ON
- **B** - Back lights ON
- **L** - Both lights ON
- **O** - Lights OFF
- **T** - Toggle auto lights mode

### Sensors
- **1** - Accelerometer (tilt, orientation)
- **2** - ToF sensors (front distances & angle)
- **3** - Ultrasonic (rear distance)
- **4** - All sensors
- **5** - Lights status

### Other
- **?** - Status (motor, servo)
- **Q** - Quit

## Example Use Cases

### Wall Following Robot

```python
import time
from client.picar_client import PicarClient

client = PicarClient()

# Simple wall-following algorithm
while True:
    # Get front sensor data
    tof = client.get_tof()
    
    if tof.get('angle'):
        angle = tof['angle']['angle_degrees']
        wall_dist = tof['angle']['wall_distance_cm']
        
        # Too close to wall - turn away
        if wall_dist < 30:
            if angle > 0:  # Wall on right
                client.set_servo(45)  # Turn left
            else:  # Wall on left
                client.set_servo(135)  # Turn right
        
        # Wall angled - correct steering
        elif abs(angle) > 5:
            if angle > 5:  # Wall angled right
                client.set_servo(90 - int(angle * 2))  # Turn left
            elif angle < -5:  # Wall angled left
                client.set_servo(90 + int(abs(angle) * 2))  # Turn right
        
        # Wall straight - drive parallel
        else:
            client.set_servo(90)
        
        # Move forward
        client.set_motor(50)
    
    time.sleep(0.2)
```

### Reverse Parking Assistant

```python
from client.picar_client import PicarClient
import time

client = PicarClient()

# Reverse with distance monitoring
client.set_motor(-40)  # Start reversing (back lights ON)

while True:
    rear = client.get_ultrasonic()
    
    if rear['in_range']:
        distance = rear['distance_cm']
        
        if distance < 10:
            print("STOP! Too close!")
            client.stop()
            break
        elif distance < 20:
            print(f"Slow down: {distance:.1f}cm")
            client.set_motor(-20)  # Slow reverse
        elif distance < 50:
            print(f"Reversing: {distance:.1f}cm")
            client.set_motor(-40)  # Normal reverse
    
    time.sleep(0.2)
```

### Stability Monitor

```python
from client.picar_client import PicarClient
import time

client = PicarClient()

while True:
    accel = client.get_accelerometer()
    
    if accel['success']:
        pitch = accel['tilt']['pitch']
        roll = accel['tilt']['roll']
        
        # Detect dangerous tilt
        if abs(pitch) > 30 or abs(roll) > 30:
            print(f"WARNING: Steep tilt detected! P:{pitch:.1f}° R:{roll:.1f}°")
            client.stop()
            break
        
        # Detect slope
        if abs(pitch) > 15:
            print(f"On a slope: {pitch:.1f}°")
            # Reduce speed on slopes
            client.set_motor(30)
        else:
            # Normal speed on level ground
            client.set_motor(60)
    
    time.sleep(0.5)
```

## Troubleshooting

### Cannot Connect
```
✗ Could not connect to http://192.168.x.x:5000. Is the Pico running?
```

**Solutions:**
1. Update IP address in `PICO_IP` variable at top of file
2. Verify PiCar is powered on and connected to WiFi
3. Check firewall settings
4. Try pinging the IP: `ping 192.168.x.x`

### Sensors Return Not Available

**Accelerometer not available:**
- Check I2C connections (SDA=GP8, SCL=GP9)
- Verify MPU-6050 is powered (3.3V)
- Run I2C scan on Pico: `from sensors import i2c_scan; i2c_scan.main()`

**ToF not available:**
- Check I2C connections for both sensors
- Verify VL53L0X sensors are powered (3.3V, NOT 5V!)
- Ensure sensors are on separate I2C buses

**Ultrasonic not available:**
- Check GPIO connections (TRIG=GP14, ECHO=GP15)
- Verify HC-SR04 is powered (5V required!)
- Ensure clear view (nothing blocking sensor)

### Lights Not Working

**Manual control works but auto doesn't:**
- Check `client.auto_lights` is set to `True`
- Verify lights API endpoint is available

**Neither manual nor auto works:**
- Check light wiring (Front=GP5, Back=GP2)
- Test lights API: `curl http://192.168.x.x:5000/api/lights/both`
- Verify `lights.py` is imported in `main.py`

## API Endpoints Reference

The client uses these HTTP endpoints on the PiCar:

- `GET /api/status` - Get motor speed and servo angle
- `GET /api/motor/<speed>` - Set motor speed (-100 to 100)
- `GET /api/servo/<angle>` - Set servo angle (0 to 180)
- `POST /api/text` - Display text on OLED
- `GET /api/lights` - Get light status
- `GET /api/lights/<status>` - Control lights (front/back/both/off)
- `GET /api/accelerometer` - Get MPU-6050 data
- `GET /api/tof` - Get dual VL53L0X data
- `GET /api/ultrasonic` - Get HC-SR04 data

## Configuration

### Change IP Address

Edit the `PICO_IP` constant at the top of `picar_client.py`:

```python
PICO_IP = "192.168.1.100"  # Your PiCar's IP address
BASE_URL = f"http://{PICO_IP}:5000"
```

### Adjust Motor Speeds

Edit movement command speeds in the `main()` function:

```python
"w": ("Forward", lambda: client.set_motor(75)),   # Change 75 to your preference
"s": ("Reverse", lambda: client.set_motor(-75)),  # Change -75 to your preference
```

### Change Default Auto Lights Behavior

In `PicarClient.__init__()`:

```python
self.auto_lights = False  # Change to False to disable by default
```

## Performance

- **API Response Time**: < 50ms typical
- **Sensor Update Rate**: 5-10 Hz (per sensor)
- **Network Latency**: Depends on WiFi quality
- **Terminal Input**: Immediate (raw mode)

## Safety Notes

⚠️ **Important Safety Considerations:**

1. **Test in open space first** - Ensure sufficient room for movement
2. **Monitor battery level** - Low battery affects motor performance
3. **Watch for obstacles** - Sensors have blind spots
4. **Emergency stop ready** - Keep SPACE key or `client.stop()` ready
5. **Tilt monitoring** - Accelerometer detects dangerous tilts
6. **Rear awareness** - Only ultrasonic sensor monitors rear

## Further Reading

For detailed sensor information, see:
- `ACCELEROMETER_README.md` - MPU-6050 details and calibration
- `DUAL_TOF_README.md` - VL53L0X angle calculation and wall following
- `ULTRASONIC_README.md` - HC-SR04 reverse parking guide

## License

Part of the PiCar project. See main repository for license information.

## Contributing

Improvements welcome! Key areas:
- Additional sensor fusion algorithms
- Enhanced autonomous navigation
- Web-based control interface
- Data logging and visualization
