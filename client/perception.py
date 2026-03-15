"""
Perception System - Sensor Fusion & Obstacle Tracking

This module implements Phase 1 of the Autonomous Improvement Roadmap:
- Sensor fusion with confidence weighting
- IMU integration for motion validation
- Obstacle persistence tracking
- Sensor health monitoring

Industry Inspiration: Waymo/Tesla sensor fusion architecture adapted for toy car
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time


# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class IMUData:
    """IMU sensor data from MPU6050."""
    accel_x: float  # g
    accel_y: float  # g
    accel_z: float  # g
    gyro_x: float   # deg/s
    gyro_y: float   # deg/s
    gyro_z: float   # deg/s
    pitch: float    # deg
    roll: float     # deg
    orientation: str
    available: bool
    timestamp: float
    
    @property
    def is_moving(self, threshold: float = 0.1) -> bool:
        """Check if vehicle is moving based on acceleration."""
        return abs(self.accel_x) > threshold or abs(self.accel_y) > threshold
    
    @property
    def acceleration_magnitude(self) -> float:
        """Calculate total acceleration magnitude."""
        return (self.accel_x**2 + self.accel_y**2 + self.accel_z**2)**0.5


@dataclass
class Obstacle:
    """Represents a detected obstacle."""
    direction: str  # 'front_left', 'front_right', 'front', 'rear'
    distance: float  # cm
    confidence: float  # 0.0 to 1.0
    sensor: str  # 'tof_left', 'tof_right', 'ultrasonic'
    velocity: Optional[float] = None  # cm/s (negative = approaching)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    detection_count: int = 1
    
    def age(self) -> float:
        """Get obstacle age in seconds."""
        return time.time() - self.first_seen
    
    def time_since_update(self) -> float:
        """Get time since last detection in seconds."""
        return time.time() - self.last_seen
    
    def update(self, distance: float, confidence: float):
        """Update obstacle with new detection."""
        # Calculate velocity if we have previous distance
        time_delta = time.time() - self.last_seen
        if time_delta > 0:
            velocity = (distance - self.distance) / time_delta
            # Smooth velocity with exponential moving average
            if self.velocity is None:
                self.velocity = velocity
            else:
                self.velocity = 0.7 * self.velocity + 0.3 * velocity
        
        self.distance = distance
        self.confidence = confidence
        self.last_seen = time.time()
        self.detection_count += 1


@dataclass
class PerceptionState:
    """Complete perception state after sensor fusion."""
    obstacles: List[Obstacle]
    front_clearance: float  # cm (minimum front distance)
    rear_clearance: float   # cm
    imu_data: Optional[IMUData]
    sensor_health: Dict[str, bool]
    timestamp: float
    
    def get_obstacle_by_direction(self, direction: str) -> Optional[Obstacle]:
        """Get obstacle in specific direction."""
        for obs in self.obstacles:
            if obs.direction == direction:
                return obs
        return None
    
    def get_closest_front_obstacle(self) -> Optional[Obstacle]:
        """Get closest front obstacle."""
        front_obstacles = [o for o in self.obstacles if o.direction.startswith('front')]
        if front_obstacles:
            return min(front_obstacles, key=lambda o: o.distance)
        return None
    
    def is_moving_validated(self) -> bool:
        """Check if vehicle is moving (validated by IMU)."""
        if self.imu_data and self.imu_data.available:
            return self.imu_data.is_moving
        return False


# ═══════════════════════════════════════════════════════════════════
# PERCEPTION SYSTEM
# ═══════════════════════════════════════════════════════════════════

class PerceptionSystem:
    """
    Unified perception layer with sensor fusion.
    
    Combines ToF, Ultrasonic, and IMU sensors with confidence weighting
    to create a robust world model for autonomous navigation.
    """
    
    # Confidence weights (industry-inspired)
    TOF_CONFIDENCE_BASE = 0.9      # ToF sensors are very reliable
    ULTRASONIC_CONFIDENCE_BASE = 0.8  # Ultrasonic slightly less reliable
    
    # Distance thresholds for confidence adjustment
    TOF_RELIABLE_MAX = 200  # cm - beyond this, confidence drops
    ULTRASONIC_RELIABLE_MAX = 300  # cm
    
    # Obstacle tracking parameters
    OBSTACLE_TIMEOUT = 2.0  # seconds - remove obstacles not seen for this long
    OBSTACLE_MERGE_DISTANCE = 10  # cm - merge obstacles within this distance
    
    # Motion validation thresholds
    MOTION_ACCEL_THRESHOLD = 0.15  # g - above this, consider moving
    STATIONARY_CONFIDENCE_BOOST = 0.1  # Boost confidence when stationary
    
    def __init__(self):
        """Initialize perception system."""
        self.obstacles: List[Obstacle] = []
        self.last_imu_data: Optional[IMUData] = None
        self._previous_distances: Dict[str, Tuple[float, float]] = {}  # (distance, timestamp)
    
    def fuse_sensors(self, 
                    tof_left: Optional[float],
                    tof_right: Optional[float],
                    ultrasonic_rear: Optional[float],
                    imu_data: Optional[IMUData] = None) -> PerceptionState:
        """
        Fuse all sensors into unified perception state.
        
        Args:
            tof_left: Left ToF distance in cm (None if unavailable)
            tof_right: Right ToF distance in cm (None if unavailable)
            ultrasonic_rear: Rear ultrasonic distance in cm (None if unavailable)
            imu_data: IMU sensor data (None if unavailable)
        
        Returns:
            PerceptionState with fused sensor data
        """
        current_time = time.time()
        new_obstacles: List[Obstacle] = []
        
        # Store IMU data
        self.last_imu_data = imu_data
        is_moving = imu_data.is_moving if imu_data and imu_data.available else False
        
        # Process front left ToF
        if tof_left is not None and tof_left > 0 and tof_left < 999:
            confidence = self._calculate_tof_confidence(tof_left, is_moving)
            obs = Obstacle(
                direction='front_left',
                distance=tof_left,
                confidence=confidence,
                sensor='tof_left'
            )
            new_obstacles.append(obs)
        
        # Process front right ToF
        if tof_right is not None and tof_right > 0 and tof_right < 999:
            confidence = self._calculate_tof_confidence(tof_right, is_moving)
            obs = Obstacle(
                direction='front_right',
                distance=tof_right,
                confidence=confidence,
                sensor='tof_right'
            )
            new_obstacles.append(obs)
        
        # Process rear ultrasonic
        if ultrasonic_rear is not None and ultrasonic_rear > 0 and ultrasonic_rear < 999:
            confidence = self._calculate_ultrasonic_confidence(ultrasonic_rear, is_moving)
            obs = Obstacle(
                direction='rear',
                distance=ultrasonic_rear,
                confidence=confidence,
                sensor='ultrasonic'
            )
            new_obstacles.append(obs)
        
        # Update obstacle tracking
        self._update_obstacle_tracking(new_obstacles)
        
        # Calculate clearances
        front_clearance = self._calculate_front_clearance()
        rear_clearance = self._calculate_rear_clearance()
        
        # Assess sensor health
        sensor_health = {
            'tof_left': tof_left is not None and tof_left < 999,
            'tof_right': tof_right is not None and tof_right < 999,
            'ultrasonic': ultrasonic_rear is not None and ultrasonic_rear < 999,
            'imu': imu_data is not None and imu_data.available if imu_data else False
        }
        
        return PerceptionState(
            obstacles=self.obstacles.copy(),
            front_clearance=front_clearance,
            rear_clearance=rear_clearance,
            imu_data=imu_data,
            sensor_health=sensor_health,
            timestamp=current_time
        )
    
    def _calculate_tof_confidence(self, distance: float, is_moving: bool) -> float:
        """Calculate confidence for ToF sensor reading."""
        confidence = self.TOF_CONFIDENCE_BASE
        
        # Reduce confidence for far distances (sensor less accurate)
        if distance > self.TOF_RELIABLE_MAX:
            confidence *= 0.7
        
        # Boost confidence when stationary (less noise)
        if not is_moving:
            confidence = min(1.0, confidence + self.STATIONARY_CONFIDENCE_BOOST)
        
        return confidence
    
    def _calculate_ultrasonic_confidence(self, distance: float, is_moving: bool) -> float:
        """Calculate confidence for ultrasonic sensor reading."""
        confidence = self.ULTRASONIC_CONFIDENCE_BASE
        
        # Ultrasonic gets less reliable at far distances
        if distance > self.ULTRASONIC_RELIABLE_MAX:
            confidence *= 0.6
        
        # Boost confidence when stationary
        if not is_moving:
            confidence = min(1.0, confidence + self.STATIONARY_CONFIDENCE_BOOST)
        
        return confidence
    
    def _update_obstacle_tracking(self, new_obstacles: List[Obstacle]):
        """
        Update persistent obstacle tracking.
        
        Matches new detections with existing obstacles, calculates velocities,
        and removes stale obstacles.
        """
        current_time = time.time()
        matched_indices = set()
        
        # Match new obstacles with existing ones
        for new_obs in new_obstacles:
            best_match_idx = None
            best_match_distance = float('inf')
            
            for idx, existing_obs in enumerate(self.obstacles):
                if idx in matched_indices:
                    continue
                
                # Only match same direction and sensor
                if (existing_obs.direction == new_obs.direction and
                    existing_obs.sensor == new_obs.sensor):
                    
                    # Check if distances are close enough to be same obstacle
                    dist_diff = abs(existing_obs.distance - new_obs.distance)
                    if dist_diff < self.OBSTACLE_MERGE_DISTANCE and dist_diff < best_match_distance:
                        best_match_idx = idx
                        best_match_distance = dist_diff
            
            if best_match_idx is not None:
                # Update existing obstacle
                self.obstacles[best_match_idx].update(new_obs.distance, new_obs.confidence)
                matched_indices.add(best_match_idx)
            else:
                # Add as new obstacle
                self.obstacles.append(new_obs)
        
        # Remove stale obstacles (not seen recently)
        self.obstacles = [
            obs for obs in self.obstacles
            if obs.time_since_update() < self.OBSTACLE_TIMEOUT
        ]
    
    def _calculate_front_clearance(self) -> float:
        """Calculate front clearance (worst case from both ToF sensors)."""
        front_obstacles = [
            obs for obs in self.obstacles
            if obs.direction in ['front_left', 'front_right', 'front']
        ]
        
        if front_obstacles:
            # Return minimum distance (worst case)
            return min(obs.distance for obs in front_obstacles)
        
        return 999.0  # No obstacles detected
    
    def _calculate_rear_clearance(self) -> float:
        """Calculate rear clearance."""
        rear_obstacle = self.get_rear_obstacle()
        if rear_obstacle:
            return rear_obstacle.distance
        return 999.0
    
    def get_rear_obstacle(self) -> Optional[Obstacle]:
        """Get rear obstacle."""
        for obs in self.obstacles:
            if obs.direction == 'rear':
                return obs
        return None
    
    def get_high_confidence_obstacles(self, min_confidence: float = 0.7) -> List[Obstacle]:
        """Get obstacles above confidence threshold."""
        return [obs for obs in self.obstacles if obs.confidence >= min_confidence]
    
    def get_approaching_obstacles(self, threshold: float = -10.0) -> List[Obstacle]:
        """
        Get obstacles that are approaching (negative velocity).
        
        Args:
            threshold: Velocity threshold in cm/s (negative = approaching)
        """
        return [
            obs for obs in self.obstacles
            if obs.velocity is not None and obs.velocity < threshold
        ]
    
    def detect_sudden_stop(self) -> bool:
        """
        Detect sudden deceleration (collision indicator).
        
        Uses IMU accelerometer to detect rapid deceleration.
        """
        if not self.last_imu_data or not self.last_imu_data.available:
            return False
        
        # Check for sudden deceleration in forward direction
        # (assuming forward is negative X-axis on MPU6050)
        sudden_decel_threshold = -1.5  # g
        return self.last_imu_data.accel_x < sudden_decel_threshold
    
    def get_sensor_health_summary(self) -> Dict[str, any]:
        """Get summary of sensor health status."""
        health = {
            'all_healthy': False,
            'critical_failure': False,
            'degraded': False,
            'details': {}
        }
        
        if not self.last_imu_data:
            return health
        
        # Check each sensor
        tof_left_ok = any(o.sensor == 'tof_left' and o.time_since_update() < 1.0 for o in self.obstacles)
        tof_right_ok = any(o.sensor == 'tof_right' and o.time_since_update() < 1.0 for o in self.obstacles)
        ultrasonic_ok = any(o.sensor == 'ultrasonic' and o.time_since_update() < 1.0 for o in self.obstacles)
        imu_ok = self.last_imu_data.available
        
        health['details'] = {
            'tof_left': tof_left_ok,
            'tof_right': tof_right_ok,
            'ultrasonic': ultrasonic_ok,
            'imu': imu_ok
        }
        
        # All healthy if at least one ToF and IMU working
        health['all_healthy'] = (tof_left_ok or tof_right_ok) and imu_ok
        
        # Critical failure if no ToF sensors working
        health['critical_failure'] = not (tof_left_ok or tof_right_ok)
        
        # Degraded if some sensors not working
        health['degraded'] = not (tof_left_ok and tof_right_ok and ultrasonic_ok and imu_ok)
        
        return health


# ═══════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def parse_imu_state(imu_state: dict) -> Optional[IMUData]:
    """
    Parse IMU state dictionary into IMUData object.
    
    Args:
        imu_state: Dictionary from accelerometer.get_state()
    
    Returns:
        IMUData object or None if unavailable
    """
    if not imu_state or not imu_state.get('available'):
        return None
    
    try:
        return IMUData(
            accel_x=imu_state['acceleration']['x'],
            accel_y=imu_state['acceleration']['y'],
            accel_z=imu_state['acceleration']['z'],
            gyro_x=imu_state['gyroscope']['x'],
            gyro_y=imu_state['gyroscope']['y'],
            gyro_z=imu_state['gyroscope']['z'],
            pitch=imu_state['tilt']['pitch'],
            roll=imu_state['tilt']['roll'],
            orientation=imu_state.get('orientation', 'unknown'),
            available=True,
            timestamp=imu_state.get('timestamp', time.time())
        )
    except (KeyError, TypeError):
        return None


def format_perception_debug(state: PerceptionState) -> str:
    """
    Format perception state for debug display.
    
    Returns:
        Formatted string for console/OLED display
    """
    lines = []
    lines.append("=== PERCEPTION ===")
    lines.append(f"Front: {state.front_clearance:.0f}cm | Rear: {state.rear_clearance:.0f}cm")
    
    # Obstacles
    if state.obstacles:
        lines.append(f"Obstacles: {len(state.obstacles)}")
        for obs in state.obstacles[:3]:  # Show top 3
            velocity_str = f"{obs.velocity:+.0f}cm/s" if obs.velocity else "---"
            lines.append(f"  {obs.direction}: {obs.distance:.0f}cm ({obs.confidence:.0%}) {velocity_str}")
    else:
        lines.append("Obstacles: None")
    
    # IMU
    if state.imu_data and state.imu_data.available:
        lines.append(f"IMU: {state.imu_data.orientation} | Moving: {state.imu_data.is_moving}")
    else:
        lines.append("IMU: Unavailable")
    
    # Sensor health
    health = [k for k, v in state.sensor_health.items() if v]
    lines.append(f"Health: {', '.join(health) if health else 'None'}")
    
    return '\n'.join(lines)
