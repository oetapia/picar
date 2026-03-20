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

import json
import math
import logging
import os
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
# VEHICLE PROFILE LOADING
# ═══════════════════════════════════════════════════════════════════

# ── Active profile ───────────────────────────────────────────────
# Change this string to switch between motor configurations:
#   "single_motor"  — original fast single-motor (motor.py)
#   "dual_motor"    — slower dual-motor setup (motor2.py)
ACTIVE_PROFILE = "dual_motor"

_PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "vehicle_profiles.json")


def load_vehicle_profile(profile_name: str = ACTIVE_PROFILE) -> dict:
    """
    Load a vehicle profile from vehicle_profiles.json.

    Args:
        profile_name: Key in the JSON file (e.g. "single_motor", "dual_motor").

    Returns:
        Profile dict with dimensions, speed_calibration, motor, physics, terrain.

    Raises:
        FileNotFoundError: If vehicle_profiles.json is missing.
        KeyError: If the requested profile doesn't exist.
    """
    with open(_PROFILES_PATH, "r") as f:
        profiles = json.load(f)

    if profile_name not in profiles:
        available = ", ".join(profiles.keys())
        raise KeyError(
            f"Vehicle profile '{profile_name}' not found. "
            f"Available profiles: {available}"
        )

    profile = profiles[profile_name]
    log.info("Loaded vehicle profile: %s — %s",
             profile_name, profile.get("description", ""))
    return profile


# Load the active profile at module import time
_PROFILE = load_vehicle_profile()


# ═══════════════════════════════════════════════════════════════════
# VEHICLE PHYSICS MODEL (loaded from profile)
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VehicleModel:
    """
    Physics model derived from real measurements.

    All parameters are loaded from vehicle_profiles.json so different
    motor configurations (single vs dual motor) can be swapped by
    changing ACTIVE_PROFILE.

    The sqrt speed mapping from motor.py / motor2.py is used to
    interpolate between the two measured calibration points.
    """

    # ── Dimensions (cm) ──────────────────────────────────────────
    length: float = 34.0
    body_width: float = 14.0
    overall_width: float = 16.0          # including tyres
    height: float = 24.0
    wheelbase: float = 22.0              # estimated
    tof_spacing: float = 11.0            # sensor-to-sensor

    # ── Motor dead zone (minimum % that moves) ───────────────────
    motor_dead_zone: int = 5

    # ── PWM formula cutoff ───────────────────────────────────────
    # Both motor.py and motor2.py use normalised = sqrt((pct - 5) / 95)
    # This is the zero-point of the PWM curve, NOT the dead zone.
    _pwm_cutoff: int = 5

    # ── Measured speed calibration ───────────────────────────────
    # motor% → cm/s  (two real data-points; rest interpolated)
    _speed_cal: Dict[int, float] = field(default_factory=lambda: {
        100: 11.1,
        50: 9.4,
    })

    # ── Timing budget (seconds) ──────────────────────────────────
    sensor_poll_s: float = 0.05          # 20 Hz loop
    network_rtt_s: float = 0.10          # WiFi round-trip
    motor_lag_s: float = 0.05            # H-bridge response
    safety_factor: float = 1.3           # ISO 26262 recommended margin

    # ── Braking estimate ─────────────────────────────────────────
    deceleration_cmss: float = 200.0     # rough coast-to-stop

    # ── Safety margins ───────────────────────────────────────────
    side_margin_cm: float = 5.0          # clearance per side
    front_margin_cm: float = 5.0         # extra buffer after braking

    # ── Hysteresis band ──────────────────────────────────────────
    hysteresis_cm: float = 3.0           # enter/exit offset

    # ── Helpers ──────────────────────────────────────────────────
    @property
    def reaction_time_s(self) -> float:
        """Total worst-case reaction time."""
        return (self.sensor_poll_s + self.network_rtt_s + self.motor_lag_s) * self.safety_factor

    @property
    def _k_speed(self) -> float:
        """Speed constant derived from 100% calibration point."""
        return self._speed_cal.get(100, 11.1)

    def speed_at(self, motor_pct: int) -> float:
        """
        Estimate true speed (cm/s) for a motor percentage.

        Uses the sqrt mapping from motor.py / motor2.py to interpolate
        between the measured calibration points.

        Note: The PWM cutoff (5%) is used for interpolation — this matches
        the hardware formula in both motor.py and motor2.py:
            normalised = sqrt((pct - 5) / 95)
        The dead zone (motor_dead_zone) is a *separate* concept: the minimum
        motor-% that actually produces movement, used by the navigation layer.
        """
        if motor_pct in self._speed_cal:
            return self._speed_cal[motor_pct]
        if motor_pct <= self._pwm_cutoff:
            return 0.0
        # motor.py / motor2.py: normalised = sqrt((pct - 5) / 95)
        # k = speed_at_100% / sqrt((100-5)/95) = speed_at_100%
        norm = math.sqrt(max(0, (motor_pct - self._pwm_cutoff)
                                / max(1, 100.0 - self._pwm_cutoff)))
        return self._k_speed * norm

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


def _build_vehicle_model(profile: dict) -> VehicleModel:
    """Construct a VehicleModel from a loaded profile dict."""
    dims = profile.get("dimensions", {})
    cal = profile.get("speed_calibration", {})
    phys = profile.get("physics", {})
    motor = profile.get("motor", {})

    speed_cal = {int(k): float(v) for k, v in cal.items()}

    return VehicleModel(
        length=dims.get("length", 34.0),
        body_width=dims.get("body_width", 14.0),
        overall_width=dims.get("overall_width", 16.0),
        height=dims.get("height", 24.0),
        wheelbase=dims.get("wheelbase", 22.0),
        tof_spacing=dims.get("tof_spacing", 11.0),
        motor_dead_zone=motor.get("dead_zone", 5),
        _speed_cal=speed_cal,
        sensor_poll_s=phys.get("sensor_poll_s", 0.05),
        network_rtt_s=phys.get("network_rtt_s", 0.10),
        motor_lag_s=phys.get("motor_lag_s", 0.05),
        safety_factor=phys.get("safety_factor", 1.3),
        deceleration_cmss=phys.get("deceleration_cmss", 200.0),
        side_margin_cm=phys.get("side_margin_cm", 5.0),
        front_margin_cm=phys.get("front_margin_cm", 5.0),
        hysteresis_cm=phys.get("hysteresis_cm", 3.0),
    )


# Singleton vehicle model (built from active profile)
VEHICLE = _build_vehicle_model(_PROFILE)


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS — loaded from active profile (physics-derived where possible)
# ═══════════════════════════════════════════════════════════════════

# Speed settings (motor %) — from profile
_motor = _PROFILE.get("motor", {})
MOTOR_DEADZONE = _motor.get("dead_zone", 5)
CRUISE_SPEED   = _motor.get("cruise_speed", 80)
CAUTIOUS_SPEED = _motor.get("cautious_speed", 50)
MINIMUM_SPEED  = _motor.get("minimum_speed", 20)

# Legacy aliases (so FSM state names still map cleanly)
MEDIUM_SPEED = CAUTIOUS_SPEED
SLOW_SPEED   = MINIMUM_SPEED
CRAWL_SPEED  = MINIMUM_SPEED           # dual motor: distinct from SLOW thanks to wide range
REVERSE_FAST = _motor.get("reverse_fast", -60)
REVERSE_SLOW = _motor.get("reverse_slow", -25)

# Steering angles (hardware — same for all profiles)
STEER_LEFT = 35
STEER_SLIGHT_LEFT = 65
STEER_RIGHT = 145
STEER_SLIGHT_RIGHT = 115
CENTRE = 90

# ── Physics-derived distance thresholds (cm) ─────────────────────
# Each threshold = stopping-distance for that speed band, rounded up
# to the nearest 5 cm for sensor granularity.
# With the dual-motor car (~11 cm/s max), stopping distances are tiny
# (~8 cm), so we apply sensible minimums.
_round5 = lambda x: int(math.ceil(x / 5.0)) * 5

_emergency_physics  = _round5(VEHICLE.stopping_distance(CRUISE_SPEED))
EMERGENCY_STOP_DIST = max(15, _emergency_physics)     # at least 15 cm
VERY_SAFE_DIST      = max(40, EMERGENCY_STOP_DIST + 25)
SAFE_DIST           = max(30, EMERGENCY_STOP_DIST + 15)
CAUTION_DIST        = max(22, _round5(VEHICLE.stopping_distance(SLOW_SPEED) + 10))
DANGER_DIST         = max(17, _round5(VEHICLE.stopping_distance(CRAWL_SPEED) + 7))
CRITICAL_DIST       = max(12, _round5(VEHICLE.stopping_distance(CRAWL_SPEED)))

# ── Hysteresis enter/exit pairs ──────────────────────────────────
CRUISE_ENTER  = VERY_SAFE_DIST + VEHICLE.hysteresis_cm
CRUISE_EXIT   = VERY_SAFE_DIST - VEHICLE.hysteresis_cm
MEDIUM_ENTER  = SAFE_DIST + VEHICLE.hysteresis_cm
MEDIUM_EXIT   = SAFE_DIST - VEHICLE.hysteresis_cm
SLOW_ENTER    = CAUTION_DIST + VEHICLE.hysteresis_cm
SLOW_EXIT     = CAUTION_DIST - VEHICLE.hysteresis_cm
CRAWL_ENTER   = DANGER_DIST + VEHICLE.hysteresis_cm
CRAWL_EXIT    = DANGER_DIST - VEHICLE.hysteresis_cm

# ── Rear distance thresholds ─────────────────────────────────────
REAR_SAFE_DIST    = 60
REAR_CAUTION_DIST = 45
REAR_DANGER_DIST  = max(10, _round5(VEHICLE.stopping_distance(abs(REVERSE_SLOW))))

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

# ── Terrain / incline parameters (from profile) ──────────────────
_terrain = _PROFILE.get("terrain", {})
INCLINE_THRESHOLD   = _terrain.get("incline_threshold", 5.0)
STEEP_INCLINE_LIMIT = _terrain.get("steep_incline_limit", 35.0)
MAX_INCLINE_BOOST   = _terrain.get("max_incline_boost", 15)
DOWNHILL_REDUCTION  = _terrain.get("downhill_reduction", 10)
LATERAL_TILT_LIMIT  = _terrain.get("lateral_tilt_limit", 25.0)

# ── Log computed thresholds so operators can verify ──────────────
log.info("Profile '%s' — speeds: cruise=%d%% (%.1f cm/s)  cautious=%d%%  "
         "minimum=%d%%  dead_zone=%d%%",
         ACTIVE_PROFILE, CRUISE_SPEED, VEHICLE.speed_at(CRUISE_SPEED),
         CAUTIOUS_SPEED, MINIMUM_SPEED, MOTOR_DEADZONE)
log.info("Thresholds: E-stop=%dcm  Safe=%dcm  Caution=%dcm  Danger=%dcm  "
         "Critical=%dcm  Hysteresis=%.0fcm",
         EMERGENCY_STOP_DIST, SAFE_DIST, CAUTION_DIST, DANGER_DIST,
         CRITICAL_DIST, VEHICLE.hysteresis_cm)


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
# TERRAIN / INCLINE-AWARE HOOKS
# ═══════════════════════════════════════════════════════════════════

def calculate_incline_speed_boost(pitch_deg: float, base_speed: int) -> int:
    """
    Calculate motor-% adjustment for terrain incline.

    Physics: on a slope of angle θ, gravity pulls the car back with
    force proportional to sin(θ).  We add a motor-% boost that
    compensates for this gravitational drag so the car maintains
    its intended speed.

    On downhill slopes the boost is negative (reduce speed, gravity
    already accelerates the car and braking distances increase).

    Args:
        pitch_deg: Pitch angle in degrees (positive = uphill).
        base_speed: The flat-ground motor-% the navigation decided on.

    Returns:
        Signed motor-% delta to ADD to base_speed.
        Positive = more power (uphill), negative = less power (downhill).
    """
    if abs(pitch_deg) < INCLINE_THRESHOLD:
        return 0  # flat enough — no adjustment

    # sin(θ) ranges 0..1; scale linearly into 0..MAX boost
    sin_theta = math.sin(math.radians(min(abs(pitch_deg), 45.0)))

    if pitch_deg > 0:
        # ── Uphill: boost power ──────────────────────────────────
        boost = int(round(sin_theta * MAX_INCLINE_BOOST))
        # Never exceed 100 % total
        max_allowed = 100 - base_speed
        return min(boost, max_allowed)
    else:
        # ── Downhill: reduce power ───────────────────────────────
        reduction = int(round(sin_theta * DOWNHILL_REDUCTION))
        # Never drop below motor dead-zone (we still want to move)
        max_reduction = base_speed - MOTOR_DEADZONE
        return -min(reduction, max(0, max_reduction))


def adjust_speed_for_terrain(base_speed: int,
                             perception_state: PerceptionState) -> int:
    """
    Single entry-point: adjust motor speed for current terrain.

    Combines incline boost/reduction with dead-zone clamping.
    Safe to call even when IMU is unavailable (returns base_speed unchanged).

    Args:
        base_speed:        Motor-% decided by the navigation layer (positive = forward).
        perception_state:  Current perception state (contains IMU data).

    Returns:
        Adjusted motor-% clamped to [MOTOR_DEADZONE .. 100].
    """
    incline = perception_state.terrain_incline  # 0 if IMU unavailable
    if abs(incline) < INCLINE_THRESHOLD:
        return base_speed  # flat — no change

    delta = calculate_incline_speed_boost(incline, base_speed)
    adjusted = base_speed + delta

    # Clamp: never below dead-zone (stall), never above 100
    adjusted = max(MOTOR_DEADZONE, min(100, adjusted))

    if delta != 0:
        log.info("Terrain adjust: incline=%+.0f° base=%d%% → %d%% (Δ%+d%%)",
                 incline, base_speed, adjusted, delta)

    return adjusted


def check_steep_incline(perception_state: PerceptionState) -> bool:
    """
    Safety check: is the incline too steep to drive?

    Returns True if the pitch exceeds STEEP_INCLINE_LIMIT — the
    navigation layer should stop or switch to crawl.
    """
    return abs(perception_state.terrain_incline) >= STEEP_INCLINE_LIMIT


def check_lateral_tilt_danger(perception_state: PerceptionState) -> bool:
    """
    Safety check: is the lateral tilt (roll) dangerously high?

    Returns True if roll exceeds LATERAL_TILT_LIMIT — the car risks
    tipping over and should stop immediately.
    """
    return abs(perception_state.terrain_roll) >= LATERAL_TILT_LIMIT


def format_terrain_status(perception_state: PerceptionState) -> str:
    """
    Format a compact terrain status string for console / display.

    Returns empty string when terrain is flat (no clutter).
    """
    incline = perception_state.terrain_incline
    roll = perception_state.terrain_roll

    if abs(incline) < INCLINE_THRESHOLD and abs(roll) < INCLINE_THRESHOLD:
        return ""

    parts = []
    if abs(incline) >= INCLINE_THRESHOLD:
        arrow = "⛰↑" if incline > 0 else "⛰↓"
        parts.append(f"{arrow}{abs(incline):.0f}°")
    if abs(roll) >= INCLINE_THRESHOLD:
        parts.append(f"Roll:{roll:+.0f}°")

    return " ".join(parts)


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
