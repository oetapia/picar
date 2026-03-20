"""
Autonomous Navigation Hooks - Reusable Functions

This module provides reusable hooks for autonomous navigation,
extracted from the original autonomous.py implementation.
These functions can be used by different navigation strategies.

Enhanced with:
- Physics-grounded vehicle model (measured speed/dimensions)
- Perception System integration (sensor fusion, IMU, obstacle tracking)
- Time-to-Collision (TTC) based safety
- Hysteresis bands for stable state transitions
- Speed-dependent steering gain
- Structured logging

Industry references:
- ISO 26262 (functional safety) — stopping distance derived from physics
- ROS Navigation Stack — layered perception/planning/control
- AUTOSAR — explicit state transitions with validation
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Tuple, Optional, Dict, List
from picar_client import PicarClient
from perception import PerceptionSystem, parse_imu_state, PerceptionState, Obstacle

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

log = logging.getLogger("picar.nav")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

# ═══════════════════════════════════════════════════════════════════
# VEHICLE PHYSICS MODEL (measured)
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VehicleModel:
    """
    Physics model derived from real measurements.

    Measurements taken:
        100 % motor → 3 m in 4.39 s  →  68.3 cm/s
         50 % motor → 3 m in 5.48 s  →  54.7 cm/s

    Dimensions (cm):
        length=34  body_width=14  overall_width=16  height=24

    ToF sensors are mounted 11 cm apart at the front.
    """

    # ── Dimensions (cm) ──────────────────────────────────────────
    length: float = 34.0
    body_width: float = 14.0
    overall_width: float = 16.0          # including tyres
    height: float = 24.0
    wheelbase: float = 22.0              # estimated
    tof_spacing: float = 11.0            # sensor-to-sensor

    # ── Measured speed calibration ───────────────────────────────
    # motor% → cm/s  (two real data-points; rest interpolated via
    # the sqrt mapping in motor.py)
    _speed_cal: Dict[int, float] = field(default_factory=lambda: {
        100: 68.3,
        50: 54.7,
    })

    # ── Timing budget (seconds) ──────────────────────────────────
    sensor_poll_s: float = 0.05          # 20 Hz loop
    network_rtt_s: float = 0.10          # WiFi round-trip
    motor_lag_s: float = 0.05            # H-bridge response
    safety_factor: float = 1.3           # ISO 26262 recommended margin

    # ── Braking estimate ─────────────────────────────────────────
    deceleration_cmss: float = 150.0     # rough coast-to-stop

    # ── Safety margins ───────────────────────────────────────────
    side_margin_cm: float = 5.0          # clearance per side
    front_margin_cm: float = 5.0         # extra buffer after braking

    # ── Hysteresis band ──────────────────────────────────────────
    hysteresis_cm: float = 5.0           # enter/exit offset

    # ── Helpers ──────────────────────────────────────────────────
    @property
    def reaction_time_s(self) -> float:
        """Total worst-case reaction time."""
        return (self.sensor_poll_s + self.network_rtt_s + self.motor_lag_s) * self.safety_factor

    def speed_at(self, motor_pct: int) -> float:
        """
        Estimate true speed (cm/s) for a motor percentage.

        Uses the sqrt mapping from motor.py to interpolate between
        the two measured calibration points.
        """
        if motor_pct in self._speed_cal:
            return self._speed_cal[motor_pct]
        if motor_pct <= 5:
            return 0.0
        # motor.py: normalised = sqrt((pct - 5) / 95)
        # We know v(100)=68.3 and v(50)=54.7.  Fit  v = k·sqrt((pct-5)/95)
        # k = 68.3 / sqrt(95/95) = 68.3
        k = 68.3  # from 100 % data-point
        norm = math.sqrt(max(0, (motor_pct - 5) / 95.0))
        return k * norm

    def stopping_distance(self, motor_pct: int) -> float:
        """
        Physics-based stopping distance (cm).

        d = v·t_react  +  v²/(2·a)  +  front_margin
        """
        v = self.speed_at(abs(motor_pct))
        d_react = v * self.reaction_time_s
        d_brake = (v ** 2) / (2 * self.deceleration_cmss) if self.deceleration_cmss > 0 else 0
        return d_react + d_brake + self.front_margin_cm

    def time_to_collision(self, distance_cm: float, motor_pct: int,
                          approach_rate_cms: float = 0.0) -> float:
        """
        Time-to-collision (TTC) in seconds.

        Considers own speed + obstacle approach rate.
        """
        closing_speed = self.speed_at(abs(motor_pct)) + abs(approach_rate_cms)
        if closing_speed <= 0:
            return float('inf')
        return distance_cm / closing_speed

    def min_passable_gap(self) -> float:
        """Minimum corridor width the car can safely pass through."""
        return self.overall_width + 2 * self.side_margin_cm

    def emergency_dist_for_speed(self, motor_pct: int) -> float:
        """
        Speed-specific emergency stop distance.

        Returns the minimum distance at which an emergency stop must
        trigger to guarantee the car stops before contact.
        """
        return self.stopping_distance(motor_pct)

    def threshold_with_hysteresis(self, base_cm: float, entering: bool) -> float:
        """
        Apply hysteresis offset.

        entering=True  → stricter (need MORE clearance to enter faster state)
        entering=False → looser  (need LESS clearance to leave slower state)
        """
        if entering:
            return base_cm + self.hysteresis_cm
        return base_cm - self.hysteresis_cm


# Singleton vehicle model
VEHICLE = VehicleModel()


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS - Navigation Parameters (physics-derived where possible)
# ═══════════════════════════════════════════════════════════════════

# Speed settings (motor %)
# ⚠️  Motor dead zone: below ~35% PWM the motor stalls (insufficient torque).
# All speeds MUST be ≥ 35 for forward, ≤ -35 for reverse.
MOTOR_DEADZONE = 35               # minimum motor % that actually moves
CRUISE_SPEED   = 55               # comfortable cruising
CAUTIOUS_SPEED = 42               # slowing down, still responsive
MINIMUM_SPEED  = 35               # barely moves — crawl / obstacle proximity
# Legacy aliases (so FSM state names still map cleanly)
MEDIUM_SPEED = CAUTIOUS_SPEED
SLOW_SPEED   = MINIMUM_SPEED
CRAWL_SPEED  = MINIMUM_SPEED
REVERSE_FAST = -50
REVERSE_SLOW = -38

# Steering angles
STEER_LEFT = 35
STEER_SLIGHT_LEFT = 65
STEER_RIGHT = 145
STEER_SLIGHT_RIGHT = 115
CENTRE = 90

# ── Physics-derived distance thresholds (cm) ─────────────────────
# Each threshold = stopping-distance for that speed band, rounded up
# to the nearest 5 cm for sensor granularity.
_round5 = lambda x: int(math.ceil(x / 5.0)) * 5

EMERGENCY_STOP_DIST = max(50, _round5(VEHICLE.stopping_distance(CRUISE_SPEED)))
VERY_SAFE_DIST      = EMERGENCY_STOP_DIST + 40   # generous headroom for cruise
SAFE_DIST           = EMERGENCY_STOP_DIST + 15    # medium speed band
CAUTION_DIST        = _round5(VEHICLE.stopping_distance(SLOW_SPEED) + 15)
DANGER_DIST         = _round5(VEHICLE.stopping_distance(CRAWL_SPEED) + 10)
CRITICAL_DIST       = _round5(VEHICLE.stopping_distance(CRAWL_SPEED))

# ── Hysteresis enter/exit pairs ──────────────────────────────────
CRUISE_ENTER  = VERY_SAFE_DIST + VEHICLE.hysteresis_cm   # need more room to speed up
CRUISE_EXIT   = VERY_SAFE_DIST - VEHICLE.hysteresis_cm   # can stay a bit closer
MEDIUM_ENTER  = SAFE_DIST + VEHICLE.hysteresis_cm
MEDIUM_EXIT   = SAFE_DIST - VEHICLE.hysteresis_cm
SLOW_ENTER    = CAUTION_DIST + VEHICLE.hysteresis_cm
SLOW_EXIT     = CAUTION_DIST - VEHICLE.hysteresis_cm
CRAWL_ENTER   = DANGER_DIST + VEHICLE.hysteresis_cm
CRAWL_EXIT    = DANGER_DIST - VEHICLE.hysteresis_cm

# ── Rear distance thresholds ─────────────────────────────────────
REAR_SAFE_DIST    = 60
REAR_CAUTION_DIST = 45
REAR_DANGER_DIST  = _round5(VEHICLE.stopping_distance(abs(REVERSE_SLOW)))

# ── TTC safety thresholds (seconds) ─────────────────────────────
TTC_EMERGENCY = 0.6    # must stop immediately
TTC_BRAKE     = 1.2    # start pre-braking
TTC_CAUTION   = 2.0    # reduce speed

# Velocity tracking
APPROACH_RATE_THRESHOLD = 15  # cm/s

# ── Minimum passable gap (cm) ────────────────────────────────────
MIN_GAP_WIDTH = VEHICLE.min_passable_gap()

# Timing
POLL_INTERVAL = 0.05

# ── Sensor staleness (seconds) ───────────────────────────────────
SENSOR_MAX_AGE = 0.25   # stop if no fresh data for 250 ms

# ── State timeout watchdog (seconds) ─────────────────────────────
STATE_TIMEOUT = {
    "RECOVERY": 5.0,
    "TACTICAL_REVERSE": 4.0,
    "TRAPPED": 10.0,
}

# ── Acceleration smoothing ───────────────────────────────────────
MAX_SPEED_STEP = 5   # max motor-% change per control loop iteration


# ═══════════════════════════════════════════════════════════════════
# PERCEPTION SYSTEM SINGLETON
# ═══════════════════════════════════════════════════════════════════

_perception_system: Optional[PerceptionSystem] = None


def get_perception_system() -> PerceptionSystem:
    """Get or create singleton perception system."""
    global _perception_system
    if _perception_system is None:
        _perception_system = PerceptionSystem()
    return _perception_system


# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SensorData:
    """Container for all sensor readings (legacy - use PerceptionState for new code)."""
    left_distance: float
    right_distance: float
    rear_distance: float
    front_clearance: float
    approach_rate: float
    timestamp: float
    
    @property
    def min_front(self) -> float:
        """Get minimum front distance (worst case)."""
        return min(self.left_distance, self.right_distance)


@dataclass
class NavigationAction:
    """Container for navigation action to execute."""
    direction: str  # "forward", "backward", "stopped"
    speed: int
    servo_angle: int
    status_label: str


# ═══════════════════════════════════════════════════════════════════
# PERCEPTION-POWERED SENSOR READING HOOKS
# ═══════════════════════════════════════════════════════════════════

def read_perception_state(client: PicarClient) -> Optional[PerceptionState]:
    """
    Read all sensors and return fused perception state.
    
    Uses PerceptionSystem for:
    - Sensor fusion with confidence weighting
    - IMU integration for motion validation
    - Obstacle tracking with velocity
    - Sensor health monitoring
    
    Returns:
        PerceptionState with fused sensor data, or None if critical sensors unavailable
    """
    # Read ToF sensors
    left, right, tof_success = read_tof_sensors(client)
    if not tof_success:
        return None
    
    # Read ultrasonic
    rear, _ = read_ultrasonic_sensor(client)
    
    # Read IMU with motor speed for motion validation
    try:
        status = client.status()
        motor_speed = status.get('motor_speed', 0)
        imu_state = client.get_accelerometer()
        imu_data = parse_imu_state(imu_state, motor_speed)
    except Exception:
        imu_data = None
    
    # Fuse sensors using perception system
    perception = get_perception_system()
    return perception.fuse_sensors(left, right, rear, imu_data)


# ═══════════════════════════════════════════════════════════════════
# BASIC SENSOR READING HOOKS (Legacy - for compatibility)
# ═══════════════════════════════════════════════════════════════════

def read_tof_sensors(client: PicarClient) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Read ToF sensors and return distances.
    
    Returns:
        (left_distance, right_distance, success)
    """
    try:
        tof = client.get_tof()
        if not tof.get('success'):
            return None, None, False
        
        left = tof.get('left_distance_cm')
        right = tof.get('right_distance_cm')
        
        # Handle None values
        if left is None:
            left = 999
        if right is None:
            right = 999
        
        return left, right, True
    except Exception:
        return None, None, False


def read_ultrasonic_sensor(client: PicarClient) -> Tuple[float, bool]:
    """
    Read ultrasonic sensor and return rear distance.
    
    Returns:
        (rear_distance, success)
    """
    try:
        ultrasonic = client.get_ultrasonic()
        if ultrasonic.get('success') and ultrasonic.get('in_range'):
            return ultrasonic.get('distance_cm', 999), True
        return 999, True  # Out of range = assume clear
    except Exception:
        return 999, False


def calculate_clearances(left: float, right: float, rear: float) -> Tuple[float, float]:
    """
    Calculate front and rear clearances.
    
    Returns:
        (front_clearance, rear_clearance)
    """
    front_clearance = min(left, right)  # Worst case matters
    rear_clearance = rear
    return front_clearance, rear_clearance


def calculate_approach_rate(current_dist: float, 
                           last_dist: Optional[float], 
                           time_delta: float) -> float:
    """
    Calculate approach rate (velocity toward obstacle).
    
    Returns:
        Approach rate in cm/s (negative = approaching)
    """
    if last_dist is None or time_delta <= 0:
        return 0.0
    return (current_dist - last_dist) / time_delta


# ═══════════════════════════════════════════════════════════════════
# PERCEPTION-AWARE DECISION HOOKS
# ═══════════════════════════════════════════════════════════════════

def should_cruise_forward_perception(state: PerceptionState) -> bool:
    """Check if safe to cruise using perception state."""
    # Filter high-confidence obstacles from state
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        return state.front_clearance > VERY_SAFE_DIST
    
    # Check closest high-confidence obstacle
    min_dist = min(o.distance for o in front_obstacles)
    return min_dist > VERY_SAFE_DIST


def should_medium_forward_perception(state: PerceptionState) -> bool:
    """Check if safe for medium speed using perception state."""
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        return state.front_clearance > SAFE_DIST
    
    min_dist = min(o.distance for o in front_obstacles)
    return min_dist > SAFE_DIST


def should_slow_forward_perception(state: PerceptionState) -> bool:
    """Check if should slow down using perception state."""
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        return state.front_clearance > CAUTION_DIST
    
    min_dist = min(o.distance for o in front_obstacles)
    return min_dist > CAUTION_DIST


def should_crawl_forward_perception(state: PerceptionState) -> bool:
    """Check if should crawl forward using perception state."""
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        return state.front_clearance > DANGER_DIST
    
    min_dist = min(o.distance for o in front_obstacles)
    return min_dist > DANGER_DIST


def should_tactical_reverse_perception(state: PerceptionState) -> bool:
    """
    Check if tactical reverse is needed using perception state.
    
    Enhanced with:
    - Obstacle velocity (approaching obstacles)
    - Motion validation (don't reverse if not moving)
    - Confidence weighting
    """
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        # Use basic logic
        return should_tactical_reverse(state.front_clearance, state.rear_clearance)
    
    # Get closest obstacle
    closest = min(front_obstacles, key=lambda o: o.distance)
    
    # Check for approaching obstacles (negative velocity)
    approaching = [o for o in front_obstacles if o.velocity and o.velocity < -15]
    
    # Fast approach with clear rear - pre-emptive reverse
    if approaching and closest.distance < CAUTION_DIST and state.rear_clearance > REAR_CAUTION_DIST:
        return True
    
    # CRITICAL front distance with clear rear - must reverse
    if closest.distance < CRITICAL_DIST and state.rear_clearance > REAR_CAUTION_DIST:
        return True
    
    return False


def check_emergency_forward_perception(state: PerceptionState, 
                                       current_direction: str,
                                       threshold: float = EMERGENCY_STOP_DIST) -> bool:
    """Check if forward emergency stop is needed using perception state."""
    if current_direction != "forward":
        return False
    
    # Filter high-confidence obstacles
    high_conf_obstacles = [o for o in state.obstacles if o.confidence >= 0.7]
    front_obstacles = [o for o in high_conf_obstacles if o.direction.startswith('front')]
    
    if not front_obstacles:
        return state.front_clearance < threshold
    
    # Check closest high-confidence obstacle
    min_dist = min(o.distance for o in front_obstacles)
    return min_dist < threshold


def check_pre_brake_perception(state: PerceptionState,
                               current_direction: str) -> bool:
    """
    Check if predictive braking is needed using perception state.
    
    Uses obstacle velocity for more accurate prediction.
    """
    if current_direction != "forward":
        return False
    
    # Get approaching obstacles (negative velocity)
    approaching = [o for o in state.obstacles if o.velocity and o.velocity < -APPROACH_RATE_THRESHOLD]
    
    if not approaching:
        return False
    
    # Check if any approaching obstacle is getting close
    for obs in approaching:
        if obs.direction.startswith('front') and obs.distance < SAFE_DIST:
            return True
    
    return False


# ═══════════════════════════════════════════════════════════════════
# SAFETY CHECK HOOKS
# ═══════════════════════════════════════════════════════════════════

def check_emergency_forward(current_direction: str, 
                           front_clearance: float,
                           threshold: float = EMERGENCY_STOP_DIST) -> bool:
    """Check if forward emergency stop is needed."""
    return current_direction == "forward" and front_clearance < threshold


def check_emergency_reverse(current_direction: str,
                           rear_clearance: float,
                           threshold: float = EMERGENCY_STOP_DIST) -> bool:
    """Check if reverse emergency stop is needed."""
    return current_direction == "backward" and rear_clearance < threshold


def check_trapped(front_clearance: float, 
                 rear_clearance: float) -> bool:
    """Check if vehicle is trapped (no safe path)."""
    return front_clearance < CRITICAL_DIST and rear_clearance < REAR_DANGER_DIST


def check_pre_brake(current_direction: str,
                   approach_rate: float,
                   threshold: float = APPROACH_RATE_THRESHOLD) -> bool:
    """Check if predictive braking is needed."""
    return current_direction == "forward" and approach_rate < -threshold


def should_clear_emergency(front_clearance: float,
                          rear_clearance: float,
                          margin: float = 10) -> bool:
    """Check if emergency flag should be cleared."""
    return (front_clearance > EMERGENCY_STOP_DIST + margin and 
            rear_clearance > EMERGENCY_STOP_DIST + margin)


# ═══════════════════════════════════════════════════════════════════
# STEERING CALCULATION HOOKS
# ═══════════════════════════════════════════════════════════════════

def calculate_steering(left_dist: float, right_dist: float) -> Tuple[int, str]:
    """
    Calculate steering angle based on side clearances.
    
    Returns:
        (servo_angle, label)
    """
    clearance_diff = abs(left_dist - right_dist)
    
    if clearance_diff > 15:  # Significant difference
        if left_dist < right_dist:
            # Left side tighter - steer right
            if clearance_diff > 30:
                return STEER_RIGHT, "→→"
            else:
                return STEER_SLIGHT_RIGHT, "→"
        else:
            # Right side tighter - steer left
            if clearance_diff > 30:
                return STEER_LEFT, "←←"
            else:
                return STEER_SLIGHT_LEFT, "←"
    else:
        # Both sides similar - go straight
        return CENTRE, "↑"


def calculate_reverse_steering(left_dist: float, right_dist: float) -> Tuple[int, str]:
    """
    Calculate steering for reverse movement.
    
    Returns:
        (servo_angle, label)
    """
    if abs(left_dist - right_dist) > 10:
        if left_dist < right_dist:
            # Left blocked more - steer right (nose goes left when reversing)
            return STEER_RIGHT, "⤴"
        else:
            # Right blocked more - steer left (nose goes right when reversing)
            return STEER_LEFT, "⤵"
    else:
        # Center steering for straight reverse
        return CENTRE, "↓"


# ═══════════════════════════════════════════════════════════════════
# ACTION EXECUTION HOOKS
# ═══════════════════════════════════════════════════════════════════

def execute_stop(client: PicarClient) -> None:
    """Execute emergency stop."""
    client.stop()
    client.centre()


def execute_forward(client: PicarClient, 
                   speed: int,
                   left_dist: float,
                   right_dist: float) -> None:
    """Execute forward movement with steering."""
    servo, _ = calculate_steering(left_dist, right_dist)
    client.set_servo(servo)
    client.set_motor(speed)


def execute_reverse(client: PicarClient,
                   speed: int,
                   left_dist: float,
                   right_dist: float,
                   rear_dist: float) -> None:
    """Execute reverse movement with steering."""
    # Don't reverse if rear too close
    if rear_dist < EMERGENCY_STOP_DIST:
        client.stop()
        return
    
    # Reduce speed if rear is getting close (but stay above dead zone)
    if rear_dist < REAR_CAUTION_DIST:
        speed = max(speed, -MOTOR_DEADZONE)  # clamp to minimum moving speed
    
    servo, _ = calculate_reverse_steering(left_dist, right_dist)
    client.set_servo(servo)
    client.set_motor(speed)


def execute_pre_brake(client: PicarClient) -> None:
    """Execute predictive braking."""
    client.set_motor(CRAWL_SPEED)


# ═══════════════════════════════════════════════════════════════════
# DISPLAY HOOKS
# ═══════════════════════════════════════════════════════════════════

def format_distance(dist: float, max_display: float = 200) -> str:
    """Format distance for display."""
    return f"{dist:.0f}" if dist < max_display else "---"


def get_status_label(front_clearance: float, emergency_active: bool) -> str:
    """Get status label for display."""
    if emergency_active:
        return "STOP!"
    elif front_clearance > VERY_SAFE_DIST:
        return "CRUISE"
    elif front_clearance > SAFE_DIST:
        return "MEDIUM"
    elif front_clearance > CAUTION_DIST:
        return "SLOW"
    elif front_clearance > DANGER_DIST:
        return "CRAWL"
    else:
        return "DANGER"


def format_display_text(sensor_data: SensorData,
                       current_direction: str,
                       emergency_active: bool) -> str:
    """
    Format complete display text for OLED.
    
    Returns:
        Formatted display string
    """
    left_str = format_distance(sensor_data.left_distance)
    right_str = format_distance(sensor_data.right_distance)
    rear_str = format_distance(sensor_data.rear_distance)
    
    status = get_status_label(sensor_data.front_clearance, emergency_active)
    
    display_text = f"AUTO: {status}\n"
    display_text += f"F: L{left_str} R{right_str}\n"
    display_text += f"Rear: {rear_str}cm\n"
    
    # Direction indicator
    if current_direction == "forward":
        display_text += "Dir: FWD"
    elif current_direction == "backward":
        display_text += "Dir: REV"
    else:
        display_text += "Dir: ---"
    
    return display_text


def update_display(client: PicarClient, display_text: str) -> None:
    """Update OLED display (non-blocking)."""
    try:
        client.send_text(display_text)
    except:
        pass  # Silently fail - don't affect navigation


# ═══════════════════════════════════════════════════════════════════
# DECISION LOGIC HOOKS
# ═══════════════════════════════════════════════════════════════════

def should_cruise_forward(front_clearance: float) -> bool:
    """Check if conditions are safe for cruise speed."""
    return front_clearance > VERY_SAFE_DIST


def should_medium_forward(front_clearance: float) -> bool:
    """Check if conditions allow medium speed."""
    return front_clearance > SAFE_DIST


def should_slow_forward(front_clearance: float) -> bool:
    """Check if should slow down."""
    return front_clearance > CAUTION_DIST


def should_crawl_forward(front_clearance: float) -> bool:
    """Check if should crawl forward."""
    return front_clearance > DANGER_DIST


def should_tactical_reverse(front_clearance: float,
                           rear_clearance: float,
                           approach_rate: float = 0) -> bool:
    """Check if tactical reverse is needed."""
    # Only reverse if CRITICAL distance or fast approach
    # NOT in danger zone (35-45cm) - that should still crawl forward!
    
    # Fast approach with clear rear - pre-emptive reverse
    if approach_rate < -15 and front_clearance < CAUTION_DIST and rear_clearance > REAR_CAUTION_DIST:
        return True
    
    # CRITICAL front distance with clear rear - must reverse
    if front_clearance < CRITICAL_DIST and rear_clearance > REAR_CAUTION_DIST:
        return True
    
    return False


def should_emergency_reverse(front_clearance: float,
                            rear_clearance: float) -> bool:
    """Check if emergency reverse is needed — can't enter CRAWL, must back up."""
    return (front_clearance < CRAWL_ENTER and
            rear_clearance > REAR_DANGER_DIST)


# ═══════════════════════════════════════════════════════════════════
# TTC & PHYSICS-AWARE SAFETY HOOKS
# ═══════════════════════════════════════════════════════════════════

def check_ttc_emergency(state: PerceptionState, motor_pct: int) -> bool:
    """
    Check if Time-to-Collision triggers an emergency stop.

    Industry practice: TTC < threshold → immediate stop regardless of
    distance, because the closing speed is too high for the remaining gap.
    """
    closest = state.get_closest_front_obstacle()
    if closest is None:
        return False
    approach = abs(closest.velocity) if closest.velocity and closest.velocity < 0 else 0
    ttc = VEHICLE.time_to_collision(closest.distance, motor_pct, approach)
    return ttc < TTC_EMERGENCY


def check_ttc_brake(state: PerceptionState, motor_pct: int) -> bool:
    """Check if TTC warrants pre-braking (slow to crawl)."""
    closest = state.get_closest_front_obstacle()
    if closest is None:
        return False
    approach = abs(closest.velocity) if closest.velocity and closest.velocity < 0 else 0
    ttc = VEHICLE.time_to_collision(closest.distance, motor_pct, approach)
    return ttc < TTC_BRAKE


def check_gap_passable(left_dist: float, right_dist: float) -> bool:
    """
    Check if the gap between left and right obstacles is wide enough
    for the car to pass through safely.

    Uses overall_width (16 cm) + 2 × side_margin (5 cm) = 26 cm.
    """
    gap = left_dist + right_dist  # crude: sensor distances sum ≈ corridor width
    # More accurate: if both sensors see walls, the gap is approximately
    # left + right (since sensors are near the edges).
    return gap >= MIN_GAP_WIDTH


# ═══════════════════════════════════════════════════════════════════
# SPEED-DEPENDENT STEERING
# ═══════════════════════════════════════════════════════════════════

def calculate_steering_with_speed(left_dist: float, right_dist: float,
                                  motor_pct: int) -> Tuple[int, str]:
    """
    Calculate steering angle with speed-dependent gain.

    At higher speeds the steering angle is reduced to prevent
    rollover and maintain stability (Ackermann-inspired).

    Returns:
        (servo_angle, label)
    """
    base_servo, label = calculate_steering(left_dist, right_dist)

    if base_servo == CENTRE:
        return CENTRE, label

    # Reduce deflection at higher speeds
    # gain = 1.0 at CRAWL, 0.6 at CRUISE
    speed_ratio = min(1.0, max(0.0, (abs(motor_pct) - CRAWL_SPEED)
                                    / max(1, CRUISE_SPEED - CRAWL_SPEED)))
    gain = 1.0 - 0.4 * speed_ratio  # 1.0 → 0.6

    deflection = base_servo - CENTRE           # signed degrees from centre
    adjusted = int(CENTRE + deflection * gain)
    # Clamp to valid servo range
    adjusted = max(STEER_LEFT, min(STEER_RIGHT, adjusted))

    return adjusted, label


# ═══════════════════════════════════════════════════════════════════
# ACCELERATION SMOOTHING
# ═══════════════════════════════════════════════════════════════════

def smooth_speed(current_motor: int, target_motor: int) -> int:
    """
    Ramp speed towards target by at most MAX_SPEED_STEP per tick.

    Prevents jerky acceleration / deceleration which can cause
    wheel-spin and sensor vibration.

    Skips the dead zone when starting from rest so the motor moves immediately.
    """
    diff = target_motor - current_motor
    if abs(diff) <= MAX_SPEED_STEP:
        return target_motor
    next_speed = current_motor + (MAX_SPEED_STEP if diff > 0 else -MAX_SPEED_STEP)
    # When starting from stopped, jump directly to the minimum speed that moves the motor
    if current_motor == 0 and target_motor > 0:
        return max(next_speed, MOTOR_DEADZONE)
    if current_motor == 0 and target_motor < 0:
        return min(next_speed, -MOTOR_DEADZONE)
    return next_speed


# ═══════════════════════════════════════════════════════════════════
# STATUS FORMATTING HOOKS
# ═══════════════════════════════════════════════════════════════════

def format_console_status(mode: str,
                         steer_label: str,
                         left_dist: float,
                         right_dist: float,
                         speed: int) -> str:
    """Format status message for console output."""
    return f"🟢 {mode} {steer_label} L:{left_dist:.0f} R:{right_dist:.0f} [{speed}%]"


def format_reverse_status(steer_label: str,
                         rear_dist: float,
                         speed: int) -> str:
    """Format reverse status for console output."""
    return f"🔵 REVERSE {steer_label} Rear:{rear_dist:.0f}cm [{speed}%]"
