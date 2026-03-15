"""
MPU-6050 Accelerometer/Gyroscope Component
Provides async monitoring and cached state for API access
"""

import machine
import time
import math
import uasyncio as asyncio

# ========== MPU-6050 Configuration ==========
MPU6050_ADDR = 0x68      # Default I2C address
SDA_PIN = 8              # GP8
SCL_PIN = 9              # GP9
I2C_BUS = 0              # I2C0
I2C_FREQ = 400_000       # 400kHz

# MPU-6050 Register Addresses
PWR_MGMT_1 = 0x6B        # Power management
WHO_AM_I = 0x75          # Device ID register
ACCEL_XOUT_H = 0x3B      # Accelerometer data start
GYRO_XOUT_H = 0x43       # Gyroscope data start

# Conversion factors
ACCEL_SCALE = 16384.0    # +/-2g range
GYRO_SCALE = 131.0       # +/-250 deg/s range


class MPU6050:
    """MPU-6050 6-axis accelerometer/gyroscope driver for MicroPython."""
    
    def __init__(self, i2c, address=MPU6050_ADDR):
        self.i2c = i2c
        self.address = address
        self.initialized = False
    
    def _read_byte(self, reg):
        """Read a single byte from a register."""
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]
    
    def _write_byte(self, reg, value):
        """Write a single byte to a register."""
        self.i2c.writeto_mem(self.address, reg, bytes([value]))
    
    def _read_word(self, reg):
        """Read a 16-bit signed word from a register (big-endian)."""
        data = self.i2c.readfrom_mem(self.address, reg, 2)
        value = (data[0] << 8) | data[1]
        # Convert to signed
        if value > 32767:
            value -= 65536
        return value
    
    def detect(self):
        """Check if MPU-6050 is present on I2C bus."""
        try:
            devices = self.i2c.scan()
            if self.address in devices:
                who_am_i = self._read_byte(WHO_AM_I)
                # MPU-6050 returns 0x68, but some clones return 0x72 or 0x73
                if who_am_i in (0x68, 0x72, 0x73):
                    return True
            return False
        except Exception:
            return False
    
    def init(self):
        """Initialize the MPU-6050 sensor."""
        try:
            if not self.detect():
                return False
            
            # Wake up the sensor (default is sleep mode)
            self._write_byte(PWR_MGMT_1, 0x00)
            time.sleep(0.1)
            
            self.initialized = True
            return True
            
        except Exception:
            return False
    
    def read_accel_raw(self):
        """Read raw accelerometer values (X, Y, Z)."""
        try:
            x = self._read_word(ACCEL_XOUT_H)
            y = self._read_word(ACCEL_XOUT_H + 2)
            z = self._read_word(ACCEL_XOUT_H + 4)
            return x, y, z
        except Exception:
            return None, None, None
    
    def read_gyro_raw(self):
        """Read raw gyroscope values (X, Y, Z)."""
        try:
            x = self._read_word(GYRO_XOUT_H)
            y = self._read_word(GYRO_XOUT_H + 2)
            z = self._read_word(GYRO_XOUT_H + 4)
            return x, y, z
        except Exception:
            return None, None, None
    
    def read_accel(self):
        """Read accelerometer values in g (gravity units)."""
        ax, ay, az = self.read_accel_raw()
        if ax is None:
            return None, None, None
        return ax / ACCEL_SCALE, ay / ACCEL_SCALE, az / ACCEL_SCALE
    
    def read_gyro(self):
        """Read gyroscope values in degrees/second."""
        gx, gy, gz = self.read_gyro_raw()
        if gx is None:
            return None, None, None
        return gx / GYRO_SCALE, gy / GYRO_SCALE, gz / GYRO_SCALE
    
    def get_tilt(self):
        """Calculate pitch and roll angles from accelerometer in degrees."""
        ax, ay, az = self.read_accel()
        if ax is None:
            return None, None
        
        # Calculate pitch (rotation around Y-axis)
        pitch = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))
        
        # Calculate roll (rotation around X-axis)
        roll = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))
        
        return pitch, roll
    
    def get_orientation(self, threshold=15.0):
        """
        Classify orientation based on tilt angles.
        Returns: "level", "forward", "back", "right", "left", or combined states.
        """
        pitch, roll = self.get_tilt()
        if pitch is None:
            return "error"
        
        if abs(pitch) < threshold and abs(roll) < threshold:
            return "level"
        
        states = []
        if pitch > threshold:
            states.append("forward")
        elif pitch < -threshold:
            states.append("back")
        
        if roll > threshold:
            states.append("right")
        elif roll < -threshold:
            states.append("left")
        
        return "+".join(states) if states else "level"


# -------------------------
# Global sensor instance
# -------------------------
_sensor = None
_sensor_available = False

# -------------------------
# Cached state (updated by monitor)
# -------------------------
_state = {
    "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
    "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0},
    "tilt": {"pitch": 0.0, "roll": 0.0},
    "orientation": "unknown",
    "available": False,
    "timestamp": 0
}


# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    """Continuously read MPU-6050 sensor and update cached state."""
    global _sensor, _sensor_available
    
    print("Accelerometer monitor: initializing MPU-6050...")
    
    # Initialize I2C
    try:
        i2c = machine.I2C(I2C_BUS, sda=machine.Pin(SDA_PIN), scl=machine.Pin(SCL_PIN), freq=I2C_FREQ)
        time.sleep(0.01)
        
        # Initialize sensor
        _sensor = MPU6050(i2c, address=MPU6050_ADDR)
        
        if _sensor.init():
            _sensor_available = True
            _state["available"] = True
            print("Accelerometer monitor: MPU-6050 initialized successfully")
        else:
            print("Accelerometer monitor: MPU-6050 not detected or init failed")
            _state["available"] = False
    except Exception as e:
        print(f"Accelerometer monitor: initialization error: {e}")
        _state["available"] = False
    
    # Monitor loop
    print("Accelerometer monitor started")
    while True:
        if _sensor_available and _sensor:
            try:
                # Read accelerometer
                ax, ay, az = _sensor.read_accel()
                if ax is not None:
                    _state["acceleration"]["x"] = round(ax, 3)
                    _state["acceleration"]["y"] = round(ay, 3)
                    _state["acceleration"]["z"] = round(az, 3)
                
                # Read gyroscope
                gx, gy, gz = _sensor.read_gyro()
                if gx is not None:
                    _state["gyroscope"]["x"] = round(gx, 1)
                    _state["gyroscope"]["y"] = round(gy, 1)
                    _state["gyroscope"]["z"] = round(gz, 1)
                
                # Read tilt
                pitch, roll = _sensor.get_tilt()
                if pitch is not None:
                    _state["tilt"]["pitch"] = round(pitch, 1)
                    _state["tilt"]["roll"] = round(roll, 1)
                
                # Read orientation
                orientation = _sensor.get_orientation()
                _state["orientation"] = orientation
                
                _state["timestamp"] = time.time()
                _state["available"] = True
                
            except Exception as e:
                print(f"Accelerometer monitor: read error: {e}")
                _state["available"] = False
        
        # Update every 100ms (10 Hz)
        await asyncio.sleep_ms(100)


# -------------------------
# State accessor for API
# -------------------------
def get_state():
    """Get current cached accelerometer state."""
    return dict(_state)


# -------------------------
# Self-test (run directly)
# -------------------------
if __name__ == "__main__":
    async def _self_test():
        print("=== Accelerometer Self-Test ===")
        asyncio.create_task(monitor())
        
        # Wait for initialization
        await asyncio.sleep(2)
        
        # Read for 10 seconds
        for i in range(20):
            await asyncio.sleep_ms(500)
            s = get_state()
            if s["available"]:
                print(f"[{i+1:02d}] Accel: X={s['acceleration']['x']:+.3f}g Y={s['acceleration']['y']:+.3f}g Z={s['acceleration']['z']:+.3f}g | "
                      f"Tilt: P={s['tilt']['pitch']:+.1f}° R={s['tilt']['roll']:+.1f}° | {s['orientation']}")
            else:
                print(f"[{i+1:02d}] Sensor not available")
        
        print("=== Self-Test Complete ===")

    asyncio.run(_self_test())
