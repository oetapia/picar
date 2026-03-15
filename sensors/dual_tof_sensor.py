"""
Dual VL53L0X Time-of-Flight Sensor Module
Measures distance from both left and right ToF sensors simultaneously

Hardware Setup:
- Left ToF:  GPIO 6 (SDA), GPIO 7 (SCL)  - Front left of car
- Right ToF: GPIO 20 (SDA), GPIO 21 (SCL) - Front right of car

Both sensors use default I2C address 0x29 but on separate I2C buses
"""

import machine
import time
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
    
    def __init__(self):
        """Initialize both ToF sensors."""
        self.left_sensor = None
        self.right_sensor = None
        self.left_i2c = None
        self.right_i2c = None
        self.initialized = False
        
    def init(self, verbose=True):
        """
        Initialize both I2C buses and ToF sensors.
        
        Args:
            verbose: Print initialization status messages
            
        Returns:
            tuple: (left_success, right_success) - True if sensor initialized successfully
        """
        left_ok = False
        right_ok = False
        
        # Initialize left sensor
        if verbose:
            print(f"[Left ToF] Initializing on GP{self.LEFT_SDA_PIN}/GP{self.LEFT_SCL_PIN}...")
        
        try:
            self.left_i2c = machine.SoftI2C(
                sda=machine.Pin(self.LEFT_SDA_PIN),
                scl=machine.Pin(self.LEFT_SCL_PIN),
                freq=self.I2C_FREQ
            )
            time.sleep_ms(10)
            
            # Check if sensor is present
            devices = self.left_i2c.scan()
            if self.I2C_ADDR in devices:
                self.left_sensor = VL53L0X(self.left_i2c, addr=self.I2C_ADDR)
                if self.left_sensor.check_id():
                    self.left_sensor.init()
                    left_ok = True
                    if verbose:
                        print("   ✓ Left sensor initialized successfully")
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
            print(f"[Right ToF] Initializing on GP{self.RIGHT_SDA_PIN}/GP{self.RIGHT_SCL_PIN}...")
        
        try:
            self.right_i2c = machine.SoftI2C(
                sda=machine.Pin(self.RIGHT_SDA_PIN),
                scl=machine.Pin(self.RIGHT_SCL_PIN),
                freq=self.I2C_FREQ
            )
            time.sleep_ms(10)
            
            # Check if sensor is present
            devices = self.right_i2c.scan()
            if self.I2C_ADDR in devices:
                self.right_sensor = VL53L0X(self.right_i2c, addr=self.I2C_ADDR)
                if self.right_sensor.check_id():
                    self.right_sensor.init()
                    right_ok = True
                    if verbose:
                        print("   ✓ Right sensor initialized successfully")
                else:
                    if verbose:
                        print("   ✗ Right sensor ID check failed")
            else:
                if verbose:
                    print(f"   ✗ Right sensor not found at 0x{self.I2C_ADDR:02X}")
        except Exception as e:
            if verbose:
                print(f"   ✗ Right sensor error: {e}")
        
        self.initialized = left_ok or right_ok
        
        if verbose:
            if left_ok and right_ok:
                print("✓ Both sensors initialized successfully")
            elif left_ok:
                print("⚠ Only left sensor available")
            elif right_ok:
                print("⚠ Only right sensor available")
            else:
                print("✗ No sensors initialized")
        
        return left_ok, right_ok
    
    def read_distances_cm(self, timeout_ms=1000):
        """
        Read distances from both sensors.
        
        Args:
            timeout_ms: Timeout for each sensor reading in milliseconds
            
        Returns:
            tuple: (left_distance_cm, right_distance_cm)
                   Returns None for sensors that fail or are not initialized
        """
        left_dist = None
        right_dist = None
        
        # Read left sensor
        if self.left_sensor:
            try:
                left_dist = self.left_sensor.read_cm(timeout_ms)
            except Exception as e:
                print(f"Left sensor read error: {e}")
        
        # Read right sensor
        if self.right_sensor:
            try:
                right_dist = self.right_sensor.read_cm(timeout_ms)
            except Exception as e:
                print(f"Right sensor read error: {e}")
        
        return left_dist, right_dist
    
    def read_distances_mm(self, timeout_ms=1000):
        """
        Read distances from both sensors in millimeters.
        
        Args:
            timeout_ms: Timeout for each sensor reading in milliseconds
            
        Returns:
            tuple: (left_distance_mm, right_distance_mm)
                   Returns None for sensors that fail or are not initialized
        """
        left_dist = None
        right_dist = None
        
        # Read left sensor
        if self.left_sensor:
            try:
                mm = self.left_sensor.read_mm(timeout_ms)
                left_dist = mm if mm != 65535 else None
            except Exception as e:
                print(f"Left sensor read error: {e}")
        
        # Read right sensor
        if self.right_sensor:
            try:
                mm = self.right_sensor.read_mm(timeout_ms)
                right_dist = mm if mm != 65535 else None
            except Exception as e:
                print(f"Right sensor read error: {e}")
        
        return left_dist, right_dist
    
    def get_status(self):
        """
        Get status of both sensors.
        
        Returns:
            dict: Status information for both sensors
        """
        return {
            'initialized': self.initialized,
            'left_available': self.left_sensor is not None,
            'right_available': self.right_sensor is not None
        }
    
    def format_reading(self, left_cm, right_cm):
        """
        Format sensor readings for display.
        
        Args:
            left_cm: Left distance in cm (or None)
            right_cm: Right distance in cm (or None)
            
        Returns:
            str: Formatted string for display
        """
        def format_dist(dist):
            if dist is None:
                return "---"
            elif dist < 10:
                return f"{dist:.1f}"
            else:
                return f"{int(dist)}"
        
        left_str = format_dist(left_cm)
        right_str = format_dist(right_cm)
        
        return f"L:{left_str:>4}cm  R:{right_str:>4}cm"


def test_dual_sensors():
    """Test function to demonstrate dual sensor reading."""
    print("=" * 50)
    print("Dual VL53L0X ToF Sensor Test")
    print("=" * 50)
    print("Left sensor:  GP6/GP7  (Front left)")
    print("Right sensor: GP20/GP21 (Front right)")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    # Initialize sensors
    tof = DualToFSensor()
    left_ok, right_ok = tof.init(verbose=True)
    
    if not tof.initialized:
        print("\n✗ Failed to initialize any sensors!")
        return
    
    print("\n" + "=" * 50)
    print("Starting continuous measurements (5 per second)")
    print("=" * 50)
    
    try:
        count = 0
        while True:
            # Read both sensors
            left_cm, right_cm = tof.read_distances_cm(timeout_ms=1000)
            
            # Format output
            count += 1
            timestamp = time.ticks_ms()
            
            # Print formatted reading
            reading_str = tof.format_reading(left_cm, right_cm)
            print(f"[{count:04d}] {reading_str}")
            
            # Optional: Print detailed info every 10 readings
            if count % 10 == 0:
                print(f"       Left:  {left_cm if left_cm else 'Out of range'}")
                print(f"       Right: {right_cm if right_cm else 'Out of range'}")
            
            # Wait before next measurement (5 Hz)
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 50)
        print("Test stopped by user")
    except Exception as e:
        print(f"\nError during test: {e}")


# Module-level instance for easy import
dual_tof = None


def get_dual_tof():
    """
    Get or create the global dual ToF sensor instance.
    
    Returns:
        DualToFSensor: Initialized sensor instance
    """
    global dual_tof
    if dual_tof is None:
        dual_tof = DualToFSensor()
        dual_tof.init(verbose=False)
    return dual_tof


if __name__ == '__main__':
    test_dual_sensors()
