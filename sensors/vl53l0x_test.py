"""
VL53L0X Time-of-Flight Laser Distance Sensor Test Script
Communication: I2C (default address 0x29)
Uses SoftI2C on GP6 (SDA) and GP7 (SCL) - separate from OLED
Displays distance measurements on OLED screen
"""

import machine
import time
try:
    import display
except ImportError:
    display = None
from vl53l0x_mp import VL53L0X, VL53L0XError

# ========== VL53L0X Configuration ==========
VL53L0X_I2C_ADDR = 0x29  # Default I2C address
SDA_PIN = 6              # GP0 - VL53L0X SDA
SCL_PIN = 7              # GP1 - VL53L0X SCL
I2C_FREQ = 100_000       # 100kHz - more reliable for VL53L0X on Pico

# Note: VL53L0X uses separate I2C pins from OLED
# OLED is on GP18/GP19 (I2C1), VL53L0X is on GP0/GP1 (SoftI2C)
def format_distance(distance_cm):
    """Format distance for display."""
    if distance_cm is None:
        return "Out of range"
    
    if distance_cm < 10:
        return f"{distance_cm:.2f} cm"
    elif distance_cm < 100:
        return f"{distance_cm:.1f} cm"
    else:
        return f"{int(distance_cm)} cm"


def main():
    """Main loop: continuously measure and display distance."""
    print("VL53L0X Time-of-Flight Laser Distance Sensor Test")
    print(f"I2C: SoftI2C @ {I2C_FREQ}Hz, Address 0x{VL53L0X_I2C_ADDR:02X}")
    print(f"Pins: SDA=GP{SDA_PIN}, SCL=GP{SCL_PIN}")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Initialize display (optional)
    use_display = display is not None and hasattr(display, 'display') and display.display is not None
    
    if use_display:
        display.update_display(header="VL53L0X Init", text="Starting...")
        time.sleep(1)
    
    # Initialize I2C (SoftI2C for better compatibility with VL53L0X)
    print(f"\n[1] Initializing SoftI2C on GP{SDA_PIN} (SDA) and GP{SCL_PIN} (SCL)...")
    i2c = machine.SoftI2C(
        sda=machine.Pin(SDA_PIN),
        scl=machine.Pin(SCL_PIN),
        freq=I2C_FREQ
    )
    time.sleep_ms(10)  # Let bus settle
    
    # Scan for devices
    devices = i2c.scan()
    print(f"   Found {len(devices)} I2C device(s): {', '.join('0x{:02X}'.format(a) for a in devices)}")
    
    if VL53L0X_I2C_ADDR not in devices:
        print(f"   ERROR: VL53L0X not found at 0x{VL53L0X_I2C_ADDR:02X}")
        if use_display:
            display.update_display(header="VL53L0X Error", text="Not detected")
        return
    
    # Initialize sensor
    print(f"\n[2] Initializing VL53L0X sensor...")
    sensor = VL53L0X(i2c, addr=VL53L0X_I2C_ADDR)
    
    # Check model ID
    if not sensor.check_id():
        print("   ERROR: Model ID check failed!")
        if use_display:
            display.update_display(header="VL53L0X Error", text="ID check fail")
        return
    print("   Model ID: 0xEE (VL53L0X confirmed)")
    
    # Full initialization with calibration
    try:
        if use_display:
            display.update_display(header="VL53L0X Init", text="Calibrating...")
        sensor.init()
        print("   Initialization complete (SPAD + ref calibration done)")
    except VL53L0XError as e:
        print(f"   ERROR: {e}")
        if use_display:
            display.update_display(header="VL53L0X Error", text=str(e)[:20])
        return
    except Exception as e:
        print(f"   ERROR: Unexpected error: {e}")
        if use_display:
            display.update_display(header="VL53L0X Error", text="Init failed")
        return
    
    print("\n[3] Streaming measurements (5 per second)...")
    if use_display:
        display.update_display(header="VL53L0X Ready", text="Measuring...")
        time.sleep(1)
    
    try:
        measurement_count = 0
        while True:
            # Measure distance (returns cm or None)
            distance_cm = sensor.read_cm(timeout_ms=1000)
            
            # Format for display
            distance_text = format_distance(distance_cm)
            
            # Update OLED display (if available)
            if use_display:
                display.update_display(
                    header="VL53L0X ToF",
                    text=distance_text,
                    icon='robot'  # Optional icon
                )
            
            # Print to console
            measurement_count += 1
            if distance_cm is not None:
                distance_mm = distance_cm * 10
                print(f"[{measurement_count:04d}] Distance: {distance_mm:4.0f} mm ({distance_cm:.2f} cm)")
            else:
                print(f"[{measurement_count:04d}] Out of range")
            
            # Wait before next measurement (5 measurements per second)
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 40)
        print("Test stopped by user")
        if use_display:
            display.update_display(header="VL53L0X", text="Test stopped")
            time.sleep(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        if use_display:
            display.update_display(header="VL53L0X Error", text=str(e)[:20])
            time.sleep(2)


if __name__ == '__main__':
    main()
