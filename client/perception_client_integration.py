"""
Perception Client Integration

Helper functions to integrate PerceptionSystem with PicarClient API.
Bridges the gap between API responses and perception data structures.
"""

from typing import Optional, Tuple
from perception import PerceptionSystem, PerceptionState, IMUData, parse_imu_state


def read_sensors_for_perception(client) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[IMUData]]:
    """
    Read all sensors from PicarClient and prepare for perception fusion.
    
    Args:
        client: PicarClient instance
    
    Returns:
        tuple: (tof_left, tof_right, ultrasonic_rear, imu_data)
    """
    tof_left = None
    tof_right = None
    ultrasonic_rear = None
    imu_data = None
    
    # Read ToF sensors
    try:
        tof = client.get_tof()
        if tof.get('success'):
            tof_left = tof.get('left_distance_cm')
            tof_right = tof.get('right_distance_cm')
            
            # Treat None or out-of-range as 999
            if tof_left is None:
                tof_left = 999.0
            if tof_right is None:
                tof_right = 999.0
    except Exception as e:
        print(f"Warning: ToF read failed: {e}")
    
    # Read ultrasonic
    try:
        ultrasonic = client.get_ultrasonic()
        if ultrasonic.get('success'):
            if ultrasonic.get('in_range'):
                ultrasonic_rear = ultrasonic.get('distance_cm', 999.0)
            else:
                ultrasonic_rear = 999.0
    except Exception as e:
        print(f"Warning: Ultrasonic read failed: {e}")
    
    # Read IMU/accelerometer
    try:
        imu_state = client.get_accelerometer()
        imu_data = parse_imu_state(imu_state)
    except Exception as e:
        print(f"Warning: IMU read failed: {e}")
    
    return tof_left, tof_right, ultrasonic_rear, imu_data


def create_perception_update(client, perception_system: PerceptionSystem) -> PerceptionState:
    """
    Convenience function to read sensors and update perception in one call.
    
    Args:
        client: PicarClient instance
        perception_system: PerceptionSystem instance
    
    Returns:
        PerceptionState with fused sensor data
    """
    tof_left, tof_right, ultrasonic_rear, imu_data = read_sensors_for_perception(client)
    return perception_system.fuse_sensors(tof_left, tof_right, ultrasonic_rear, imu_data)
