"""
VL53L0X Time-of-Flight Laser Distance Sensor Test Script
Communication: I2C (default address 0x29)
Uses I2C1: SDA=GP18, SCL=GP19 (shared with OLED)
Displays distance measurements on OLED screen
"""

import machine
import time
import display

# ========== VL53L0X Configuration ==========
VL53L0X_I2C_ADDR = 0x29  # Default I2C address
I2C_BUS = 1              # I2C1 (shared with OLED)
SDA_PIN = 18             # GP18
SCL_PIN = 19             # GP19

# VL53L0X Register Addresses
REG_IDENTIFICATION_MODEL_ID = 0xC0
REG_SYSRANGE_START = 0x00
REG_RESULT_RANGE_STATUS = 0x14
REG_SYSTEM_INTERMEASUREMENT_PERIOD = 0x04

# Initialize I2C
i2c = machine.I2C(I2C_BUS, sda=machine.Pin(SDA_PIN), scl=machine.Pin(SCL_PIN), freq=400000)


class VL53L0X:
    """Simplified VL53L0X Time-of-Flight sensor driver."""
    
    def __init__(self, i2c, address=VL53L0X_I2C_ADDR):
        self.i2c = i2c
        self.address = address
        self.initialized = False
        
    def read_byte(self, reg):
        """Read a single byte from a register."""
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]
    
    def read_word(self, reg):
        """Read a 16-bit word from a register (big-endian)."""
        data = self.i2c.readfrom_mem(self.address, reg, 2)
        return (data[0] << 8) | data[1]
    
    def write_byte(self, reg, value):
        """Write a single byte to a register."""
        self.i2c.writeto_mem(self.address, reg, bytes([value]))
    
    def write_word(self, reg, value):
        """Write a 16-bit word to a register (big-endian)."""
        data = bytes([(value >> 8) & 0xFF, value & 0xFF])
        self.i2c.writeto_mem(self.address, reg, data)
    
    def detect(self):
        """Check if VL53L0X is present on I2C bus."""
        try:
            devices = self.i2c.scan()
            if self.address in devices:
                model_id = self.read_byte(REG_IDENTIFICATION_MODEL_ID)
                if model_id == 0xEE:  # VL53L0X model ID
                    return True
                else:
                    print(f"Warning: Unexpected model ID: 0x{model_id:02X} (expected 0xEE)")
                    return True  # Still try to use it
            return False
        except Exception as e:
            print(f"Detection error: {e}")
            return False
    
    def init(self):
        """Initialize the sensor for basic operation."""
        try:
            if not self.detect():
                print("VL53L0X not detected on I2C bus!")
                return False
            
            # Basic initialization sequence
            # Set to continuous ranging mode
            self.write_byte(0x80, 0x01)
            self.write_byte(0xFF, 0x01)
            self.write_byte(0x00, 0x00)
            self.write_byte(0x91, 0x3C)
            self.write_byte(0x00, 0x01)
            self.write_byte(0xFF, 0x00)
            self.write_byte(0x80, 0x00)
            
            self.initialized = True
            print("VL53L0X initialized successfully")
            return True
            
        except Exception as e:
            print(f"Initialization error: {e}")
            return False
    
    def start_ranging(self):
        """Start a single ranging measurement."""
        try:
            self.write_byte(REG_SYSRANGE_START, 0x01)
        except Exception as e:
            print(f"Start ranging error: {e}")
    
    def wait_for_measurement(self, timeout_ms=500):
        """Wait for measurement to complete."""
        start_time = time.ticks_ms()
        while True:
            try:
                status = self.read_byte(REG_RESULT_RANGE_STATUS)
                if status & 0x01:  # Bit 0 indicates new data ready
                    return True
                
                if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                    return False
                    
                time.sleep_ms(10)
            except Exception as e:
                print(f"Wait error: {e}")
                return False
    
    def read_distance(self):
        """Read distance measurement in millimeters."""
        try:
            # Distance is at offset 0x14 + 10 bytes
            distance_mm = self.read_word(REG_RESULT_RANGE_STATUS + 10)
            return distance_mm
        except Exception as e:
            print(f"Read distance error: {e}")
            return None
    
    def measure_distance(self):
        """
        Perform a single distance measurement.
        
        Returns:
            float: Distance in millimeters, or None if measurement failed
        """
        if not self.initialized:
            return None
        
        try:
            self.start_ranging()
            
            if not self.wait_for_measurement(timeout_ms=500):
                print("Measurement timeout")
                return None
            
            distance_mm = self.read_distance()
            
            # Validate measurement (VL53L0X range: ~30mm to 2000mm)
            if distance_mm is not None and 30 <= distance_mm <= 2000:
                return distance_mm
            elif distance_mm == 8190 or distance_mm == 8191:
                # Out of range indicator
                return None
            else:
                return distance_mm  # Return anyway, let user decide
                
        except Exception as e:
            print(f"Measurement error: {e}")
            return None


def format_distance(distance_mm):
    """Format distance for display."""
    if distance_mm is None:
        return "Out of range"
    
    # Convert to cm for consistency with HC-SR04
    distance_cm = distance_mm / 10.0
    
    if distance_cm < 10:
        return f"{distance_cm:.2f} cm"
    elif distance_cm < 100:
        return f"{distance_cm:.1f} cm"
    else:
        return f"{int(distance_cm)} cm"


def main():
    """Main loop: continuously measure and display distance."""
    print("VL53L0X Time-of-Flight Laser Distance Sensor Test")
    print(f"I2C: Bus {I2C_BUS}, Address 0x{VL53L0X_I2C_ADDR:02X}")
    print(f"Pins: SDA=GP{SDA_PIN}, SCL=GP{SCL_PIN}")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Initialize display
    if display.display is None:
        print("Error: OLED display not initialized!")
        return
    
    display.update_display(header="VL53L0X Init", text="Starting...")
    time.sleep(1)
    
    # Initialize sensor
    sensor = VL53L0X(i2c)
    
    print("Detecting VL53L0X sensor...")
    if not sensor.init():
        print("Failed to initialize VL53L0X!")
        display.update_display(header="VL53L0X Error", text="Not detected")
        return
    
    print("VL53L0X ready!")
    display.update_display(header="VL53L0X Ready", text="Measuring...")
    time.sleep(1)
    
    try:
        measurement_count = 0
        while True:
            # Measure distance
            distance_mm = sensor.measure_distance()
            
            # Format for display
            distance_text = format_distance(distance_mm)
            
            # Update OLED display
            display.update_display(
                header="VL53L0X ToF",
                text=distance_text,
                icon='robot'  # Optional icon
            )
            
            # Print to console
            measurement_count += 1
            if distance_mm is not None:
                distance_cm = distance_mm / 10.0
                print(f"[{measurement_count:04d}] Distance: {distance_mm:4d} mm ({distance_cm:.2f} cm)")
            else:
                print(f"[{measurement_count:04d}] Out of range or error")
            
            # Wait before next measurement (5 measurements per second)
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 40)
        print("Test stopped by user")
        display.update_display(header="VL53L0X", text="Test stopped")
        time.sleep(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        display.update_display(header="VL53L0X Error", text=str(e)[:20])
        time.sleep(2)


if __name__ == '__main__':
    main()
