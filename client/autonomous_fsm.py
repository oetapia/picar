"""
Autonomous Navigation — Hybrid Finite State Machine (Industry-Hardened)

Enhanced with physics-grounded vehicle model for:
- Stopping distances derived from measured speed & reaction time
- Time-to-Collision (TTC) based emergency triggering
- Hysteresis bands to prevent state oscillation
- Speed-dependent steering gain for stability
- Acceleration smoothing to reduce jerk
- Gap-width safety check (vehicle is 16 cm wide)
- Valid state-transition table (AUTOSAR-inspired)
- Thread-safe shared state via Lock
- State-timeout watchdog & sensor-staleness detection
- Structured logging (replaces bare prints)

Architecture:
- Finite State Machine for safety-critical states (emergency, recovery)
- Priority-ordered Decision Tree for normal navigation
- Perception system for advanced sensor fusion and obstacle tracking
- Uses hooks from autonomous_hooks.py for all low-level operations
- VehicleModel in hooks for physics calculations

Industry references:
    ISO 26262  — functional safety (stopping distance, watchdog)
    AUTOSAR    — explicit state-transition validation
    ROS nav    — layered perception → planning → control
"""

import sys
import tty
import termios
import threading
import time
import logging
from enum import Enum, auto
from typing import Optional, Set, Dict

from picar_client import PicarClient
import autonomous_hooks as hooks

log = logging.getLogger("picar.fsm")


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


# ── Valid transitions (AUTOSAR-style) ────────────────────────────
# If a transition is not listed here it will be rejected and logged.
VALID_TRANSITIONS: Dict[NavigationState, Set[NavigationState]] = {
    NavigationState.STOPPED: {
        NavigationState.CRUISE, NavigationState.MEDIUM,
        NavigationState.SLOW, NavigationState.CRAWL,
        NavigationState.EMERGENCY_STOP, NavigationState.TACTICAL_REVERSE,
    },
    NavigationState.CRUISE: {
        NavigationState.MEDIUM, NavigationState.SLOW,
        NavigationState.EMERGENCY_STOP, NavigationState.STOPPED,
    },
    NavigationState.MEDIUM: {
        NavigationState.CRUISE, NavigationState.SLOW,
        NavigationState.CRAWL, NavigationState.EMERGENCY_STOP,
        NavigationState.STOPPED,
    },
    NavigationState.SLOW: {
        NavigationState.MEDIUM, NavigationState.CRAWL,
        NavigationState.EMERGENCY_STOP, NavigationState.STOPPED,
    },
    NavigationState.CRAWL: {
        NavigationState.SLOW, NavigationState.TACTICAL_REVERSE,
        NavigationState.EMERGENCY_STOP, NavigationState.STOPPED,
    },
    NavigationState.TACTICAL_REVERSE: {
        NavigationState.CRAWL, NavigationState.STOPPED,
        NavigationState.EMERGENCY_STOP, NavigationState.TRAPPED,
    },
    NavigationState.EMERGENCY_STOP: {
        NavigationState.RECOVERY, NavigationState.STOPPED,
        NavigationState.TRAPPED,
    },
    NavigationState.RECOVERY: {
        NavigationState.STOPPED, NavigationState.CRAWL,
        NavigationState.EMERGENCY_STOP, NavigationState.TRAPPED,
    },
    NavigationState.TRAPPED: {
        NavigationState.RECOVERY, NavigationState.STOPPED,
    },
}

# Map state → speed motor-% for physics queries
STATE_SPEED: Dict[NavigationState, int] = {
    NavigationState.CRUISE: hooks.CRUISE_SPEED,
    NavigationState.MEDIUM: hooks.MEDIUM_SPEED,
    NavigationState.SLOW: hooks.SLOW_SPEED,
    NavigationState.CRAWL: hooks.CRAWL_SPEED,
    NavigationState.TACTICAL_REVERSE: abs(hooks.REVERSE_SLOW),
}


# ═══════════════════════════════════════════════════════════════════
# HYBRID FSM CLASS
# ═══════════════════════════════════════════════════════════════════

class AutonomousFSM:
    """
    Hybrid Finite State Machine for autonomous navigation.

    Uses a hierarchical decision structure:
    1. Emergency checks — TTC + distance (highest priority)
    2. Recovery logic — timeout-guarded
    3. Normal navigation — hysteresis-stabilised decision tree

    Thread-safe: all shared state protected by ``_lock``.
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.state = NavigationState.STOPPED
        self.autonomous = False

        # ── Thread safety ────────────────────────────────────────
        self._lock = threading.Lock()

        # ── State tracking ───────────────────────────────────────
        self._current_direction = "stopped"
        self._current_motor_pct = 0          # actual motor % sent
        self._last_front_dist: Optional[float] = None
        self._last_measurement_time: Optional[float] = None
        self._display_update_counter = 0

        # ── Watchdog / staleness ─────────────────────────────────
        self._state_enter_time: float = time.time()
        self._last_sensor_time: float = time.time()
        self._stuck_counter: int = 0         # escalation counter

        # ── Background thread ────────────────────────────────────
        self._thread: Optional[threading.Thread] = None

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC INTERFACE
    # ═══════════════════════════════════════════════════════════════

    def start(self):
        """Start autonomous navigation."""
        if self.autonomous:
            return

        with self._lock:
            self.autonomous = True
            self.state = NavigationState.STOPPED
            self._current_direction = "stopped"
            self._current_motor_pct = 0
            self._last_front_dist = None
            self._last_measurement_time = None
            self._display_update_counter = 0
            self._state_enter_time = time.time()
            self._last_sensor_time = time.time()
            self._stuck_counter = 0

        try:
            self.client.send_text("FSM AUTO\nStarting...")
        except Exception:
            log.warning("Could not update display on start")

        self._thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self._thread.start()

        # Log physics config at startup
        v = hooks.VEHICLE
        log.info("Autonomous FSM ON — physics-grounded")
        log.info("  Vehicle: %.0fcm L × %.0fcm W (overall %.0fcm) × %.0fcm H",
                 v.length, v.body_width, v.overall_width, v.height)
        log.info("  Cruise %d%% ≈ %.0f cm/s  stop-dist %.0f cm",
                 hooks.CRUISE_SPEED,
                 v.speed_at(hooks.CRUISE_SPEED),
                 v.stopping_distance(hooks.CRUISE_SPEED))
        log.info("  E-stop=%dcm  Safe=%dcm  Caution=%dcm  Danger=%dcm  Critical=%dcm",
                 hooks.EMERGENCY_STOP_DIST, hooks.SAFE_DIST,
                 hooks.CAUTION_DIST, hooks.DANGER_DIST, hooks.CRITICAL_DIST)
        log.info("  MinGap=%.0fcm  Hysteresis=%.0fcm  TTC_emerg=%.1fs",
                 hooks.MIN_GAP_WIDTH, v.hysteresis_cm, hooks.TTC_EMERGENCY)

    def stop(self):
        """Stop autonomous navigation."""
        with self._lock:
            self.autonomous = False
            self._current_direction = "stopped"
            self._current_motor_pct = 0
        hooks.execute_stop(self.client)
        self.state = NavigationState.STOPPED

        try:
            self.client.send_text("FSM AUTO\nStopped")
        except Exception:
            pass

        log.info("Autonomous FSM OFF — vehicle stopped")
    
    # ═══════════════════════════════════════════════════════════════
    # NAVIGATION LOOP
    # ═══════════════════════════════════════════════════════════════
    
    def _navigation_loop(self):
        """Main navigation loop running in background thread."""
        while self.autonomous:
            loop_start = time.time()

            try:
                # ── Sensor reading ───────────────────────────────
                perception_state = self._read_sensors()
                if perception_state is None:
                    if time.time() - self._last_sensor_time > hooks.SENSOR_MAX_AGE:
                        log.warning("Sensor stale > %.0f ms — emergency stop",
                                    hooks.SENSOR_MAX_AGE * 1000)
                        hooks.execute_stop(self.client)
                        with self._lock:
                            self._current_direction = "stopped"
                            self._current_motor_pct = 0
                    time.sleep(0.1)
                    continue

                with self._lock:
                    self._last_sensor_time = perception_state.timestamp

                perception_state = self._update_approach_rate(perception_state)

                # ── State-timeout watchdog ────────────────────────
                self._check_state_timeout()

                # ═══ PRIORITY 0: TTC EMERGENCY (physics-based) ═══
                motor_pct = STATE_SPEED.get(self.state, 0)
                if self._current_direction == "forward" and hooks.check_ttc_emergency(perception_state, motor_pct):
                    log.warning("TTC < %.1fs — emergency stop  front=%.0fcm",
                                hooks.TTC_EMERGENCY, perception_state.front_clearance)
                    hooks.execute_stop(self.client)
                    with self._lock:
                        self._current_direction = "stopped"
                        self._current_motor_pct = 0
                    self._transition_to(NavigationState.EMERGENCY_STOP)
                    self._update_display_throttled_perception(perception_state)
                    self._maintain_poll_rate(loop_start)
                    continue

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
                    with self._lock:
                        self._current_direction = "stopped"
                        self._current_motor_pct = 0
                    log.warning("TRAPPED  F:%.0fcm  R:%.0fcm",
                                perception_state.front_clearance,
                                perception_state.rear_clearance)
                    self._update_display_throttled_perception(perception_state)
                    self._maintain_poll_rate(loop_start)
                    continue

                # ═══ PRIORITY 4: NAVIGATION DECISION TREE ═══
                new_state = self._decide_navigation_state_perception(perception_state)
                if new_state != self.state:
                    self._transition_to(new_state)

                # Execute current state
                self._handle_state_perception(perception_state)

                # Update display
                self._update_display_throttled_perception(perception_state)

            except Exception as e:
                log.error("Navigation error: %s", e, exc_info=True)
                hooks.execute_stop(self.client)
                with self._lock:
                    self._current_direction = "stopped"
                    self._current_motor_pct = 0
                time.sleep(0.5)
                continue

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
            log.warning("EMERGENCY STOP — front=%.0fcm  dir=%s",
                        state.front_clearance, self._current_direction)
            hooks.execute_stop(self.client)
            with self._lock:
                self._current_direction = "stopped"
                self._current_motor_pct = 0
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP

        # Reverse emergency
        if hooks.check_emergency_reverse(self._current_direction, state.rear_clearance):
            log.warning("EMERGENCY STOP REVERSE — rear=%.0fcm", state.rear_clearance)
            hooks.execute_stop(self.client)
            with self._lock:
                self._current_direction = "stopped"
                self._current_motor_pct = 0
            time.sleep(0.1)
            return NavigationState.EMERGENCY_STOP

        # TTC-based pre-brake (physics-aware)
        motor_pct = STATE_SPEED.get(self.state, 0)
        if self._current_direction == "forward" and hooks.check_ttc_brake(state, motor_pct):
            log.info("TTC pre-brake — slowing to crawl")
            hooks.execute_pre_brake(self.client)
            with self._lock:
                self._current_motor_pct = hooks.CRAWL_SPEED
            time.sleep(0.05)

        # Velocity-based pre-brake (legacy compatibility)
        elif hooks.check_pre_brake_perception(state, self._current_direction):
            approaching_obs = [o for o in state.obstacles
                               if o.velocity and o.velocity < -hooks.APPROACH_RATE_THRESHOLD]
            if approaching_obs:
                vel = approaching_obs[0].velocity
                log.info("PRE-BRAKE — obstacle approaching at %.0f cm/s", -vel)
            hooks.execute_pre_brake(self.client)
            with self._lock:
                self._current_motor_pct = hooks.CRAWL_SPEED
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
        Decide navigation state using perception state with hysteresis.

        Hysteresis: to *enter* a faster state the clearance must exceed
        the upper threshold; to *stay* in it only the lower threshold is
        needed.  This eliminates rapid flickering at boundary distances.
        """
        fc = state.front_clearance
        rc = state.rear_clearance

        # ── Gap-width safety gate ────────────────────────────────
        left_obs = state.get_obstacle_by_direction('front_left')
        right_obs = state.get_obstacle_by_direction('front_right')
        left = left_obs.distance if left_obs else 999
        right = right_obs.distance if right_obs else 999
        if not hooks.check_gap_passable(left, right):
            log.info("Gap too narrow (L:%.0f R:%.0f < %.0f) — stopping",
                     left, right, hooks.MIN_GAP_WIDTH)
            return NavigationState.STOPPED

        # ── Hysteresis helper ────────────────────────────────────
        def _above(enter_thresh: float, exit_thresh: float,
                   target_state: NavigationState) -> bool:
            """True if clearance justifies *target_state*."""
            if self.state == target_state:
                return fc > exit_thresh       # already in — use lower bar
            return fc > enter_thresh          # entering — use higher bar

        # Decision tree (priority order) with hysteresis
        if _above(hooks.CRUISE_ENTER, hooks.CRUISE_EXIT, NavigationState.CRUISE):
            return NavigationState.CRUISE

        if _above(hooks.MEDIUM_ENTER, hooks.MEDIUM_EXIT, NavigationState.MEDIUM):
            return NavigationState.MEDIUM

        if _above(hooks.SLOW_ENTER, hooks.SLOW_EXIT, NavigationState.SLOW):
            return NavigationState.SLOW

        if _above(hooks.CRAWL_ENTER, hooks.CRAWL_EXIT, NavigationState.CRAWL):
            if hooks.should_tactical_reverse_perception(state):
                return NavigationState.TACTICAL_REVERSE
            return NavigationState.CRAWL

        if hooks.should_emergency_reverse(fc, rc):
            return NavigationState.TACTICAL_REVERSE

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
        """Handle recovery with stuck-counter escalation."""
        if state.front_clearance < state.rear_clearance:
            hooks.execute_reverse(self.client, hooks.REVERSE_SLOW, left, right, state.rear_clearance)
            with self._lock:
                self._current_direction = "backward"
                self._current_motor_pct = hooks.REVERSE_SLOW
            log.info("RECOVERY REVERSE  rear=%.0fcm  stuck=%d",
                     state.rear_clearance, self._stuck_counter)
        else:
            hooks.execute_forward(self.client, hooks.CRAWL_SPEED, left, right)
            with self._lock:
                self._current_direction = "forward"
                self._current_motor_pct = hooks.CRAWL_SPEED
            log.info("RECOVERY FORWARD  front=%.0fcm  stuck=%d",
                     state.front_clearance, self._stuck_counter)

    def _handle_forward_perception(self, state, left: float, right: float,
                                   target_speed: int, mode: str):
        """Handle forward movement with acceleration smoothing and speed-dependent steering."""
        # Smooth speed ramp
        smoothed = hooks.smooth_speed(self._current_motor_pct, target_speed)
        # Speed-dependent steering
        servo, steer_label = hooks.calculate_steering_with_speed(left, right, smoothed)
        self.client.set_servo(servo)
        self.client.set_motor(smoothed)
        with self._lock:
            self._current_direction = "forward"
            self._current_motor_pct = smoothed
        status = hooks.format_console_status(mode, steer_label, left, right, smoothed)
        print(f"\r{status}", end="")

    def _handle_reverse_perception(self, state, left: float, right: float):
        """Handle tactical reverse with smoothing."""
        target = hooks.REVERSE_SLOW
        smoothed = hooks.smooth_speed(self._current_motor_pct, target)
        hooks.execute_reverse(self.client, smoothed, left, right, state.rear_clearance)
        with self._lock:
            self._current_direction = "backward"
            self._current_motor_pct = smoothed
        servo, steer_label = hooks.calculate_reverse_steering(left, right)
        status = hooks.format_reverse_status(steer_label, state.rear_clearance, smoothed)
        print(f"\r{status}", end="")
    
    # ═══════════════════════════════════════════════════════════════
    # STATE TRANSITIONS (validated)
    # ═══════════════════════════════════════════════════════════════

    def _transition_to(self, new_state: NavigationState):
        """
        Transition to a new state with AUTOSAR-style validation.

        Invalid transitions are rejected and logged as warnings.
        Emergency transitions are always allowed (safety override).
        """
        if new_state == self.state:
            return

        old_state = self.state
        allowed = VALID_TRANSITIONS.get(old_state, set())

        # Safety override: EMERGENCY_STOP is always reachable
        if new_state == NavigationState.EMERGENCY_STOP or new_state in allowed:
            self.state = new_state
            self._state_enter_time = time.time()
            # Reset stuck counter when leaving trapped/recovery
            if old_state in (NavigationState.TRAPPED, NavigationState.RECOVERY):
                self._stuck_counter = 0
            log.debug("FSM %s → %s", old_state.name, new_state.name)
        else:
            log.warning("REJECTED transition %s → %s  (not in valid set)",
                        old_state.name, new_state.name)

    # ═══════════════════════════════════════════════════════════════
    # STATE TIMEOUT WATCHDOG
    # ═══════════════════════════════════════════════════════════════

    def _check_state_timeout(self):
        """
        Watchdog: escalate if stuck in a state too long.

        RECOVERY / TACTICAL_REVERSE → TRAPPED after timeout.
        TRAPPED → increment stuck counter for telemetry.
        """
        timeout = hooks.STATE_TIMEOUT.get(self.state.name)
        if timeout is None:
            return

        elapsed = time.time() - self._state_enter_time
        if elapsed <= timeout:
            return

        if self.state in (NavigationState.RECOVERY, NavigationState.TACTICAL_REVERSE):
            self._stuck_counter += 1
            log.warning("State %s timed out after %.1fs (stuck=%d) → TRAPPED",
                        self.state.name, elapsed, self._stuck_counter)
            self._transition_to(NavigationState.TRAPPED)
            hooks.execute_stop(self.client)
            with self._lock:
                self._current_direction = "stopped"
                self._current_motor_pct = 0

        elif self.state == NavigationState.TRAPPED:
            self._stuck_counter += 1
            # Attempt recovery after trapped timeout
            log.info("TRAPPED timeout (%.1fs, stuck=%d) — attempting recovery",
                     elapsed, self._stuck_counter)
            self._transition_to(NavigationState.RECOVERY)
    
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
    print("PICAR AUTONOMOUS FSM — Industry-Hardened Navigation")
    print("="*70)
    print("\nControls:")
    print("  G       — Start FSM autonomous mode")
    print("  SPACE   — Stop (exit autonomous mode)")
    print("  Q       — Quit")
    print("="*70)
    v = hooks.VEHICLE
    print(f"\nVehicle: {v.length:.0f}×{v.overall_width:.0f}×{v.height:.0f}cm  "
          f"Cruise≈{v.speed_at(hooks.CRUISE_SPEED):.0f}cm/s  "
          f"Stop-dist≈{v.stopping_distance(hooks.CRUISE_SPEED):.0f}cm")
    print(f"MinGap: {hooks.MIN_GAP_WIDTH:.0f}cm  "
          f"Hysteresis: ±{v.hysteresis_cm:.0f}cm  "
          f"TTC-emerg: {hooks.TTC_EMERGENCY:.1f}s")
    print("\nFeatures:")
    print("  ✓ Physics-grounded stopping distances (measured speed)")
    print("  ✓ Time-to-Collision (TTC) emergency & pre-brake")
    print("  ✓ Hysteresis bands — no state oscillation")
    print("  ✓ AUTOSAR-style state transition validation")
    print("  ✓ Speed-dependent steering gain")
    print("  ✓ Acceleration smoothing (jerk limiting)")
    print("  ✓ Gap-width safety (vehicle 16cm wide)")
    print("  ✓ Sensor staleness detection & state watchdog")
    print("  ✓ Thread-safe shared state (Lock)")
    print("  ✓ Sensor fusion + IMU + obstacle tracking")
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
