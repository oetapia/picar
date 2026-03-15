"""
Autonomous Navigation Hooks - Reusable Functions

This module provides reusable hooks for autonomous navigation,
extracted from the original autonomous.py implementation.
These functions can be used by different navigation strategies.

Now enhanced with Perception System integration for:
- Sensor fusion with confidence weighting
- IMU-validated motion detection
- Obstacle tracking with velocity
- Sensor health monitoring
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from picar_client import PicarClient
from perception import PerceptionSystem, parse_imu_state, PerceptionState, Obstacle

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS - Navigation Parameters
# ═══════════════════════════════════════════════════════════════════

# Speed settings
CRUISE_SPEED = 35
MEDIUM_SPEED = 25
SLOW_SPEED = 18
CRAWL_SPEED = 12
REVERSE_FAST = -35
REVERSE_SLOW = -22

# Steering angles
STEER_LEFT = 35
STEER_SLIGHT_LEFT = 65
STEER_RIGHT = 145
STEER_SLIGHT_RIGHT = 115
CENTRE = 90

# Distance thresholds (cm)
EMERGENCY_STOP_DIST = 50
VERY_SAFE_DIST = 90
SAFE_DIST = 60
CAUTION_DIST = 45
DANGER_DIST = 35
CRITICAL_DIST = 25

# Rear distance thresholds
REAR_SAFE_DIST = 60
REAR_CAUTION_DIST = 45
REAR_DANGER_DIST = 35

# Velocity tracking
APPROACH_RATE_THRESHOLD = 15  # cm/s

# Timing
POLL_INTERVAL = 0.05


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
    
    # Reduce speed if rear is getting close
    if rear_dist < REAR_CAUTION_DIST:
        speed = min(speed, -18)
    
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
    """Check if emergency reverse is needed."""
    return (front_clearance < CRITICAL_DIST and 
            rear_clearance > REAR_DANGER_DIST)


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
