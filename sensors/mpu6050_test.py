"""
MPU-6050 Accelerometer/Gyroscope Test Script
Communication: I2C (default address 0x68)
Uses I2C0: SDA=GP4, SCL=GP5
Displays sensor data on OLED screen
"""

import sys
sys.path.insert(0, '/sensors')  # For mpremote run from root

import machine
import time
import math
import display

# ========== MPU-6050 Configuration ==========
MPU6050_ADDR = 0x68      # Default I2C address
SDA_PIN = 4              # GP4
SCL_PIN = 5              # GP5
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
                else:
                    print(f"Warning: Unexpected WHO_AM_I: 0x{who_am_i:02X}")
                    return True  # Try to use it anyway
            return False
        except Exception as e:
            print(f"Detection error: {e}")
            return False
    
    def init(self):
        """Initialize the MPU-6050 sensor."""
        try:
            if not self.detect():
                print("MPU-6050 not detected on I2C bus!")
                return False
            
            # Wake up the sensor (default is sleep mode)
            self._write_byte(PWR_MGMT_1, 0x00)
            time.sleep_ms(100)
            
            # Set accelerometer range to +/-2g (default)
            # Set gyroscope range to +/-250 deg/s (default)
            # These are already defaults, but we could configure if needed
            
            self.initialized = True
            print("MPU-6050 initialized successfully")
            return True
            
        except Exception as e:
            print(f"Initialization error: {e}")
            return False
    
    def read_accel_raw(self):
        """Read raw accelerometer values (X, Y, Z)."""
        try:
            x = self._read_word(ACCEL_XOUT_H)
            y = self._read_word(ACCEL_XOUT_H + 2)
            z = self._read_word(ACCEL_XOUT_H + 4)
            return x, y, z
        except Exception as e:
            print(f"Read accel error: {e}")
            return None, None, None
    
    def read_gyro_raw(self):
        """Read raw gyroscope values (X, Y, Z)."""
        try:
            x = self._read_word(GYRO_XOUT_H)
            y = self._read_word(GYRO_XOUT_H + 2)
            z = self._read_word(GYRO_XOUT_H + 4)
            return x, y, z
        except Exception as e:
            print(f"Read gyro error: {e}")
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


def format_sensor_data(sensor):
    """Format sensor data for OLED display (compact format)."""
    pitch, roll = sensor.get_tilt()
    if pitch is None:
        return "Read error"
    
    orientation = sensor.get_orientation()
    
    # Format: "P:±XX R:±XX" and orientation on separate lines
    return f"P:{pitch:+.0f} R:{roll:+.0f}\n{orientation}"


def main():
    """Main loop: continuously read sensor and display data."""
    print("MPU-6050 Accelerometer/Gyroscope Test")
    print(f"I2C: Bus {I2C_BUS}, Address 0x{MPU6050_ADDR:02X}")
    print(f"Pins: SDA=GP{SDA_PIN}, SCL=GP{SCL_PIN}")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Initialize display
    if display.display is None:
        print("Error: OLED display not initialized!")
        return
    
    display.update_display(header="MPU6050 Init", text="Starting...")
    time.sleep(1)
    
    # Initialize I2C
    print(f"\n[1] Initializing I2C on GP{SDA_PIN} (SDA) and GP{SCL_PIN} (SCL)...")
    i2c = machine.I2C(I2C_BUS, sda=machine.Pin(SDA_PIN), scl=machine.Pin(SCL_PIN), freq=I2C_FREQ)
    time.sleep_ms(10)
    
    # Scan for devices
    devices = i2c.scan()
    print(f"   Found {len(devices)} I2C device(s): {', '.join('0x{:02X}'.format(a) for a in devices)}")
    
    if MPU6050_ADDR not in devices:
        print(f"   ERROR: MPU-6050 not found at 0x{MPU6050_ADDR:02X}")
        display.update_display(header="MPU6050 Error", text="Not detected")
        return
    
    # Initialize sensor
    print(f"\n[2] Initializing MPU-6050 sensor...")
    sensor = MPU6050(i2c, address=MPU6050_ADDR)
    
    if not sensor.init():
        print("   ERROR: Failed to initialize MPU-6050!")
        display.update_display(header="MPU6050 Error", text="Init failed")
        return
    
    # Check WHO_AM_I
    who_am_i = sensor._read_byte(WHO_AM_I)
    print(f"   WHO_AM_I: 0x{who_am_i:02X} (MPU-6050 confirmed)")
    
    print("\n[3] Streaming sensor data (5 per second)...")
    display.update_display(header="MPU6050 Ready", text="Reading...")
    time.sleep(1)
    
    try:
        measurement_count = 0
        while True:
            # Read sensor data
            ax, ay, az = sensor.read_accel()
            gx, gy, gz = sensor.read_gyro()
            pitch, roll = sensor.get_tilt()
            orientation = sensor.get_orientation()
            
            # Format for display (compact, 2 lines)
            if pitch is not None:
                display_text = f"P:{pitch:+.0f} R:{roll:+.0f}\n{orientation}"
            else:
                display_text = "Read error"
            
            # Update OLED display
            display.update_display(
                header="MPU6050 IMU",
                text=display_text,
                icon='robot'  # Optional icon
            )
            
            # Print to console
            measurement_count += 1
            if ax is not None:
                print(f"[{measurement_count:04d}] "
                      f"Accel: X={ax:+.3f}g Y={ay:+.3f}g Z={az:+.3f}g | "
                      f"Gyro: X={gx:+.1f}°/s Y={gy:+.1f}°/s Z={gz:+.1f}°/s | "
                      f"Pitch={pitch:+.1f}° Roll={roll:+.1f}° | {orientation}")
            else:
                print(f"[{measurement_count:04d}] Read error")
            
            # Wait before next measurement (5 measurements per second)
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 40)
        print("Test stopped by user")
        display.update_display(header="MPU6050", text="Test stopped")
        time.sleep(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        display.update_display(header="MPU6050 Error", text=str(e)[:20])
        time.sleep(2)


if __name__ == '__main__':
    main()
