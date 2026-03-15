"""
I2C Bus Scanner Utility
Scans I2C bus and reports all detected device addresses
Pins: Configurable (default GP20/GP21 for I2C0, GP18/GP19 for I2C1)
Communication: I2C
"""

import machine
import time
import display

# ========== I2C Scanner Configuration ==========
# Default bus configuration (can be changed)
I2C_BUS_ID = 0        # I2C bus number (0 or 1)
I2C_SDA_PIN = 20      # SDA pin
I2C_SCL_PIN = 21      # SCL pin
I2C_FREQ = 400_000    # 400kHz (standard fast mode)

# Known device addresses for reference
KNOWN_DEVICES = {
    0x29: "VL53L0X/VL53L1X ToF Sensor",
    0x68: "MPU6050 IMU / DS1307 RTC",
    0x69: "MPU6050 IMU (alt address)",
    0x3C: "SSD1306 OLED Display (128x64)",
    0x3D: "SSD1306 OLED Display (alt)",
    0x76: "BMP280 Pressure Sensor",
    0x77: "BMP280 Pressure Sensor (alt)",
}


def scan_i2c_bus(i2c_bus):
    """
    Scan I2C bus for devices.
    
    Args:
        i2c_bus: I2C bus object
        
    Returns:
        list: List of detected device addresses
    """
    try:
        devices = i2c_bus.scan()
        return devices
    except Exception as e:
        print(f"   ✗ Scan error: {e}")
        return []


def format_for_display(device_count, last_addr=None):
    """
    Format scan results for OLED display.
    
    Args:
        device_count: Number of devices found
        last_addr: Last detected device address (optional)
        
    Returns:
        str: Formatted string for display
    """
    if device_count == 0:
        return "No devices\nfound"
    elif device_count == 1:
        return f"1 device\n0x{last_addr:02X}"
    else:
        line2 = f"0x{last_addr:02X}" if last_addr else "multiple"
        return f"{device_count} devices\n{line2}"


def identify_device(addr):
    """
    Identify device by address if known.
    
    Args:
        addr: I2C address
        
    Returns:
        str: Device name or "Unknown"
    """
    return KNOWN_DEVICES.get(addr, "Unknown device")


def main():
    """Main scan loop: scan I2C bus and display results."""
    # ========== Header ==========
    print("=" * 60)
    print("I2C Bus Scanner")
    print("=" * 60)
    print("Configuration:")
    print(f"  I2C Bus: {I2C_BUS_ID}")
    print(f"  SDA Pin: GP{I2C_SDA_PIN}")
    print(f"  SCL Pin: GP{I2C_SCL_PIN}")
    print(f"  Frequency: {I2C_FREQ/1000:.0f} kHz")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    # ========== Display Check ==========
    if display.display is None:
        print("WARNING: OLED display not initialized!")
        print("Continuing with console output only...")
    else:
        display.update_display(header="I2C Scanner", text="Starting...")
        time.sleep(1)
    
    # ========== I2C Initialization ==========
    print("\n[1] Initializing I2C bus...")
    try:
        i2c = machine.I2C(
            I2C_BUS_ID,
            sda=machine.Pin(I2C_SDA_PIN),
            scl=machine.Pin(I2C_SCL_PIN),
            freq=I2C_FREQ
        )
        time.sleep_ms(10)
        print("   ✓ I2C bus initialized successfully")
    except Exception as e:
        print(f"   ✗ Initialization failed: {e}")
        if display.display:
            display.update_display(header="I2C Error", text="Init failed")
        return
    
    # ========== Initial Scan ==========
    print("\n[2] Performing initial scan...")
    devices = scan_i2c_bus(i2c)
    
    if devices:
        print(f"   ✓ Found {len(devices)} device(s):")
        for addr in devices:
            device_name = identify_device(addr)
            print(f"      0x{addr:02X} ({addr:3d}) - {device_name}")
    else:
        print("   ✗ No I2C devices found")
        print("      Check wiring and power connections")
    
    # ========== Continuous Monitoring ==========
    print("\n[3] Monitoring I2C bus (rescans every 2 seconds)...")
    print("   Changes will be reported automatically")
    print()
    
    if display.display:
        display.update_display(header="I2C Scanner", text="Scanning...")
        time.sleep(0.5)
    
    try:
        scan_count = 0
        last_devices = set(devices)
        
        while True:
            scan_count += 1
            
            # Scan bus
            current_devices = set(scan_i2c_bus(i2c))
            
            # Check for changes
            added = current_devices - last_devices
            removed = last_devices - current_devices
            
            # Report changes
            if added or removed:
                print(f"[{scan_count:04d}] ⚡ Bus changed:")
                for addr in added:
                    device_name = identify_device(addr)
                    print(f"   ✓ Added: 0x{addr:02X} - {device_name}")
                for addr in removed:
                    device_name = identify_device(addr)
                    print(f"   ✗ Removed: 0x{addr:02X} - {device_name}")
            
            # Update OLED display (if available)
            if display.display:
                device_count = len(current_devices)
                last_addr = list(current_devices)[-1] if current_devices else None
                display_text = format_for_display(device_count, last_addr)
                display.update_display(
                    header=f"I2C Scan #{scan_count}",
                    text=display_text
                )
            
            # Periodic status (every 10 scans)
            if scan_count % 10 == 0:
                if current_devices:
                    addr_list = ", ".join(f"0x{addr:02X}" for addr in sorted(current_devices))
                    print(f"[{scan_count:04d}] Status: {len(current_devices)} device(s) - {addr_list}")
                else:
                    print(f"[{scan_count:04d}] Status: No devices detected")
            
            last_devices = current_devices
            
            # Wait 2 seconds before next scan
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        print("✓ Scanner stopped by user")
        print(f"Final device count: {len(last_devices)}")
        if display.display:
            display.update_display(header="I2C Scanner", text="Stopped")
            time.sleep(1)
    except Exception as e:
        print(f"\n✗ Error during scanning: {e}")
        if display.display:
            display.update_display(header="Error", text=str(e)[:20])
        import sys
        sys.print_exception(e)
        time.sleep(2)


def quick_scan():
    """Perform a quick one-time scan without continuous monitoring."""
    print("I2C Quick Scan")
    print("-" * 60)
    
    i2c = machine.I2C(
        I2C_BUS_ID,
        sda=machine.Pin(I2C_SDA_PIN),
        scl=machine.Pin(I2C_SCL_PIN),
        freq=I2C_FREQ
    )
    
    devices = scan_i2c_bus(i2c)
    
    if devices:
        print(f"Found {len(devices)} device(s):")
        for addr in devices:
            device_name = identify_device(addr)
            print(f"  0x{addr:02X} ({addr:3d}) - {device_name}")
    else:
        print("No I2C devices found")
        print("Check wiring and power connections")


if __name__ == '__main__':
    # Run continuous monitoring by default
    main()
    
    # For quick scan only, uncomment:
    # quick_scan()
