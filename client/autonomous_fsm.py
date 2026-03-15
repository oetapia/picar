"""
Autonomous Navigation using Hybrid Finite State Machine

This module implements a cleaner, more maintainable autonomous navigation
system using a Hybrid FSM + Decision Tree approach.

Architecture:
- Finite State Machine for safety-critical states (emergency, recovery)
- Priority-ordered Decision Tree for normal navigation
- Uses hooks from autonomous_hooks.py for all low-level operations
"""

import sys
import tty
import termios
import threading
import time
from enum import Enum, auto
from typing import Optional

from picar_client import PicarClient
import autonomous_hooks as hooks


# ═══════════════════════════════════════════════════════════════════
# STATE MACHINE DEFINITION
# ═══════════════════════════════════════════════════════════════════

class NavigationState(Enum):
    """Finite State Machine states for autonomous navigation."""
    STOPPED = auto()
    EMERGENCY_STOP = auto()
    RECOVERY = auto()
    CRUISE = auto()
    MEDIUM = auto()
    SLOW = auto()
    CRAWL = auto()
    TACTICAL_REVERSE = auto()
    TRAPPED = auto()


# ═══════════════════════════════════════════════════════════════════
# HYBRID FSM CLASS
# ═══════════════════════════════════════════════════════════════════

class AutonomousFSM:
    """
    Hybrid Finite State Machine for autonomous navigation.
    
    Uses a hierarchical decision structure:
    1. Emergency checks (highest priority)
    2. Recovery logic (for emergency clearance)
    3. Normal navigation (decision tree)
    """
    
    def __init__(self, client: PicarClient):
        self.client = client
        self.state = NavigationState.STOPPED
        self.autonomous = False
        
        # State tracking
        self._current_direction = "stopped"
        self._last_front_dist: Optional[float] = None
        self._last_measurement_time: Optional[float] = None
        self._display_update_counter = 0
        
        # Background thread
        self._thread: Optional[threading.Thread] = None
    
    # ═══════════════════════════════════════════════════════════════
    # PUBLIC INTERFACE
    # ═══════════════════════════════════════════════════════════════
    
    def start(self):
        """Start autonomous navigation."""
        if self.autonomous:
            return
        
        self.autonomous = True
        self.state = NavigationState.STOPPED
        self._current_direction = "stopped"
        self._last_front_dist = None
        self._last_measurement_time = None
        self._display_update_counter = 0
        
        # Display startup
        try:
            self.client.send_text("FSM AUTO\nStarting...")
        except:
            pass
        
        # Start navigation loop
        self._thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self._thread.start()
        
        print("\r🚗 Autonomous FSM ON - Hybrid State Machine")
        print("\r   Industry-standard navigation active")
    
    def stop(self):
        """Stop autonomous navigation."""
        self.autonomous = False
        hooks.execute_stop(self.client)
        self.state = NavigationState.STOPPED
        self._current_direction = "stopped"
        
        try:
            self.client.send_text("FSM AUTO\nStopped")
        except:
            pass
        
        print("\r🛑 Autonomous FSM OFF - Vehicle stopped")
    
    # ═══════════════════════════════════════════════════════════════
    # NAVIGATION LOOP
    # ═══════════════════════════════════════════════════════════════
    
    def _navigation_loop(self):
        """Main navigation loop running in background thread."""
        while self.autonomous:
            loop_start = time.time()
            
            try:
                # Read all sensors
                sensor_data = self._read_sensors()
                if sensor_data is None:
                    print("\r⚠️  Sensors unavailable")
                    hooks.execute_stop(self.client)
                    time.sleep(0.5)
                    continue
                
                # Update approach rate
                sensor_data = self._update_approach_rate(sensor_data)
                
                # ═══ PRIORITY 1: EMERGENCY CHECKS ═══
                emergency_state = self._check_emergency_conditions(sensor_data)
                if emergency_state:
                    self._transition_to(emergency_state)
                    self._handle_state(sensor_data)
                    self._update_display_throttled(sensor_data)
                    self._maintain_poll_rate(loop_start)
                    continue
                
                # ═══ PRIORITY 2: RECOVERY LOGIC ═══
                if self.state == NavigationState.EMERGENCY_STOP:
                    recovery_state = self._handle_recovery(sensor_data)
                    if recovery_state:
                        self._transition_to(recovery_state)
                        self._handle_state(sensor_data)
                        self._update_display_throttled(sensor_data)
                        self._maintain_poll_rate(loop_start)
                        continue
                
                # Clear emergency flag if recovered
                if hooks.should_clear_emergency(sensor_data.front_clearance, 
                                               sensor_data.rear_distance):
                    if self.state == NavigationState.EMERGENCY_STOP:
                        self.state = NavigationState.STOPPED
                
                # ═══ PRIORITY 3: TRAPPED CHECK ═══
                if hooks.check_trapped(sensor_data.front_clearance, 
                                      sensor_data.rear_distance):
                    self._transition_to(NavigationState.TRAPPED)
                    hooks.execute_stop(self.client)
                    self._current_direction = "stopped"
                    print(f"\r🚨 TRAPPED! F:{sensor_data.front_clearance:.0f}cm "
                          f"R:{sensor_data.rear_distance:.0f}cm")
                    self._update_display_throttled(sensor_data)
                    self._maintain_poll_rate(loop_start)
                    continue
                
                # ═══ PRIORITY 4: NAVIGATION DECISION TREE ═══
                new_state = self._decide_navigation_state(sensor_data)
                if new_state != self.state:
                    self._transition_to(new_state)
                
                # Execute current state
                self._handle_state(sensor_data)
                
                # Update display
                self._update_display_throttled(sensor_data)
                
            except Exception as e:
                print(f"\r⚠️  Navigation error: {e}")
                hooks.execute_stop(self.client)
                time.sleep(0.5)
                continue
            
            # Maintain consistent poll rate
            self._maintain_poll_rate(loop_start)
    
    # ═══════════════════════════════════════════════════════════════
    # SENSOR READING
    # ═══════════════════════════════════════════════════════════════
    
    def _read_sensors(self) -> Optional[hooks.SensorData]:
        """Read all sensors and return SensorData object."""
        # Read ToF sensors
        left, right, tof_success = hooks.read_tof_sensors(self.client)
        if not tof_success:
            return None
        
        # Read ultrasonic
        rear, _ = hooks.read_ultrasonic_sensor(self.client)
        
        # Calculate clearances
        front_clearance, _ = hooks.calculate_clearances(left, right, rear)
        
        return hooks.SensorData(
            left_distance=left,
            right_distance=right,
            rear_distance=rear,
            front_clearance=front_clearance,
            approach_rate=0.0,  # Will be updated
            timestamp=time.time()
        )
    
    def _update_approach_rate(self, sensor_data: hooks.SensorData) -> hooks.SensorData:
        """Update approach rate in sensor data."""
        time_delta = 0
        if self._last_measurement_time:
            time_delta = sensor_data.timestamp - self._last_measurement_time
        
        approach_rate = hooks.calculate_approach_rate(
            sensor_data.front_clearance,
            self._last_front_dist,
            time_delta
        )
        
        self._last_front_dist = sensor_data.front_clearance
        self._last_measurement_time = sensor_data.timestamp
        
        # Create new SensorData with updated approach rate
        return hooks.SensorData(
            left_distance=sensor_data.left_distance,
            right_distance=sensor_data.right_distance,
            rear_distance=sensor_data.rear_distance,
            front_clearance=sensor_data.front_clearance,
            approach_rate=approach_rate,
            timestamp=sensor_data.timestamp
        )
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 1: EMERGENCY CHECKS
    # ═══════════════════════════════════════════════════════════════
    
    def _check_emergency_conditions(self, sensor_data: hooks.SensorData) -> Optional[NavigationState]:
        """
        Check for emergency conditions requiring immediate stop.
        Returns new state if emergency detected, None otherwise.
        """
        # Forward emergency
        if hooks.check_emergency_forward(self._current_direction, 
                                        sensor_data.front_clearance):
            print(f"\r🚨 EMERGENCY STOP! Front:{sensor_data.front_clearance:.0f}cm")
            hooks.execute_stop(self.client)
            self._current_direction = "stopped"
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP
        
        # Reverse emergency
        if hooks.check_emergency_reverse(self._current_direction,
                                        sensor_data.rear_distance):
            print(f"\r🚨 EMERGENCY STOP REVERSE! Rear:{sensor_data.rear_distance:.0f}cm")
            hooks.execute_stop(self.client)
            self._current_direction = "stopped"
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP
        
        # Predictive braking
        if hooks.check_pre_brake(self._current_direction, sensor_data.approach_rate):
            print(f"\r⚡ PRE-BRAKE! Approaching at {-sensor_data.approach_rate:.0f}cm/s")
            hooks.execute_pre_brake(self.client)
            time.sleep(0.05)
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 2: RECOVERY LOGIC
    # ═══════════════════════════════════════════════════════════════
    
    def _handle_recovery(self, sensor_data: hooks.SensorData) -> Optional[NavigationState]:
        """
        Handle recovery from emergency stop.
        Returns recovery state or None if should stay stopped.
        """
        margin = 5  # Small margin to avoid getting stuck
        
        # Front still too close - must reverse
        if (sensor_data.front_clearance < hooks.EMERGENCY_STOP_DIST + margin and
            sensor_data.rear_distance > hooks.REAR_CAUTION_DIST):
            return NavigationState.RECOVERY
        
        # Rear still too close - must move forward
        if (sensor_data.rear_distance < hooks.EMERGENCY_STOP_DIST + margin and
            sensor_data.front_clearance > hooks.EMERGENCY_STOP_DIST + margin):
            return NavigationState.RECOVERY
        
        # Both still too close - stay stopped
        if (sensor_data.front_clearance < hooks.EMERGENCY_STOP_DIST + margin and
            sensor_data.rear_distance < hooks.EMERGENCY_STOP_DIST + margin):
            return None
        
        # Emergency cleared - resume normal navigation
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 3: NAVIGATION DECISION TREE
    # ═══════════════════════════════════════════════════════════════
    
    def _decide_navigation_state(self, sensor_data: hooks.SensorData) -> NavigationState:
        """
        Decide navigation state based on sensor data using decision tree.
        Priority-ordered from safest to most aggressive.
        """
        fc = sensor_data.front_clearance
        rc = sensor_data.rear_distance
        ar = sensor_data.approach_rate
        
        # Decision tree (priority order)
        if hooks.should_cruise_forward(fc):
            return NavigationState.CRUISE
        
        elif hooks.should_medium_forward(fc):
            return NavigationState.MEDIUM
        
        elif hooks.should_slow_forward(fc):
            return NavigationState.SLOW
        
        elif hooks.should_crawl_forward(fc):
            # Check if should reverse instead due to fast approach
            if hooks.should_tactical_reverse(fc, rc, ar):
                return NavigationState.TACTICAL_REVERSE
            return NavigationState.CRAWL
        
        elif hooks.should_emergency_reverse(fc, rc):
            return NavigationState.TACTICAL_REVERSE
        
        else:
            # No safe forward movement - try reverse if rear clear
            if rc > hooks.REAR_DANGER_DIST:
                return NavigationState.TACTICAL_REVERSE
            return NavigationState.STOPPED
    
    # ═══════════════════════════════════════════════════════════════
    # STATE EXECUTION
    # ═══════════════════════════════════════════════════════════════
    
    def _handle_state(self, sensor_data: hooks.SensorData):
        """Execute actions for current state."""
        state_handlers = {
            NavigationState.STOPPED: self._handle_stopped,
            NavigationState.EMERGENCY_STOP: self._handle_emergency_stop,
            NavigationState.RECOVERY: self._handle_recovery_state,
            NavigationState.CRUISE: lambda sd: self._handle_forward(sd, hooks.CRUISE_SPEED, "CRUISE"),
            NavigationState.MEDIUM: lambda sd: self._handle_forward(sd, hooks.MEDIUM_SPEED, "MEDIUM"),
            NavigationState.SLOW: lambda sd: self._handle_forward(sd, hooks.SLOW_SPEED, "SLOW"),
            NavigationState.CRAWL: lambda sd: self._handle_forward(sd, hooks.CRAWL_SPEED, "CRAWL"),
            NavigationState.TACTICAL_REVERSE: self._handle_reverse,
            NavigationState.TRAPPED: self._handle_trapped,
        }
        
        handler = state_handlers.get(self.state)
        if handler:
            handler(sensor_data)
    
    def _handle_stopped(self, sensor_data: hooks.SensorData):
        """Handle stopped state."""
        # Already stopped, nothing to do
        pass
    
    def _handle_emergency_stop(self, sensor_data: hooks.SensorData):
        """Handle emergency stop state."""
        # Already stopped in emergency check
        pass
    
    def _handle_recovery_state(self, sensor_data: hooks.SensorData):
        """Handle recovery state."""
        if sensor_data.front_clearance < sensor_data.rear_distance:
            # Front more blocked - reverse slowly
            hooks.execute_reverse(self.client, hooks.REVERSE_SLOW,
                                sensor_data.left_distance,
                                sensor_data.right_distance,
                                sensor_data.rear_distance)
            self._current_direction = "backward"
            print(f"\r🔄 RECOVERY REVERSE Rear:{sensor_data.rear_distance:.0f}cm", end="")
        else:
            # Rear more blocked - crawl forward
            hooks.execute_forward(self.client, hooks.CRAWL_SPEED,
                                sensor_data.left_distance,
                                sensor_data.right_distance)
            self._current_direction = "forward"
            print(f"\r🔄 RECOVERY FORWARD Front:{sensor_data.front_clearance:.0f}cm", end="")
    
    def _handle_forward(self, sensor_data: hooks.SensorData, speed: int, mode: str):
        """Handle forward movement states."""
        hooks.execute_forward(self.client, speed,
                            sensor_data.left_distance,
                            sensor_data.right_distance)
        self._current_direction = "forward"
        
        servo, steer_label = hooks.calculate_steering(sensor_data.left_distance,
                                                      sensor_data.right_distance)
        status = hooks.format_console_status(mode, steer_label,
                                            sensor_data.left_distance,
                                            sensor_data.right_distance,
                                            speed)
        print(f"\r{status}", end="")
    
    def _handle_reverse(self, sensor_data: hooks.SensorData):
        """Handle tactical reverse state."""
        hooks.execute_reverse(self.client, hooks.REVERSE_SLOW,
                            sensor_data.left_distance,
                            sensor_data.right_distance,
                            sensor_data.rear_distance)
        self._current_direction = "backward"
        
        servo, steer_label = hooks.calculate_reverse_steering(sensor_data.left_distance,
                                                              sensor_data.right_distance)
        status = hooks.format_reverse_status(steer_label,
                                            sensor_data.rear_distance,
                                            hooks.REVERSE_SLOW)
        print(f"\r{status}", end="")
    
    def _handle_trapped(self, sensor_data: hooks.SensorData):
        """Handle trapped state."""
        # Already stopped in trapped check
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # STATE TRANSITIONS
    # ═══════════════════════════════════════════════════════════════
    
    def _transition_to(self, new_state: NavigationState):
        """Transition to a new state."""
        if new_state != self.state:
            old_state = self.state
            self.state = new_state
            # Optional: log state transitions for debugging
            # print(f"\r[FSM] {old_state.name} → {new_state.name}")
    
    # ═══════════════════════════════════════════════════════════════
    # DISPLAY AND TIMING
    # ═══════════════════════════════════════════════════════════════
    
    def _update_display_throttled(self, sensor_data: hooks.SensorData):
        """Update OLED display with throttling."""
        self._display_update_counter += 1
        if self._display_update_counter >= 4:  # Every 4 loops (~0.2s)
            self._display_update_counter = 0
            
            emergency_active = self.state == NavigationState.EMERGENCY_STOP
            display_text = hooks.format_display_text(sensor_data,
                                                    self._current_direction,
                                                    emergency_active)
            hooks.update_display(self.client, display_text)
    
    def _maintain_poll_rate(self, loop_start: float):
        """Maintain consistent polling rate."""
        loop_duration = time.time() - loop_start
        sleep_time = max(0, hooks.POLL_INTERVAL - loop_duration)
        time.sleep(sleep_time)


# ═══════════════════════════════════════════════════════════════════
# MAIN FUNCTION (for standalone testing)
# ═══════════════════════════════════════════════════════════════════

def main():
    """Main function for testing FSM autonomous mode."""
    client = PicarClient()
    driver = AutonomousFSM(client)
    
    print(f"Connecting to Picar at {client.base_url}...")
    try:
        s = client.status()
        print(f"✓ Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except Exception:
        print(f"✗ Could not connect. Is the Pico running?")
        return
    
    print("\n" + "="*70)
    print("PICAR AUTONOMOUS FSM - Hybrid State Machine Navigation")
    print("="*70)
    print("\nControls:")
    print("  G       — Start FSM autonomous mode")
    print("  SPACE   — Stop (exit autonomous mode)")
    print("  Q       — Quit")
    print("="*70)
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
                print("\r\n✓ FSM Stopped. Goodbye.\n")
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
