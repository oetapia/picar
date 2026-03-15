# Sensor Diagnostic Tools - Unified Standards

## Purpose
This document defines the unified structure and standards for all sensor diagnostic test scripts in the `/sensors` directory.

## File Naming Convention
- **Test/Diagnostic scripts**: `<sensor_name>_test.py`
- **Display variants**: `<sensor_name>_display.py`
- **Calculator/Processing**: `<sensor_name>_calculator.py`
- **Core modules**: `<sensor_name>_sensor.py` or just `<sensor_name>.py`
- **Utility scripts**: Descriptive names (e.g., `i2c_scan.py`)

## Standard Structure Template

```python
"""
<Sensor Name> Test Script
<Brief description>
Pins: <List GPIO pins used>
Communication: <I2C/SPI/Digital/etc and details>
"""

import machine
import time
import display  # For OLED display integration

# ========== <SENSOR> Configuration ==========
# Pin definitions
PIN_1 = X
PIN_2 = Y

# Sensor settings
SENSOR_ADDR = 0xXX  # For I2C sensors
MEASUREMENT_RATE = 5  # Hz (standard: 5 measurements per second)

# Constants
MAX_VALUE = 100


def format_for_display(value):
    """
    Format sensor reading for OLED display.
    
    Args:
        value: Sensor reading
        
    Returns:
        str: Formatted string for display
    """
    if value is None:
        return "No data"
    # Format logic here
    return f"{value:.2f}"


def main():
    """Main test loop: initialize sensor, measure continuously, display results."""
    # ========== Header ==========
    print("=" * 60)
    print("<Sensor Name> Test")
    print("=" * 60)
    print("Configuration:")
    print(f"  Pin 1: GP{PIN_1}")
    print(f"  Pin 2: GP{PIN_2}")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    # ========== Display Check ==========
    if display.display is None:
        print("WARNING: OLED display not initialized!")
        print("Continuing with console output only...")
    else:
        display.update_display(header="<Sensor> Init", text="Starting...")
        time.sleep(1)
    
    # ========== Sensor Initialization ==========
    print("\n[1] Initializing sensor...")
    try:
        # Sensor init code here
        sensor = None  # Replace with actual sensor object
        print("   ✓ Sensor initialized successfully")
    except Exception as e:
        print(f"   ✗ Initialization failed: {e}")
        if display.display:
            display.update_display(header="<Sensor> Error", text="Init failed")
        return
    
    # ========== Main Measurement Loop ==========
    print("\n[2] Starting measurements...")
    if display.display:
        display.update_display(header="<Sensor> Ready", text="Measuring...")
        time.sleep(0.5)
    
    measurement_delay_ms = int(1000 / MEASUREMENT_RATE)
    
    try:
        count = 0
        while True:
            # Read sensor
            value = None  # Replace with actual sensor read
            
            count += 1
            
            # Update OLED display (if available)
            if display.display:
                display_text = format_for_display(value)
                display.update_display(
                    header="<Sensor Name>",
                    text=display_text,
                    icon='robot'  # Optional
                )
            
            # Print to console
            if value is not None:
                print(f"[{count:04d}] Value: {value:.2f}")
            else:
                print(f"[{count:04d}] No reading")
            
            # Wait before next measurement
            time.sleep_ms(measurement_delay_ms)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        print("✓ Test stopped by user")
        if display.display:
            display.update_display(header="<Sensor>", text="Stopped")
            time.sleep(1)
    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        if display.display:
            display.update_display(header="Error", text=str(e)[:20])
        import sys
        sys.print_exception(e)
        time.sleep(2)


if __name__ == '__main__':
    main()
```

## Key Standards

### 1. Import Order
```python
import machine      # Hardware access
import time         # Timing
import math         # If needed for calculations
import display      # OLED display (standard module)
# Then any sensor-specific imports
```

### 2. Configuration Section
- Use ALL_CAPS for constants
- Group by category with comments
- Include pin definitions, addresses, timing settings

### 3. Display Integration
- **Always check** if display is available
- Degrade gracefully to console-only if display not available
- Use standard `display.update_display()` function
- Format: header (sensor name), text (reading), optional icon

### 4. Console Output Format
- Header: `=` border (60 chars)
- Sections: Numbered [1], [2], etc.
- Measurements: `[nnnn]` counter with formatted value
- Indented details: 2-4 spaces with `✓`/`✗` symbols
- Footer: `-` border (60 chars)

### 5. Error Handling
- Try/except around initialization
- Try/except around main loop
- KeyboardInterrupt for clean exit
- Display error messages on both console and OLED

### 6. Measurement Rate
- **Standard: 5 Hz** (200ms delay between measurements)
- Use `MEASUREMENT_RATE` constant for easy adjustment
- Calculate delay: `measurement_delay_ms = int(1000 / MEASUREMENT_RATE)`

### 7. Function Naming
- `main()` - Main test loop
- `format_for_display()` - Format data for OLED
- `format_<type>()` - Other formatting functions
- Sensor classes: PascalCase (e.g., `MPU6050`)
- Helper functions: snake_case

### 8. Comments
- Module docstring at top
- Section comments with `==========`
- Inline comments for complex logic
- Clear parameter/return documentation

## File Categories

### A. Core Test Files (Follow template exactly)
- `hcsr04_test.py` ✓
- `mpu6050_test.py` ✓
- `vl53l0x_test.py` ✓
- `dual_tof_test.py` ✓
- `ir_sensor_test.py` (to be created/updated)

### B. Display Variants (Extended template)
- `tof_angle_display.py` ✓
- Additional display variants as needed

### C. Processing Modules (Flexible structure)
- `dual_tof_sensor.py` (sensor manager)
- `tof_angle_calculator.py` (processing logic)

### D. Utility Scripts (Minimal structure)
- `i2c_scan.py` (simple utility)
- `payload_sensor.py` (API module)

## Migration Checklist

When updating old diagnostic files:
- [ ] Update module docstring
- [ ] Organize imports
- [ ] Add configuration section with constants
- [ ] Check display availability before use
- [ ] Standardize console output format
- [ ] Use 5 Hz measurement rate (unless sensor-specific reason)
- [ ] Add proper error handling
- [ ] Use Unicode symbols (✓/✗) for status
- [ ] Add measurement counter [nnnn]
- [ ] Test on hardware

## Benefits of Unified Structure

1. **Consistency**: Easy to understand any test file
2. **Maintainability**: Standard patterns for updates
3. **Debugging**: Predictable behavior and error messages
4. **Reusability**: Common code patterns
5. **Documentation**: Self-documenting code structure
