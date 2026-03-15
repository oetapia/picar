"""
Dual ToF Sensor Test Script
Simple test to verify both VL53L0X sensors are working
"""

import sys
sys.path.insert(0, '/sensors')  # For mpremote run from root

from dual_tof_sensor import DualToFSensor
import time


def main():
    """Run dual sensor test."""
    print("=" * 60)
    print("Dual VL53L0X ToF Sensor Test")
    print("=" * 60)
    print("Hardware Configuration:")
    print("  Left Sensor (Front Left):   GPIO 6 (SDA), GPIO 7 (SCL)")
    print("  Right Sensor (Front Right): GPIO 20 (SDA), GPIO 21 (SCL)")
    print("=" * 60)
    
    # Create and initialize sensors
    sensors = DualToFSensor()
    print("\nInitializing sensors...")
    left_ok, right_ok = sensors.init(verbose=True)
    
    if not sensors.initialized:
        print("\n✗ ERROR: Failed to initialize any sensors!")
        print("  Check wiring and connections.")
        return
    
    # Show status
    status = sensors.get_status()
    print(f"\nStatus:")
    print(f"  Left sensor:  {'✓ Available' if status['left_available'] else '✗ Not available'}")
    print(f"  Right sensor: {'✓ Available' if status['right_available'] else '✗ Not available'}")
    
    print("\n" + "=" * 60)
    print("Starting continuous measurements...")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        count = 0
        while True:
            # Read both sensors
            left_cm, right_cm = sensors.read_distances_cm(timeout_ms=1000)
            
            count += 1
            
            # Format and display
            reading = sensors.format_reading(left_cm, right_cm)
            print(f"[{count:04d}] {reading}")
            
            # Show detailed info every 20 readings
            if count % 20 == 0:
                print(f"       ├─ Left:  {f'{left_cm:.2f} cm' if left_cm else 'Out of range'}")
                print(f"       └─ Right: {f'{right_cm:.2f} cm' if right_cm else 'Out of range'}")
            
            # 5 Hz measurement rate
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("✓ Test stopped by user")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import sys
        sys.print_exception(e)


if __name__ == '__main__':
    main()
