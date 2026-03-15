"""
Dual VL53L0X ToF Sensor Component with Angle Calculator
Provides async monitoring and cached state for API access

Hardware Setup:
- Left ToF:  GPIO 6 (SDA), GPIO 7 (SCL)  - Front left
- Right ToF: GPIO 20 (SDA), GPIO 21 (SCL) - Front right
"""

import machine
import time
import math
import uasyncio as asyncio
from vl53l0x_mp import VL53L0X, VL53L0XError


class DualToFSensor:
    """Manages two VL53L0X ToF sensors for left and right distance measurement."""
    
    # Left sensor configuration (front left)
    LEFT_SDA_PIN = 6
    LEFT_SCL_PIN = 7
    
    # Right sensor configuration (front right)
    RIGHT_SDA_PIN = 20
    RIGHT_SCL_PIN = 21
    
    # Common configuration
    I2C_ADDR = 0x29
    I2C_FREQ = 100_000  # 100kHz for reliability
    
    # Sensor spacing for angle calculation (cm)
    SENSOR_SPACING_CM = 15.0  # Adjust this to match your car's sensor spacing
    
    def __init__(self):
        """Initialize both ToF sensors."""
        self.left_sensor = None
        self.right_sensor = None
        self.left_i2c = None
        self.right_i2c = None
        self.left_available = False
        self.right_available = False
        
    def init(self, verbose=True):
        """
        Initialize both I2C buses and ToF sensors.
        
        Args:
            verbose: Print initialization status messages
            
        Returns:
            tuple: (left_success, right_success)
        """
        left_ok = False
        right_ok = False
        
        # Initialize left sensor
        if verbose:
            print(f"Dual ToF: Initializing left sensor on GP{self.LEFT_SDA_PIN}/GP{self.LEFT_SCL_PIN}...")
        
        try:
            self.left_i2c = machine.SoftI2C(
                sda=machine.Pin(self.LEFT_SDA_PIN),
                scl=machine.Pin(self.LEFT_SCL_PIN),
                freq=self.I2C_FREQ
            )
            time.sleep_ms(10)
            
            devices = self.left_i2c.scan()
            if self.I2C_ADDR in devices:
                self.left_sensor = VL53L0X(self.left_i2c, addr=self.I2C_ADDR)
                if self.left_sensor.check_id():
                    self.left_sensor.init()
                    left_ok = True
                    self.left_available = True
                    if verbose:
                        print("   ✓ Left sensor initialized")
                else:
                    if verbose:
                        print("   ✗ Left sensor ID check failed")
            else:
                if verbose:
                    print(f"   ✗ Left sensor not found at 0x{self.I2C_ADDR:02X}")
        except Exception as e:
            if verbose:
                print(f"   ✗ Left sensor error: {e}")
        
        # Initialize right sensor
        if verbose:
            print(f"Dual ToF: Initializing right sensor on GP{self.RIGHT_SDA_PIN}/GP{self.RIGHT_SCL_PIN}...")
        
        try:
            self.right_i2c = machine.SoftI2C(
                sda=machine.Pin(self.RIGHT_SDA_PIN),
                scl=machine.Pin(self.RIGHT_SCL_PIN),
                freq=self.I2C_FREQ
            )
            time.sleep_ms(10)
            
            devices = self.right_i2c.scan()
            if self.I2C_ADDR in devices:
                self.right_sensor = VL53L0X(self.right_i2c, addr=self.I2C_ADDR)
                if self.right_sensor.check_id():
                    self.right_sensor.init()
                    right_ok = True
                    self.right_available = True
                    if verbose:
                        print("   ✓ Right sensor initialized")
                else:
                    if verbose:
                        print("   ✗ Right sensor ID check failed")
            else:
                if verbose:
                    print(f"   ✗ Right sensor not found at 0x{self.I2C_ADDR:02X}")
        except Exception as e:
            if verbose:
                print(f"   ✗ Right sensor error: {e}")
        
        return left_ok, right_ok
    
    def read_distances_cm(self, timeout_ms=1000):
        """
        Read distances from both sensors in centimeters.
        
        Returns:
            tuple: (left_cm, right_cm) - None if sensor unavailable or error
        """
        left_dist = None
        right_dist = None
        
        if self.left_sensor:
            try:
                left_dist = self.left_sensor.read_cm(timeout_ms)
            except Exception:
                pass
        
        if self.right_sensor:
            try:
                right_dist = self.right_sensor.read_cm(timeout_ms)
            except Exception:
                pass
        
        return left_dist, right_dist
    
    def calculate_wall_angle(self, left_cm, right_cm):
        """
        Calculate the angle of a wall relative to the car's forward direction.
        
        Returns:
            dict with angle information or None if invalid measurements
        """
        if left_cm is None or right_cm is None:
            return None
        
        if left_cm <= 0 or right_cm <= 0:
            return None
        
        # Calculate angle using arctangent
        distance_diff = right_cm - left_cm
        angle_radians = math.atan2(distance_diff, self.SENSOR_SPACING_CM)
        angle_degrees = math.degrees(angle_radians)
        
        # Determine if wall is perpendicular (within ±5 degrees)
        is_perpendicular = abs(angle_degrees) < 5.0
        
        # Determine orientation
        if is_perpendicular:
            orientation = 'straight'
        elif angle_degrees > 0:
            orientation = 'angled_right'
        else:
            orientation = 'angled_left'
        
        # Calculate approximate perpendicular distance to wall
        min_distance = min(left_cm, right_cm)
        wall_distance_cm = min_distance * math.cos(angle_radians)
        
        return {
            'angle_degrees': round(angle_degrees, 2),
            'is_perpendicular': is_perpendicular,
            'orientation': orientation,
            'wall_distance_cm': round(wall_distance_cm, 1)
        }


# -------------------------
# Global sensor instance
# -------------------------
_sensor = None
_sensor_available = False

# -------------------------
# Cached state (updated by monitor)
# -------------------------
_state = {
    "left_distance_cm": None,
    "right_distance_cm": None,
    "angle": None,  # Will contain angle calculation results
    "left_available": False,
    "right_available": False,
    "available": False,
    "timestamp": 0
}


# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    """Continuously read dual ToF sensors and calculate angles."""
    global _sensor, _sensor_available
    
    print("Dual ToF monitor: initializing sensors...")
    
    # Initialize sensors
    try:
        _sensor = DualToFSensor()
        left_ok, right_ok = _sensor.init(verbose=True)
        
        if left_ok or right_ok:
            _sensor_available = True
            _state["left_available"] = left_ok
            _state["right_available"] = right_ok
            _state["available"] = True
            
            if left_ok and right_ok:
                print("Dual ToF monitor: both sensors initialized successfully")
            elif left_ok:
                print("Dual ToF monitor: only left sensor available")
            elif right_ok:
                print("Dual ToF monitor: only right sensor available")
        else:
            print("Dual ToF monitor: no sensors detected or init failed")
            _state["available"] = False
    except Exception as e:
        print(f"Dual ToF monitor: initialization error: {e}")
        _state["available"] = False
    
    # Monitor loop
    print("Dual ToF monitor started")
    while True:
        if _sensor_available and _sensor:
            try:
                # Read distances
                left_cm, right_cm = _sensor.read_distances_cm(timeout_ms=1000)
                
                _state["left_distance_cm"] = round(left_cm, 1) if left_cm else None
                _state["right_distance_cm"] = round(right_cm, 1) if right_cm else None
                
                # Calculate angle if both sensors have valid readings
                if left_cm and right_cm:
                    angle_data = _sensor.calculate_wall_angle(left_cm, right_cm)
                    _state["angle"] = angle_data
                else:
                    _state["angle"] = None
                
                _state["timestamp"] = time.time()
                
            except Exception as e:
                print(f"Dual ToF monitor: read error: {e}")
                _state["left_distance_cm"] = None
                _state["right_distance_cm"] = None
                _state["angle"] = None
        
        # Update every 200ms (5 Hz)
        await asyncio.sleep_ms(200)


# -------------------------
# State accessor for API
# -------------------------
def get_state():
    """Get current cached dual ToF sensor state."""
    return dict(_state)


# -------------------------
# Self-test (run directly)
# -------------------------
if __name__ == "__main__":
    async def _self_test():
        print("=== Dual ToF Self-Test ===")
        asyncio.create_task(monitor())
        
        # Wait for initialization
        await asyncio.sleep(2)
        
        # Read for 10 seconds
        for i in range(20):
            await asyncio.sleep_ms(500)
            s = get_state()
            
            if s["available"]:
                left = s['left_distance_cm']
                right = s['right_distance_cm']
                angle_data = s.get('angle')
                
                left_str = f"{left:.1f}cm" if left else "---"
                right_str = f"{right:.1f}cm" if right else "---"
                
                print(f"[{i+1:02d}] L:{left_str:>7} R:{right_str:>7}", end="")
                
                if angle_data:
                    angle = angle_data['angle_degrees']
                    orientation = angle_data['orientation']
                    wall_dist = angle_data['wall_distance_cm']
                    print(f" | Angle:{angle:+6.2f}° {orientation:>12} | Wall:{wall_dist:5.1f}cm")
                else:
                    print(" | No angle data")
            else:
                print(f"[{i+1:02d}] Sensors not available")
        
        print("=== Self-Test Complete ===")

    asyncio.run(_self_test())
