"""
MPU-6050 Accelerometer Test Script
Displays acceleration values on OLED and console
"""

from machine import I2C, Pin
import time
try:
    import display
except ImportError:
    display = None

# MPU-6050 Constants
MPU6050_ADDR = 0x68
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B


def read_accel(i2c):
    """Read acceleration values from MPU-6050."""
    data = i2c.readfrom_mem(MPU6050_ADDR, ACCEL_XOUT_H, 6)
    
    def s16(hi, lo):
        """Convert two bytes to signed 16-bit integer."""
        v = (hi << 8) | lo
        return v - 65536 if v > 32767 else v
    
    # Convert raw values to g units (±2g range, 16384 LSB/g)
    ax = s16(data[0], data[1]) / 16384.0
    ay = s16(data[2], data[3]) / 16384.0
    az = s16(data[4], data[5]) / 16384.0
    return ax, ay, az


def format_g_value(v):
    """Format acceleration value with sign."""
    return ("+" if v >= 0 else "") + f"{v:.2f}"


def run():
    """Main loop: continuously read and display acceleration."""
    print("MPU-6050 Accelerometer Test")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Initialize I2C
    i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
    
    # Check if display is available
    use_display = display is not None and hasattr(display, 'display') and display.display is not None
    
    if use_display:
        display.update_display(header="MPU-6050 Init", text="Starting...")
    
    # Wake MPU-6050 (clear sleep bit)
    try:
        i2c.writeto_mem(MPU6050_ADDR, PWR_MGMT_1, b'\x00')
        time.sleep_ms(100)
        print("MPU-6050 initialized successfully")
        
        if use_display:
            display.update_display(header="MPU-6050", text="Ready")
            time.sleep(1)
    except Exception as e:
        print(f"ERROR: Failed to initialize MPU-6050: {e}")
        if use_display:
            display.update_display(header="MPU-6050 Error", text="Init failed")
        return
    
    print("\nReading acceleration values (10 per second)...")
    measurement_count = 0
    
    try:
        while True:
            try:
                # Read accelerometer values
                ax, ay, az = read_accel(i2c)
                measurement_count += 1
                
                # Format for display
                x_str = format_g_value(ax)
                y_str = format_g_value(ay)
                z_str = format_g_value(az)
                
                # Update display (if available)
                if use_display:
                    display.update_display(
                        header="MPU-6050",
                        text=f"X:{x_str} Y:{y_str}\nZ:{z_str}",
                        icon='robot'
                    )
                
                # Print to console
                print(f"[{measurement_count:04d}] X:{x_str}g  Y:{y_str}g  Z:{z_str}g")
                
            except OSError as e:
                print(f"I2C error: {e}")
                if use_display:
                    display.update_display(header="I2C Error", text="Check wiring")
                time.sleep(1)
            
            # 10 measurements per second
            time.sleep_ms(100)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 40)
        print("Test stopped by user")
        if use_display:
            display.update_display(header="MPU-6050", text="Test stopped")
            time.sleep(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        if use_display:
            display.update_display(header="Error", text=str(e)[:20])
        time.sleep(2)


if __name__ == '__main__':
    run()
