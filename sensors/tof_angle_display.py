"""
ToF Angle Display Module
Shows wall angles from dual ToF sensors on OLED display

Displays:
- Visual angle indicator
- Angle in degrees
- Wall distance
- Navigation arrows
"""

import time
try:
    import display
except ImportError:
    display = None
from sensors.tof_angle_calculator import ToFAngleCalculator


def format_angle_for_display(angle_data):
    """
    Format angle data for OLED display (128x32 pixels).
    
    Returns:
        tuple: (line1, line2) - Two lines of text for display
    """
    if angle_data is None:
        return ("ToF Angle", "No data")
    
    angle = angle_data['angle_degrees']
    wall_dist = angle_data['wall_distance_cm']
    orientation = angle_data['orientation']
    
    # Line 1: Angle with visual indicator
    if orientation == 'straight':
        indicator = "|"  # Straight
    elif orientation == 'angled_left':
        indicator = "/"  # Angled left
    else:
        indicator = "\\"  # Angled right
    
    line1 = f"{indicator} {angle:+5.1f}deg"
    
    # Line 2: Distance and navigation arrow
    if wall_dist < 10:
        dist_str = f"{wall_dist:.1f}cm"
    else:
        dist_str = f"{int(wall_dist)}cm"
    
    # Navigation arrow
    if abs(angle) < 5:
        arrow = "^"  # Straight
    elif angle > 0:
        arrow = "<"  # Turn left
    else:
        arrow = ">"  # Turn right
    
    line2 = f"{arrow} {dist_str}"
    
    return (line1, line2)


def run_angle_display(sensor_spacing_cm=15.0, update_rate_hz=5):
    """
    Run continuous angle display on OLED.
    
    Args:
        sensor_spacing_cm: Distance between sensors in cm
        update_rate_hz: Display update rate (Hz)
    """
    print("=" * 60)
    print("ToF Angle Display")
    print("=" * 60)
    print(f"Sensor spacing: {sensor_spacing_cm} cm")
    print(f"Update rate: {update_rate_hz} Hz")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    # Check display
    use_display = display is not None and hasattr(display, 'display') and display.display is not None
    if not use_display:
        print("WARNING: OLED display not available - console output only")
    
    # Initialize angle calculator
    if use_display:
        display.update_display(header="ToF Init", text="Starting...")
    calc = ToFAngleCalculator(sensor_spacing_cm=sensor_spacing_cm)
    
    print("Initializing ToF sensors...")
    left_ok, right_ok = calc.init(verbose=True)
    
    if not (left_ok and right_ok):
        print("\nWARNING: Not all sensors initialized!")
        if use_display:
            display.update_display(
                header="ToF Error",
                text="Check wiring"
            )
            time.sleep(2)
        if not left_ok and not right_ok:
            return
    
    if use_display:
        display.update_display(header="ToF Ready", text="Starting...")
        time.sleep(1)
    
    print("\nDisplaying angles on OLED...")
    
    # Calculate update delay
    update_delay_ms = int(1000 / update_rate_hz)
    
    try:
        count = 0
        while True:
            # Read sensors and calculate angle
            angle_data = calc.read_with_angle(timeout_ms=1000)
            
            count += 1
            
            # Format for display
            line1, line2 = format_angle_for_display(angle_data)
            
            # Update OLED (if available)
            if use_display:
                display.update_display(
                    header="Wall Angle",
                    text=f"{line1}\n{line2}"
                )
            
            # Print to console
            if angle_data:
                print(f"[{count:04d}] Angle: {angle_data['angle_degrees']:+6.2f}deg | "
                      f"Dist: {angle_data['wall_distance_cm']:5.1f}cm | "
                      f"Orient: {angle_data['orientation']}")
            else:
                print(f"[{count:04d}] No valid reading")
            
            # Wait before next update
            time.sleep_ms(update_delay_ms)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        print("Stopped by user")
        if use_display:
            display.update_display(header="ToF Angle", text="Stopped")
            time.sleep(1)
    except Exception as e:
        print(f"\nError: {e}")
        if use_display:
            display.update_display(header="Error", text=str(e)[:20])
        import sys
        sys.print_exception(e)
        time.sleep(2)


def test_display_formats():
    """Test different angle display formats without sensors."""
    print("Testing display formats...")
    
    use_display = display is not None and hasattr(display, 'display') and display.display is not None
    if not use_display:
        print("ERROR: OLED display not available!")
        return
    
    test_cases = [
        {
            'angle_degrees': 0.0,
            'wall_distance_cm': 20.0,
            'orientation': 'straight',
            'is_perpendicular': True,
            'left_distance_cm': 20.0,
            'right_distance_cm': 20.0
        },
        {
            'angle_degrees': 15.5,
            'wall_distance_cm': 18.3,
            'orientation': 'angled_right',
            'is_perpendicular': False,
            'left_distance_cm': 15.0,
            'right_distance_cm': 25.0
        },
        {
            'angle_degrees': -12.8,
            'wall_distance_cm': 22.7,
            'orientation': 'angled_left',
            'is_perpendicular': False,
            'left_distance_cm': 30.0,
            'right_distance_cm': 15.0
        },
    ]
    
    for i, test_data in enumerate(test_cases):
        print(f"\nTest case {i+1}: {test_data['orientation']}")
        line1, line2 = format_angle_for_display(test_data)
        print(f"  Display: {line1} / {line2}")
        
        display.update_display(
            header="Test Mode",
            text=f"{line1}\n{line2}"
        )
        time.sleep(2)
    
    display.update_display(header="Test", text="Complete")


def show_angle_legend():
    """Show a quick legend on the display."""
    use_display = display is not None and hasattr(display, 'display') and display.display is not None
    if not use_display:
        print("ERROR: OLED display not available!")
        return
    
    legends = [
        ("Legend", "^ = straight"),
        ("Legend", "< = turn left"),
        ("Legend", "> = turn right"),
        ("Legend", "| = wall ahead"),
        ("Legend", "/ = wall left"),
        ("Legend", "\\ = wall right"),
    ]
    
    for header, text in legends:
        display.update_display(header=header, text=text)
        time.sleep(1.5)


if __name__ == '__main__':
    # Main program
    print("\nToF Angle Display")
    print("=" * 60)
    print("Options:")
    print("1. Run live angle display (default)")
    print("2. Test display formats")
    print("3. Show legend")
    print()
    
    # For MicroPython, just run the main display
    # If you want to test formats first, change this line
    run_angle_display(sensor_spacing_cm=15.0, update_rate_hz=5)
    
    # To test formats instead:
    # test_display_formats()
    
    # To show legend:
    # show_angle_legend()
