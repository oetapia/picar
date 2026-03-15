"""
Autonomous Navigation using Hybrid Finite State Machine - Perception-Powered

Enhanced with perception system for:
- Sensor fusion with confidence weighting
- IMU-validated motion detection
- Obstacle tracking with velocity
- Predictive collision avoidance

Architecture:
- Finite State Machine for safety-critical states (emergency, recovery)
- Priority-ordered Decision Tree for normal navigation
- Perception system for advanced sensor fusion and obstacle tracking
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
        
        print("\r🚗 Autonomous FSM ON - Perception-Powered")
        print("\r   Sensor fusion + IMU + Obstacle tracking + State Machine active")
    
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
                # Read all sensors via perception system
                perception_state = self._read_sensors()
                if perception_state is None:
                    print("\r⚠️  Critical sensors unavailable")
                    hooks.execute_stop(self.client)
                    time.sleep(0.5)
                    continue
                
                # Update tracking
                perception_state = self._update_approach_rate(perception_state)
                
                # ═══ PRIORITY 1: EMERGENCY CHECKS (PERCEPTION-AWARE) ═══
                emergency_state = self._check_emergency_conditions_perception(perception_state)
                if emergency_state:
                    self._transition_to(emergency_state)
                    self._handle_state_perception(perception_state)
                    self._update_display_throttled_perception(perception_state)
                    self._maintain_poll_rate(loop_start)
                    continue
                
                # ═══ PRIORITY 2: RECOVERY LOGIC ═══
                if self.state == NavigationState.EMERGENCY_STOP:
                    recovery_state = self._handle_recovery_perception(perception_state)
                    if recovery_state:
                        self._transition_to(recovery_state)
                        self._handle_state_perception(perception_state)
                        self._update_display_throttled_perception(perception_state)
                        self._maintain_poll_rate(loop_start)
                        continue
                
                # Clear emergency flag if recovered
                if hooks.should_clear_emergency(perception_state.front_clearance, 
                                               perception_state.rear_clearance):
                    if self.state == NavigationState.EMERGENCY_STOP:
                        self.state = NavigationState.STOPPED
                
                # ═══ PRIORITY 3: TRAPPED CHECK ═══
                if hooks.check_trapped(perception_state.front_clearance, 
                                      perception_state.rear_clearance):
                    self._transition_to(NavigationState.TRAPPED)
                    hooks.execute_stop(self.client)
                    self._current_direction = "stopped"
                    print(f"\r🚨 TRAPPED! F:{perception_state.front_clearance:.0f}cm "
                          f"R:{perception_state.rear_clearance:.0f}cm")
                    self._update_display_throttled_perception(perception_state)
                    self._maintain_poll_rate(loop_start)
                    continue
                
                # ═══ PRIORITY 4: NAVIGATION DECISION TREE (PERCEPTION-AWARE) ═══
                new_state = self._decide_navigation_state_perception(perception_state)
                if new_state != self.state:
                    self._transition_to(new_state)
                
                # Execute current state
                self._handle_state_perception(perception_state)
                
                # Update display
                self._update_display_throttled_perception(perception_state)
                
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
    
    def _read_sensors(self):
        """Read all sensors via perception system."""
        # Use perception system for sensor fusion
        perception_state = hooks.read_perception_state(self.client)
        if perception_state is None:
            return None
        
        # Return perception state directly (not SensorData)
        return perception_state
    
    def _update_approach_rate(self, perception_state):
        """Update tracking for perception state (approach rate calculated by perception system)."""
        # Perception system already tracks velocities per obstacle
        # Just update our internal state tracking
        self._last_front_dist = perception_state.front_clearance
        self._last_measurement_time = perception_state.timestamp
        
        return perception_state
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 1: EMERGENCY CHECKS (PERCEPTION-AWARE)
    # ═══════════════════════════════════════════════════════════════
    
    def _check_emergency_conditions_perception(self, state) -> Optional[NavigationState]:
        """
        Check for emergency conditions using perception state.
        Returns new state if emergency detected, None otherwise.
        """
        # Forward emergency (perception-aware)
        if hooks.check_emergency_forward_perception(state, self._current_direction):
            print(f"\r🚨 EMERGENCY STOP! Front:{state.front_clearance:.0f}cm")
            hooks.execute_stop(self.client)
            self._current_direction = "stopped"
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP
        
        # Reverse emergency
        if hooks.check_emergency_reverse(self._current_direction, state.rear_clearance):
            print(f"\r🚨 EMERGENCY STOP REVERSE! Rear:{state.rear_clearance:.0f}cm")
            hooks.execute_stop(self.client)
            self._current_direction = "stopped"
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP
        
        # Predictive braking (perception-aware with velocity)
        if hooks.check_pre_brake_perception(state, self._current_direction):
            approaching_obs = [o for o in state.obstacles if o.velocity and o.velocity < -hooks.APPROACH_RATE_THRESHOLD]
            if approaching_obs:
                vel = approaching_obs[0].velocity
                print(f"\r⚡ PRE-BRAKE! Obstacle approaching at {-vel:.0f}cm/s")
            hooks.execute_pre_brake(self.client)
            time.sleep(0.05)
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 2: RECOVERY LOGIC
    # ═══════════════════════════════════════════════════════════════
    
    def _handle_recovery_perception(self, state) -> Optional[NavigationState]:
        """
        Handle recovery from emergency stop using perception state.
        Returns recovery state or None if should stay stopped.
        """
        margin = 5  # Small margin to avoid getting stuck
        
        # Front still too close - must reverse
        if (state.front_clearance < hooks.EMERGENCY_STOP_DIST + margin and
            state.rear_clearance > hooks.REAR_CAUTION_DIST):
            return NavigationState.RECOVERY
        
        # Rear still too close - must move forward
        if (state.rear_clearance < hooks.EMERGENCY_STOP_DIST + margin and
            state.front_clearance > hooks.EMERGENCY_STOP_DIST + margin):
            return NavigationState.RECOVERY
        
        # Both still too close - stay stopped
        if (state.front_clearance < hooks.EMERGENCY_STOP_DIST + margin and
            state.rear_clearance < hooks.EMERGENCY_STOP_DIST + margin):
            return None
        
        # Emergency cleared - resume normal navigation
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # PRIORITY 3: NAVIGATION DECISION TREE (PERCEPTION-AWARE)
    # ═══════════════════════════════════════════════════════════════
    
    def _decide_navigation_state_perception(self, state) -> NavigationState:
        """
        Decide navigation state using perception state.
        Priority-ordered from safest to most aggressive.
        """
        fc = state.front_clearance
        rc = state.rear_clearance
        
        # Decision tree (priority order) - using perception-aware hooks
        if hooks.should_cruise_forward_perception(state):
            return NavigationState.CRUISE
        
        elif hooks.should_medium_forward_perception(state):
            return NavigationState.MEDIUM
        
        elif hooks.should_slow_forward_perception(state):
            return NavigationState.SLOW
        
        elif hooks.should_crawl_forward_perception(state):
            # Check if should reverse instead (perception-aware)
            if hooks.should_tactical_reverse_perception(state):
                return NavigationState.TACTICAL_REVERSE
            return NavigationState.CRAWL
        
        elif hooks.should_emergency_reverse(fc, rc):
            return NavigationState.TACTICAL_REVERSE
        
        else:
            # No safe forward movement and not critical enough for reverse - STOP
            return NavigationState.STOPPED
    
    # ═══════════════════════════════════════════════════════════════
    # STATE EXECUTION (PERCEPTION-AWARE)
    # ═══════════════════════════════════════════════════════════════
    
    def _handle_state_perception(self, state):
        """Execute actions for current state using perception state."""
        # Extract left/right from obstacles
        left_obs = state.get_obstacle_by_direction('front_left')
        right_obs = state.get_obstacle_by_direction('front_right')
        left = left_obs.distance if left_obs else 999
        right = right_obs.distance if right_obs else 999
        
        state_handlers = {
            NavigationState.STOPPED: lambda: None,
            NavigationState.EMERGENCY_STOP: lambda: None,
            NavigationState.RECOVERY: lambda: self._handle_recovery_state_perception(state, left, right),
            NavigationState.CRUISE: lambda: self._handle_forward_perception(state, left, right, hooks.CRUISE_SPEED, "CRUISE"),
            NavigationState.MEDIUM: lambda: self._handle_forward_perception(state, left, right, hooks.MEDIUM_SPEED, "MEDIUM"),
            NavigationState.SLOW: lambda: self._handle_forward_perception(state, left, right, hooks.SLOW_SPEED, "SLOW"),
            NavigationState.CRAWL: lambda: self._handle_forward_perception(state, left, right, hooks.CRAWL_SPEED, "CRAWL"),
            NavigationState.TACTICAL_REVERSE: lambda: self._handle_reverse_perception(state, left, right),
            NavigationState.TRAPPED: lambda: None,
        }
        
        handler = state_handlers.get(self.state)
        if handler:
            handler()
    
    def _handle_recovery_state_perception(self, state, left: float, right: float):
        """Handle recovery state using perception."""
        if state.front_clearance < state.rear_clearance:
            # Front more blocked - reverse slowly
            hooks.execute_reverse(self.client, hooks.REVERSE_SLOW, left, right, state.rear_clearance)
            self._current_direction = "backward"
            print(f"\r🔄 RECOVERY REVERSE Rear:{state.rear_clearance:.0f}cm", end="")
        else:
            # Rear more blocked - crawl forward
            hooks.execute_forward(self.client, hooks.CRAWL_SPEED, left, right)
            self._current_direction = "forward"
            print(f"\r🔄 RECOVERY FORWARD Front:{state.front_clearance:.0f}cm", end="")
    
    def _handle_forward_perception(self, state, left: float, right: float, speed: int, mode: str):
        """Handle forward movement states using perception."""
        hooks.execute_forward(self.client, speed, left, right)
        self._current_direction = "forward"
        
        servo, steer_label = hooks.calculate_steering(left, right)
        status = hooks.format_console_status(mode, steer_label, left, right, speed)
        print(f"\r{status}", end="")
    
    def _handle_reverse_perception(self, state, left: float, right: float):
        """Handle tactical reverse state using perception."""
        hooks.execute_reverse(self.client, hooks.REVERSE_SLOW, left, right, state.rear_clearance)
        self._current_direction = "backward"
        
        servo, steer_label = hooks.calculate_reverse_steering(left, right)
        status = hooks.format_reverse_status(steer_label, state.rear_clearance, hooks.REVERSE_SLOW)
        print(f"\r{status}", end="")
    
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
    
    def _update_display_throttled_perception(self, state):
        """Update OLED display with perception data."""
        self._display_update_counter += 1
        if self._display_update_counter >= 4:  # Every 4 loops (~0.2s)
            self._display_update_counter = 0
            
            # Extract obstacles for display
            left_obs = state.get_obstacle_by_direction('front_left')
            right_obs = state.get_obstacle_by_direction('front_right')
            left = left_obs.distance if left_obs else 999
            right = right_obs.distance if right_obs else 999
            
            sensor_data = hooks.SensorData(
                left_distance=left,
                right_distance=right,
                rear_distance=state.rear_clearance,
                front_clearance=state.front_clearance,
                approach_rate=0,
                timestamp=state.timestamp
            )
            
            emergency_active = self.state == NavigationState.EMERGENCY_STOP
            display_text = hooks.format_display_text(sensor_data,
                                                    self._current_direction,
                                                    emergency_active)
            
            # Add perception info
            high_conf = len([o for o in state.obstacles if o.confidence >= 0.8])
            if high_conf > 0:
                display_text += f"\nConf:{high_conf}"
            
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
    print("PICAR AUTONOMOUS FSM - Perception-Powered State Machine")
    print("="*70)
    print("\nControls:")
    print("  G       — Start FSM autonomous mode")
    print("  SPACE   — Stop (exit autonomous mode)")
    print("  Q       — Quit")
    print("="*70)
    print("\nFeatures:")
    print("  ✓ Hybrid FSM + Decision Tree architecture")
    print("  ✓ Sensor fusion with confidence weighting")
    print("  ✓ IMU-validated motion detection")
    print("  ✓ Obstacle tracking with velocity")
    print("  ✓ Predictive collision avoidance")
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
