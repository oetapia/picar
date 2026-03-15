"""
ToF Angle Calculator Module
Calculates wall/obstacle angles using dual VL53L0X ToF sensor measurements

Uses trigonometry to determine:
- Angle of wall relative to car heading
- Whether car is facing wall straight-on
- Direction of wall orientation (left/right)

Geometry:
    Left Sensor (L)        Right Sensor (R)
         |                      |
         |                      |
         +--------D-------------+  <- Car front (sensors separated by distance D)
          \                    /
           \                  /
            \                /
          L_dist          R_dist
              \          /
               \        /
                \      /
                 \    /
                  \  /
                   \/
              Wall/Obstacle

If L_dist < R_dist: Wall is angled to the left
If L_dist > R_dist: Wall is angled to the right
If L_dist ≈ R_dist: Wall is perpendicular (straight ahead)
"""

import sys
sys.path.insert(0, '/sensors')  # For mpremote run from root

import math
try:
    from .dual_tof_sensor import DualToFSensor
except ImportError:
    from dual_tof_sensor import DualToFSensor


class ToFAngleCalculator:
    """Calculate angles and orientations from dual ToF sensor readings."""
    
    def __init__(self, sensor_spacing_cm=15.0):
        """
        Initialize angle calculator.
        
        Args:
            sensor_spacing_cm: Distance between left and right sensors in cm
                              (measure the distance between sensor centers on your car)
        """
        self.sensor_spacing_cm = sensor_spacing_cm
        self.tof_sensor = DualToFSensor()
        
    def init(self, verbose=True):
        """Initialize the ToF sensors."""
        return self.tof_sensor.init(verbose=verbose)
    
    def calculate_wall_angle(self, left_cm, right_cm):
        """
        Calculate the angle of a wall relative to the car's forward direction.
        
        Args:
            left_cm: Distance from left sensor to wall (cm)
            right_cm: Distance from right sensor to wall (cm)
            
        Returns:
            dict with:
                - angle_degrees: Angle in degrees (positive = wall angled right, negative = left)
                - is_perpendicular: True if wall is roughly perpendicular (within 5°)
                - orientation: 'straight', 'angled_left', or 'angled_right'
                - wall_distance_cm: Approximate perpendicular distance to wall
                
            Returns None if measurements are invalid
        """
        if left_cm is None or right_cm is None:
            return None
        
        # Handle edge cases
        if left_cm <= 0 or right_cm <= 0:
            return None
        
        # Calculate the difference
        distance_diff = right_cm - left_cm
        
        # Calculate angle using arctangent
        # tan(angle) = opposite / adjacent = distance_diff / sensor_spacing
        angle_radians = math.atan2(distance_diff, self.sensor_spacing_cm)
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
        # Use the closer sensor and adjust for angle
        min_distance = min(left_cm, right_cm)
        wall_distance_cm = min_distance * math.cos(angle_radians)
        
        return {
            'angle_degrees': angle_degrees,
            'is_perpendicular': is_perpendicular,
            'orientation': orientation,
            'wall_distance_cm': wall_distance_cm,
            'left_distance_cm': left_cm,
            'right_distance_cm': right_cm
        }
    
    def read_with_angle(self, timeout_ms=1000):
        """
        Read sensors and calculate angle in one call.
        
        Args:
            timeout_ms: Timeout for sensor reading
            
        Returns:
            dict: Angle calculation results (or None if reading failed)
        """
        left_cm, right_cm = self.tof_sensor.read_distances_cm(timeout_ms)
        return self.calculate_wall_angle(left_cm, right_cm)
    
    def format_angle_info(self, angle_data):
        """
        Format angle data for display.
        
        Args:
            angle_data: Dictionary from calculate_wall_angle()
            
        Returns:
            str: Formatted string for display
        """
        if angle_data is None:
            return "No data available"
        
        angle = angle_data['angle_degrees']
        orientation = angle_data['orientation']
        wall_dist = angle_data['wall_distance_cm']
        
        # Create orientation symbol
        if orientation == 'straight':
            symbol = "═══║"  # Straight wall
        elif orientation == 'angled_left':
            symbol = " ╱ "  # Angled left
        else:
            symbol = " ╲ "  # Angled right
        
        return f"{symbol} {angle:+6.2f}° | Dist: {wall_dist:5.1f}cm"
    
    def get_navigation_hint(self, angle_data, threshold_angle=10.0):
        """
        Get navigation hint based on wall angle.
        
        Args:
            angle_data: Dictionary from calculate_wall_angle()
            threshold_angle: Angle threshold for corrections (degrees)
            
        Returns:
            str: Navigation hint ('turn_left', 'turn_right', 'straight', or 'no_data')
        """
        if angle_data is None:
            return 'no_data'
        
        angle = angle_data['angle_degrees']
        
        if angle_data['is_perpendicular']:
            return 'straight'
        elif angle > threshold_angle:
            return 'turn_left'  # Wall angled right, turn left to face it
        elif angle < -threshold_angle:
            return 'turn_right'  # Wall angled left, turn right to face it
        else:
            return 'straight'


def test_angle_calculator():
    """Test function demonstrating angle calculation."""
    import time
    
    print("=" * 70)
    print("ToF Angle Calculator Test")
    print("=" * 70)
    print("This module calculates wall angles from dual ToF sensor readings")
    print()
    
    # Get sensor spacing from user (or use default)
    sensor_spacing = 15.0  # cm - adjust this to match your car
    print(f"Sensor spacing: {sensor_spacing} cm")
    print("(Edit SENSOR_SPACING in code if your sensors are different)")
    print()
    
    # Initialize calculator
    calc = ToFAngleCalculator(sensor_spacing_cm=sensor_spacing)
    print("Initializing sensors...")
    left_ok, right_ok = calc.init(verbose=True)
    
    if not (left_ok and right_ok):
        print("\n⚠ WARNING: Not all sensors initialized!")
        print("Angle calculation requires both sensors.")
        if not left_ok and not right_ok:
            return
    
    print("\n" + "=" * 70)
    print("Reading angles continuously...")
    print("Legend:")
    print("  ═══║ = Wall straight ahead")
    print("   ╱  = Wall angled to the left")
    print("   ╲  = Wall angled to the right")
    print("Press Ctrl+C to stop")
    print("=" * 70)
    
    try:
        count = 0
        while True:
            # Read sensors and calculate angle
            angle_data = calc.read_with_angle(timeout_ms=1000)
            
            count += 1
            
            if angle_data:
                # Format output
                angle_str = calc.format_angle_info(angle_data)
                nav_hint = calc.get_navigation_hint(angle_data)
                
                # Print measurement
                print(f"[{count:04d}] {angle_str}")
                
                # Show detailed info every 10 readings
                if count % 10 == 0:
                    print(f"       Left:  {angle_data['left_distance_cm']:.1f} cm")
                    print(f"       Right: {angle_data['right_distance_cm']:.1f} cm")
                    print(f"       Angle: {angle_data['angle_degrees']:+.2f}°")
                    print(f"       Nav:   {nav_hint.upper()}")
            else:
                print(f"[{count:04d}] No valid reading")
            
            # 5 Hz update rate
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("✓ Test stopped by user")
        print("=" * 70)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import sys
        sys.print_exception(e)


def demonstrate_calculations():
    """Demonstrate angle calculations with example values."""
    print("=" * 70)
    print("Angle Calculation Examples")
    print("=" * 70)
    print()
    
    calc = ToFAngleCalculator(sensor_spacing_cm=10.5)
    
    test_cases = [
        (20.0, 20.0, "Wall straight ahead"),
        (15.0, 25.0, "Wall angled to the right"),
        (25.0, 15.0, "Wall angled to the left"),
        (10.0, 30.0, "Sharp angle to the right"),
        (30.0, 10.0, "Sharp angle to the left"),
    ]
    
    for left, right, description in test_cases:
        result = calc.calculate_wall_angle(left, right)
        if result:
            print(f"{description}:")
            print(f"  Left: {left} cm, Right: {right} cm")
            print(f"  → Angle: {result['angle_degrees']:+.2f}°")
            print(f"  → Orientation: {result['orientation']}")
            print(f"  → Wall distance: {result['wall_distance_cm']:.1f} cm")
            print()


if __name__ == '__main__':
    # For MicroPython, just run the live test directly
    # input() is not available in MicroPython REPL
    print("\nToF Angle Calculator")
    print("Running live test mode...")
    print()
    test_angle_calculator()
    
    # To run examples instead, comment above and uncomment below:
    # demonstrate_calculations()
