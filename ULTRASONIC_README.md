# HC-SR04 Ultrasonic Sensor Component for PiCar

## Overview

The HC-SR04 ultrasonic sensor component provides real-time rear obstacle detection for the PiCar. It continuously monitors the sensor in the background and makes distance measurements available via an HTTP endpoint. Mounted on the back of the car, it's perfect for reverse parking assistance and rear collision avoidance.

## Hardware

- **Sensor**: HC-SR04 Ultrasonic Distance Sensor
- **Technology**: Ultrasonic ranging (40 kHz)
- **Range**: 2cm - 400cm (typical)
- **Accuracy**: ±3mm
- **Beam Angle**: ~15° cone

### Wiring

**HC-SR04 Sensor (Rear mounted):**
- VCC: 5V (HC-SR04 requires 5V, not 3.3V!)
- TRIG: GP14
- ECHO: GP15
- GND: GND

**Important**: The HC-SR04 requires 5V power. The Echo pin is 5V tolerant on most Pico boards, but verify your board's specifications.

## Files Created/Modified

### New Files
1. **`sensors/hcsr04.py`** - Main HC-SR04 component
   - HCSR04Sensor class for ultrasonic ranging
   - Async monitoring task
   - Cached state management
   - Self-test capability

2. **`test_ultrasonic_api.py`** - API test script
   - Single reading test
   - Continuous reading test
   - Connection diagnostics
   - Proximity warnings

### Modified Files
1. **`main.py`** - Added HC-SR04 integration
   - Import: `from sensors import hcsr04`
   - Endpoint: `/api/ultrasonic`
   - Task: `asyncio.create_task(hcsr04.monitor())`

## API Endpoint

### GET `/api/ultrasonic`

Returns current rear ultrasonic sensor state.

#### Success Response (Obstacle Detected)
```json
{
  "success": true,
  "distance_cm": 45.3,
  "in_range": true,
  "timestamp": 1234567890,
  "message": "Rear: 45.3cm"
}
```

#### Success Response (No Obstacle)
```json
{
  "success": true,
  "distance_cm": null,
  "in_range": false,
  "timestamp": 1234567890,
  "message": "Rear: No obstacle detected"
}
```

#### Error Response (Sensor Not Available)
```json
{
  "success": false,
  "message": "HC-SR04 ultrasonic sensor not available",
  "available": false
}
```

## Data Descriptions

### Distance Measurement
- **distance_cm**: Distance to obstacle in centimeters
  - Range: 2-400 cm
  - null if no obstacle detected or out of range
  - Resolution: 0.1 cm

### Status Flags
- **in_range**: Boolean indicating if obstacle detected within sensor range
  - true: Obstacle detected (distance is valid)
  - false: No obstacle or out of range (distance is null)

### How It Works

The HC-SR04 uses ultrasonic sound to measure distance:

1. **Trigger pulse**: 10μs pulse sent to TRIG pin
2. **Ultrasonic burst**: Sensor emits 8x 40kHz sound pulses
3. **Echo wait**: Sound travels to object and reflects back
4. **Echo pulse**: ECHO pin goes HIGH for duration proportional to distance
5. **Distance calculation**: `distance = (pulse_time × speed_of_sound) / 2`

```
Speed of sound: 343 m/s = 0.0343 cm/μs
Distance (cm) = (pulse_time_μs × 0.0343) / 2
```

## Usage Examples

### 1. Test the Sensor Directly (on Pico)
```python
# From Pico command line or Thonny
import asyncio
from sensors import hcsr04
asyncio.run(hcsr04._self_test())
```

### 2. Query via API (from your computer)
```bash
# Using curl
curl http://192.168.1.100:5000/api/ultrasonic

# Using Python
python test_ultrasonic_api.py  # (update IP address first)
```

### 3. Use in Client Code
```python
import requests

response = requests.get('http://192.168.1.100:5000/api/ultrasonic')
data = response.json()

if data['success']:
    if data['in_range']:
        distance = data['distance_cm']
        print(f"Obstacle detected at {distance:.1f}cm behind car")
        
        if distance < 20:
            print("WARNING: Too close!")
    else:
        print("All clear behind")
```

### 4. JavaScript/Web Client
```javascript
fetch('http://192.168.1.100:5000/api/ultrasonic')
  .then(response => response.json())
  .then(data => {
    if (data.success && data.in_range) {
      console.log(`Rear obstacle: ${data.distance_cm}cm`);
      
      if (data.distance_cm < 30) {
        alert('Warning: Obstacle close behind!');
      }
    }
  });
```

## Architecture

The HC-SR04 component follows the same pattern as other sensor modules:

1. **Background Monitoring**: Async task continuously reads sensor at 5 Hz
2. **Cached State**: Latest reading stored in `_state` dictionary
3. **Non-blocking**: API queries return cached data immediately
4. **Graceful Degradation**: Handles sensor errors without crashing

### Component Flow
```
main.py startup
    ↓
hcsr04.monitor() started as async task
    ↓
GPIO pins initialized → HC-SR04 sensor ready
    ↓
Loop: Measure distance every 200ms
    ↓
Send trigger pulse → Measure echo pulse → Calculate distance
    ↓
Update _state dictionary
    ↓
API endpoint reads _state via get_state()
    ↓
Return JSON to client
```

### Why 5 Hz Update Rate?

The HC-SR04 needs recovery time between measurements:
- **Minimum cycle time**: ~60ms (for sound to travel and dissipate)
- **Safe interval**: 200ms (5 Hz) prevents interference
- **Faster rates**: May cause echo overlap and false readings

## Troubleshooting

### Sensor Not Detected
**Symptom**: API returns `"available": false`

**Solutions**:
1. Verify 5V power supply (HC-SR04 won't work on 3.3V)
2. Check GPIO connections (TRIG=GP14, ECHO=GP15)
3. Ensure sensor has clear view (nothing blocking transducers)
4. Test with standalone script: `python sensors/hcsr04_test.py`

### Always Returns null
**Symptom**: `distance_cm` always null, `in_range` always false

**Solutions**:
1. Check if object is within range (2-400cm)
2. Verify object is in ~15° beam cone (center-aligned)
3. Avoid sound-absorbing materials (foam, fabric, grass)
4. Check for acoustic interference (other ultrasonic devices)
5. Ensure trigger pulse is working (test with oscilloscope)

### Erratic Readings
**Symptom**: Distance jumps around significantly

**Solutions**:
1. **Common issue**: Angled surfaces reflect sound away
2. Ensure sensor is mounted level and perpendicular
3. Avoid transparent materials (glass, clear plastic)
4. Add small delay if using near other ultrasonic sensors
5. Check for electrical noise from motors (add decoupling capacitor)

### Reading Too Slow
**Symptom**: Distance updates seem delayed

**Solutions**:
- Normal: 200ms update rate (5 readings/second)
- Don't decrease update rate (causes interference)
- If you need faster: Consider VL53L0X ToF sensors instead

## Performance

- **Update Rate**: 5 Hz (200ms interval)
- **API Response Time**: < 5ms (cached data)
- **Memory Usage**: ~1.5KB for module + state
- **CPU Impact**: Minimal (async I/O)
- **Measurement Time**: ~30-60ms per reading

## Integration with Autonomous Navigation

The rear ultrasonic sensor is essential for:

### Reverse Parking Assistance
```python
response = requests.get('http://picar:5000/api/ultrasonic')
data = response.json()

if data['in_range']:
    distance = data['distance_cm']
    
    # Proximity warnings
    if distance < 10:
        print("STOP! Obstacle very close!")
        motor_speed = 0
    elif distance < 20:
        print("Slow down - obstacle close")
        motor_speed = -20  # Slow reverse
    elif distance < 50:
        print("Caution - obstacle detected")
        motor_speed = -40  # Normal reverse
    else:
        print("All clear")
        motor_speed = -60  # Full reverse speed
```

### Collision Avoidance (Reversing)
```python
# Check rear before reversing
rear = requests.get('http://picar:5000/api/ultrasonic').json()

if rear['in_range'] and rear['distance_cm'] < 30:
    print("Cannot reverse - obstacle behind")
    # Take alternative action (stop, turn, go forward)
else:
    print("Safe to reverse")
    # Execute reverse maneuver
```

### Parking Space Detection
```python
# Drive past parking space, measure rear distances
# Detect when gap opens up (no obstacle for X seconds)
# Indicates potential parking space

rear_readings = []
for _ in range(10):  # 2 seconds of data
    rear = requests.get('http://picar:5000/api/ultrasonic').json()
    rear_readings.append(rear.get('in_range', False))
    time.sleep(0.2)

# If clear for extended period, might be parking space
if rear_readings.count(False) > 7:
    print("Potential parking space detected!")
```

## Sensor Placement Tips

1. **Height**: Mount 10-30cm above ground for best results
2. **Angle**: Point straight back (perpendicular to car)
3. **Clearance**: Keep 5cm away from other objects
4. **Protection**: Shield from direct water/rain if outdoor use
5. **Vibration**: Secure firmly (vibration affects readings)

## Comparison: HC-SR04 vs VL53L0X ToF

| Feature | HC-SR04 | VL53L0X (ToF) |
|---------|---------|---------------|
| Range | 2-400cm | 3-200cm |
| Accuracy | ±3mm | ±3% |
| Update Rate | 5 Hz max | 50 Hz+ |
| Beam Angle | ~15° cone | ~25° cone |
| Power | 5V | 3.3V |
| Interface | GPIO (pulse) | I2C |
| Cost | Very cheap | Moderate |
| Best For | Rear parking | Front navigation |

**Why HC-SR04 on rear?**
- ✅ Cheaper for single rear sensor
- ✅ Longer range for parking
- ✅ Simple GPIO interface
- ✅ Proven reliability

**Why VL53L0X on front?**
- ✅ Dual sensors for angle calculation
- ✅ Faster updates for navigation
- ✅ Multiple sensors on I2C
- ✅ Better in bright light

## Future Enhancements

Possible additions:
1. **Distance Zones**: Define warning/danger zones
2. **Beeping Pattern**: Faster beeps as obstacles get closer
3. **Historical Tracking**: Detect if obstacle is approaching
4. **Multi-sensor Fusion**: Combine with ToF data
5. **Calibration**: Auto-calibrate speed of sound for temperature

## References

- HC-SR04 Datasheet: https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf
- Ultrasonic Ranging: https://en.wikipedia.org/wiki/Ultrasonic_transducer
- Speed of Sound: https://en.wikipedia.org/wiki/Speed_of_sound
- MicroPython Pin: https://docs.micropython.org/en/latest/library/machine.Pin.html
- time_pulse_us: https://docs.micropython.org/en/latest/library/machine.html#machine.time_pulse_us
