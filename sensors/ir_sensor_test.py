"""
IR Break-Beam Sensor Test Script
Tests infrared break-beam sensors for payload detection
Pins: GP3 (Left Front), GP7 (Right Front), GP8 (Left Back), GP4 (Right Back)
Communication: Digital GPIO
"""

import machine
import time
import display

# ========== IR Sensor Configuration ==========
# Pin definitions
IR_LEFT_FRONT_PIN = 3
IR_RIGHT_FRONT_PIN = 7
IR_LEFT_BACK_PIN = 8
IR_RIGHT_BACK_PIN = 4

# Sensor settings
MEASUREMENT_RATE = 5  # Hz (5 measurements per second)
USE_PULL_UP = True    # Sensors require pull-up resistors


class IRSensorArray:
    """Manages multiple IR break-beam sensors."""
    
    def __init__(self):
        """Initialize all IR sensors."""
        self.sensors = {
            'left_front': machine.Pin(IR_LEFT_FRONT_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
            'right_front': machine.Pin(IR_RIGHT_FRONT_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
            'left_back': machine.Pin(IR_LEFT_BACK_PIN, machine.Pin.IN, machine.Pin.PULL_UP),
            'right_back': machine.Pin(IR_RIGHT_BACK_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        }
        self.last_state = {name: False for name in self.sensors}
    
    def read_all(self):
        """
        Read all IR sensors.
        
        Returns:
            dict: Sensor name -> beam_broken (True if beam is broken)
        """
        return {name: pin.value() == 0 for name, pin in self.sensors.items()}
    
    def get_changes(self):
        """
        Get sensors that changed state since last read.
        
        Returns:
            dict: Sensor name -> new_state (for changed sensors only)
        """
        current = self.read_all()
        changes = {}
        
        for name, state in current.items():
            if state != self.last_state[name]:
                changes[name] = state
        
        self.last_state = current
        return changes
    
    def count_broken(self):
        """
        Count how many beams are currently broken.
        
        Returns:
            int: Number of broken beams
        """
        states = self.read_all()
        return sum(states.values())


def format_for_display(sensor_states):
    """
    Format IR sensor states for OLED display.
    
    Args:
        sensor_states: Dictionary of sensor states
        
    Returns:
        str: Formatted string for display (2 lines)
    """
    # Symbols: ● = broken, ○ = clear
    lf = "●" if sensor_states['left_front'] else "○"
    rf = "●" if sensor_states['right_front'] else "○"
    lb = "●" if sensor_states['left_back'] else "○"
    rb = "●" if sensor_states['right_back'] else "○"
    
    line1 = f"F: {lf} L  R {rf}"
    line2 = f"B: {lb} L  R {rb}"
    
    return f"{line1}\n{line2}"


def main():
    """Main test loop: initialize sensors, monitor continuously, display status."""
    # ========== Header ==========
    print("=" * 60)
    print("IR Break-Beam Sensor Array Test")
    print("=" * 60)
    print("Configuration:")
    print(f"  Left Front:  GP{IR_LEFT_FRONT_PIN}")
    print(f"  Right Front: GP{IR_RIGHT_FRONT_PIN}")
    print(f"  Left Back:   GP{IR_LEFT_BACK_PIN}")
    print(f"  Right Back:  GP{IR_RIGHT_BACK_PIN}")
    print("Signal: 0 = beam broken, 1 = beam clear")
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    # ========== Display Check ==========
    if display.display is None:
        print("WARNING: OLED display not initialized!")
        print("Continuing with console output only...")
    else:
        display.update_display(header="IR Sensors Init", text="Starting...")
        time.sleep(1)
    
    # ========== Sensor Initialization ==========
    print("\n[1] Initializing IR sensors...")
    try:
        ir_array = IRSensorArray()
        print("   ✓ All 4 IR sensors initialized successfully")
        print("   Sensors configured with pull-up resistors")
    except Exception as e:
        print(f"   ✗ Initialization failed: {e}")
        if display.display:
            display.update_display(header="IR Error", text="Init failed")
        return
    
    # ========== Main Monitoring Loop ==========
    print("\n[2] Monitoring IR sensors...")
    if display.display:
        display.update_display(header="IR Ready", text="Monitoring...")
        time.sleep(0.5)
    
    measurement_delay_ms = int(1000 / MEASUREMENT_RATE)
    
    try:
        count = 0
        while True:
            # Read all sensors
            states = ir_array.read_all()
            changes = ir_array.get_changes()
            broken_count = ir_array.count_broken()
            
            count += 1
            
            # Update OLED display (if available)
            if display.display:
                display_text = format_for_display(states)
                display.update_display(
                    header=f"IR Sensors [{broken_count}]",
                    text=display_text
                )
            
            # Print to console (only when state changes)
            if changes:
                status_str = " | ".join([
                    f"{name}={'BROKEN' if state else 'clear'}"
                    for name, state in changes.items()
                ])
                print(f"[{count:04d}] ⚡ {status_str}")
            
            # Print summary every 50 readings
            if count % 50 == 0:
                status_list = [
                    f"{name}={'●' if state else '○'}"
                    for name, state in states.items()
                ]
                print(f"[{count:04d}] Status: {' | '.join(status_list)} | "
                      f"Broken: {broken_count}/4")
            
            # Wait before next measurement
            time.sleep_ms(measurement_delay_ms)
            
    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        print("✓ Test stopped by user")
        if display.display:
            display.update_display(header="IR Sensors", text="Stopped")
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
