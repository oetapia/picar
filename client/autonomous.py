"""
Autonomous Navigation - Refactored to Use Hooks

This is the refactored version that uses autonomous_hooks.py for all logic.
The original monolithic version is preserved in autonomous_legacy.py.

Key improvements:
- Uses shared hooks for logic
- Much smaller file (~300 lines vs 600)
- Same behavior and interface
- Easier to maintain (fix bugs in hooks, both versions benefit)
"""

import sys
import tty
import termios
import threading
import time
from typing import Optional

from picar_client import PicarClient
import autonomous_hooks as hooks


class AutonomousDriver:
    """
    Bidirectional autonomous navigation using hooks for all logic.
    
    This refactored version uses autonomous_hooks.py for all navigation logic,
    making it easier to maintain and share fixes with autonomous_fsm.py.
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread: Optional[threading.Thread] = None
        self._current_direction = "stopped"
        self._last_front_dist: Optional[float] = None
        self._last_measurement_time: Optional[float] = None
        self._emergency_stop_active = False
        self._display_update_counter = 0

    def start(self):
        """Start autonomous navigation."""
        if self.autonomous:
            return
        
        self.autonomous = True
        self._current_direction = "stopped"
        self._last_front_dist = None
        self._last_measurement_time = None
        self._emergency_stop_active = False
        self._display_update_counter = 0
        
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        try:
            self.client.send_text("AUTO MODE\nStarting...")
        except:
            pass
        
        print("\r🚗 Autonomous ON - Using Hooks")
        print("\r   Shared logic with FSM version")

    def stop(self):
        """Stop autonomous navigation."""
        self.autonomous = False
        hooks.execute_stop(self.client)
        self._current_direction = "stopped"
        
        try:
            self.client.send_text("AUTO MODE\nStopped")
        except:
            pass
        
        print("\r🛑 Autonomous OFF - Vehicle stopped")

    def _loop(self):
        """Main navigation loop."""
        while self.autonomous:
            loop_start = time.time()
            
            try:
                # Read sensors using hooks
                left, right, tof_success = hooks.read_tof_sensors(self.client)
                if not tof_success:
                    print("\r⚠️  ToF sensors unavailable")
                    hooks.execute_stop(self.client)
                    time.sleep(0.5)
                    continue
                
                rear, _ = hooks.read_ultrasonic_sensor(self.client)
                
                # Calculate clearances
                front_clearance, rear_clearance = hooks.calculate_clearances(left, right, rear)
                
                # Calculate approach rate
                current_time = time.time()
                time_delta = 0
                if self._last_measurement_time:
                    time_delta = current_time - self._last_measurement_time
                
                approach_rate = hooks.calculate_approach_rate(
                    front_clearance,
                    self._last_front_dist,
                    time_delta
                )
                
                self._last_front_dist = front_clearance
                self._last_measurement_time = current_time
                
                # PRIORITY 1: Emergency checks
                if hooks.check_emergency_forward(self._current_direction, front_clearance):
                    print(f"\r🚨 EMERGENCY STOP! Front:{front_clearance:.0f}cm")
                    hooks.execute_stop(self.client)
                    self._emergency_stop_active = True
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue
                
                if hooks.check_emergency_reverse(self._current_direction, rear_clearance):
                    print(f"\r🚨 EMERGENCY STOP REVERSE! Rear:{rear_clearance:.0f}cm")
                    hooks.execute_stop(self.client)
                    self._emergency_stop_active = True
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue
                
                # Predictive braking
                if hooks.check_pre_brake(self._current_direction, approach_rate):
                    print(f"\r⚡ PRE-BRAKE! Approaching at {-approach_rate:.0f}cm/s")
                    hooks.execute_pre_brake(self.client)
                    time.sleep(0.05)
                
                # Clear emergency flag if safe
                if hooks.should_clear_emergency(front_clearance, rear_clearance):
                    self._emergency_stop_active = False
                
                # Update display (throttled)
                self._display_update_counter += 1
                if self._display_update_counter >= 4:
                    self._display_update_counter = 0
                    self._update_display(left, right, rear, front_clearance)
                
                # Navigate
                self._navigate(left, right, rear, front_clearance, rear_clearance, approach_rate)
                
            except Exception as e:
                print(f"\r⚠️  Error: {e}")
                hooks.execute_stop(self.client)
                self._emergency_stop_active = False
                time.sleep(0.5)
                continue
            
            # Maintain poll rate
            loop_duration = time.time() - loop_start
            sleep_time = max(0, hooks.POLL_INTERVAL - loop_duration)
            time.sleep(sleep_time)

    def _navigate(self, left: float, right: float, rear: float, 
                  front_clearance: float, rear_clearance: float, approach_rate: float):
        """Navigation decision logic using hooks."""
        
        # TRAPPED check
        if hooks.check_trapped(front_clearance, rear_clearance):
            if self._current_direction != "stopped":
                hooks.execute_stop(self.client)
                self._current_direction = "stopped"
                print(f"\r🚨 TRAPPED! F:{front_clearance:.0f}cm R:{rear_clearance:.0f}cm")
            return
        
        # RECOVERY from emergency
        if self._emergency_stop_active:
            margin = 5
            if front_clearance < hooks.EMERGENCY_STOP_DIST + margin and rear_clearance > hooks.REAR_CAUTION_DIST:
                self._move_backward(left, right, rear_clearance, hooks.REVERSE_SLOW)
                return
            elif rear_clearance < hooks.EMERGENCY_STOP_DIST + margin and front_clearance > hooks.EMERGENCY_STOP_DIST + margin:
                self._move_forward(left, right, hooks.CRAWL_SPEED, "RECOVER")
                return
            elif front_clearance < hooks.EMERGENCY_STOP_DIST + margin and rear_clearance < hooks.EMERGENCY_STOP_DIST + margin:
                return
        
        # DECISION TREE (using hooks for decisions)
        if hooks.should_cruise_forward(front_clearance):
            self._move_forward(left, right, hooks.CRUISE_SPEED, "CRUISE")
        
        elif hooks.should_medium_forward(front_clearance):
            self._move_forward(left, right, hooks.MEDIUM_SPEED, "MEDIUM")
        
        elif hooks.should_slow_forward(front_clearance):
            self._move_forward(left, right, hooks.SLOW_SPEED, "SLOW")
        
        elif hooks.should_crawl_forward(front_clearance):
            # Check if should reverse instead
            if hooks.should_tactical_reverse(front_clearance, rear_clearance, approach_rate):
                self._move_backward(left, right, rear_clearance, hooks.REVERSE_SLOW)
            else:
                self._move_forward(left, right, hooks.CRAWL_SPEED, "CRAWL")
        
        elif hooks.should_emergency_reverse(front_clearance, rear_clearance):
            self._move_backward(left, right, rear_clearance, hooks.REVERSE_SLOW)
        
        else:
            # No safe forward movement and not critical enough for reverse - STOP
            if self._current_direction != "stopped":
                hooks.execute_stop(self.client)
                self._current_direction = "stopped"
                print(f"\r⚠️ No safe path: F:{front_clearance:.0f}cm R:{rear_clearance:.0f}cm")

    def _move_forward(self, left: float, right: float, speed: int, mode: str):
        """Execute forward movement using hooks."""
        if self._emergency_stop_active:
            return
        
        hooks.execute_forward(self.client, speed, left, right)
        self._current_direction = "forward"
        
        servo, steer_label = hooks.calculate_steering(left, right)
        status = hooks.format_console_status(mode, steer_label, left, right, speed)
        print(f"\r{status}", end="")

    def _move_backward(self, left: float, right: float, rear: float, speed: int):
        """Execute backward movement using hooks."""
        if rear < hooks.EMERGENCY_STOP_DIST:
            if self._current_direction == "backward":
                hooks.execute_stop(self.client)
                self._current_direction = "stopped"
                print(f"\r🚨 ABORT REVERSE! Rear:{rear:.0f}cm", end="")
            return
        
        hooks.execute_reverse(self.client, speed, left, right, rear)
        self._current_direction = "backward"
        
        servo, steer_label = hooks.calculate_reverse_steering(left, right)
        status = hooks.format_reverse_status(steer_label, rear, speed)
        print(f"\r{status}", end="")

    def _update_display(self, left: float, right: float, rear: float, front_clearance: float):
        """Update OLED display using hooks."""
        sensor_data = hooks.SensorData(
            left_distance=left,
            right_distance=right,
            rear_distance=rear,
            front_clearance=front_clearance,
            approach_rate=0,
            timestamp=time.time()
        )
        
        display_text = hooks.format_display_text(
            sensor_data,
            self._current_direction,
            self._emergency_stop_active
        )
        hooks.update_display(self.client, display_text)


def main():
    """Main function for autonomous navigation."""
    client = PicarClient()
    driver = AutonomousDriver(client)

    print(f"Connecting to Picar at {client.base_url}...")
    try:
        s = client.status()
        print(f"✓ Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except Exception:
        print(f"✗ Could not connect. Is the Pico running?")
        return

    print("\n" + "="*70)
    print("PICAR AUTONOMOUS MODE - Refactored Version (Uses Hooks)")
    print("="*70)
    print("\nControls:")
    print("  G       — Start autonomous mode")
    print("  SPACE   — Stop autonomous mode")
    print("  Q       — Quit")
    print("="*70)
    print("\nNote: This version uses autonomous_hooks.py for all logic.")
    print("Fix bugs in hooks → both autonomous.py and autonomous_fsm.py benefit!")
    print()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = sys.stdin.read(1).lower()

            if key == "q":
                if driver.autonomous:
                    driver.stop()
                print("\r\n✓ Stopped. Goodbye.\n")
                break

            elif key == " ":
                if driver.autonomous:
                    driver.stop()
                else:
                    hooks.execute_stop(client)
                    print("\r🛑 Stopped")

            elif key == "g":
                driver.start()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
