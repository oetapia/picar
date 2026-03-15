"""
HC-SR04 Ultrasonic Sensor Test Script
Pins: GP20 (TRIGGER), GP21 (ECHO)
Displays distance measurements on OLED screen
"""

import machine
import time
import display

# ========== HC-SR04 Configuration ==========
TRIGGER_PIN = 20  # GP20
ECHO_PIN = 21     # GP21
MAX_DISTANCE_CM = 400  # Maximum measurable distance
TIMEOUT_US = int(MAX_DISTANCE_CM * 58.8)  # Timeout for pulse measurement

# Initialize pins
trigger = machine.Pin(TRIGGER_PIN, machine.Pin.OUT)
echo = machine.Pin(ECHO_PIN, machine.Pin.IN)

# Ensure trigger starts low
trigger.low()
time.sleep_ms(100)


def measure_distance():
    """
    Measure distance using HC-SR04 ultrasonic sensor.
    
    Returns:
        float: Distance in centimeters, or None if measurement failed
    """
    # Ensure trigger is low
    trigger.low()
    time.sleep_us(2)
    
    # Send 10μs pulse to trigger
    trigger.high()
    time.sleep_us(10)
    trigger.low()
    
    try:
        # Measure the duration of the echo pulse (in microseconds)
        pulse_time = machine.time_pulse_us(echo, 1, TIMEOUT_US)
        
        if pulse_time < 0:
            # Timeout occurred
            return None
        
        # Calculate distance: distance = (pulse_time * speed_of_sound) / 2
        # Speed of sound = 343 m/s = 0.0343 cm/μs
        distance_cm = (pulse_time * 0.0343) / 2
        
        # Validate measurement range (2-400 cm typical for HC-SR04)
        if 2 <= distance_cm <= MAX_DISTANCE_CM:
            return distance_cm
        else:
            return None
            
    except Exception as e:
        print(f"Measurement error: {e}")
        return None


def format_distance(distance):
    """Format distance for display."""
    if distance is None:
        return "Out of range"
    elif distance < 10:
        return f"{distance:.2f} cm"
    elif distance < 100:
        return f"{distance:.1f} cm"
    else:
        return f"{int(distance)} cm"


def main():
    """Main loop: continuously measure and display distance."""
    print("HC-SR04 Ultrasonic Sensor Test")
    print(f"TRIGGER: GP{TRIGGER_PIN}, ECHO: GP{ECHO_PIN}")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    # Initialize display
    if display.display is None:
        print("Error: OLED display not initialized!")
        return
    
    display.update_display(header="HC-SR04 Ready", text="Starting...")
    time.sleep(1)
    
    try:
        measurement_count = 0
        while True:
            # Measure distance
            distance = measure_distance()
            
            # Format for display
            distance_text = format_distance(distance)
            
            # Update OLED display
            display.update_display(
                header="HC-SR04 Sensor",
                text=distance_text,
                icon='robot'  # Optional icon
            )
            
            # Print to console
            measurement_count += 1
            if distance is not None:
                print(f"[{measurement_count:04d}] Distance: {distance:.2f} cm")
            else:
                print(f"[{measurement_count:04d}] Out of range or error")
            
            # Wait before next measurement (5 measurements per second)
            time.sleep_ms(200)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 40)
        print("Test stopped by user")
        display.update_display(header="HC-SR04", text="Test stopped")
        time.sleep(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        display.update_display(header="HC-SR04 Error", text=str(e)[:20])
        time.sleep(2)


if __name__ == '__main__':
    main()
