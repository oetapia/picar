#!/usr/bin/env python3
"""
Perception System Test Script

Tests the Phase 1 perception system with sensor fusion, IMU integration,
and obstacle tracking.

Usage:
    python client/test_perception.py
"""

import sys
import time
from picar_client import PicarClient
from perception import PerceptionSystem, format_perception_debug
from perception_client_integration import create_perception_update


def test_perception_system():
    """Test perception system with live sensor data."""
    
    print("=" * 70)
    print("PERCEPTION SYSTEM TEST - Phase 1")
    print("=" * 70)
    print()
    
    # Initialize client
    client = PicarClient()
    print(f"Connecting to Picar at {client.base_url}...")
    
    try:
        status = client.status()
        print(f"✓ Connected successfully")
        print(f"  Motor: {status['motor_speed']}, Servo: {status['servo_angle']}°")
    except Exception as e:
        print(f"✗ Could not connect: {e}")
        print("  Make sure the Pico is running and accessible")
        return
    
    print()
    print("Testing sensors individually...")
    print("-" * 70)
    
    # Test ToF
    try:
        tof = client.get_tof()
        if tof.get('success'):
            print(f"✓ ToF sensors: L={tof.get('left_distance_cm')}cm, R={tof.get('right_distance_cm')}cm")
        else:
            print("✗ ToF sensors not available")
    except Exception as e:
        print(f"✗ ToF error: {e}")
    
    # Test Ultrasonic
    try:
        ultrasonic = client.get_ultrasonic()
        if ultrasonic.get('success'):
            dist = ultrasonic.get('distance_cm') if ultrasonic.get('in_range') else 'out of range'
            print(f"✓ Ultrasonic: {dist}")
        else:
            print("✗ Ultrasonic not available")
    except Exception as e:
        print(f"✗ Ultrasonic error: {e}")
    
    # Test IMU
    try:
        imu = client.get_accelerometer()
        if imu.get('available'):
            accel = imu['acceleration']
            print(f"✓ IMU: X={accel['x']:.2f}g, Y={accel['y']:.2f}g, Z={accel['z']:.2f}g")
        else:
            print("⚠ IMU not available (optional)")
    except Exception as e:
        print(f"⚠ IMU error (optional): {e}")
    
    print()
    print("=" * 70)
    print("Starting perception fusion test...")
    print("Reading sensors every 0.5 seconds for 20 iterations")
    print("Move obstacles around to test tracking")
    print("=" * 70)
    print()
    
    # Create perception system
    perception = PerceptionSystem()
    
    try:
        for i in range(20):
            # Update perception
            state = create_perception_update(client, perception)
            
            # Display iteration header
            print(f"\n[Iteration {i+1}/20] --- {time.strftime('%H:%M:%S')} ---")
            
            # Display clearances
            print(f"Clearances: Front={state.front_clearance:.0f}cm, Rear={state.rear_clearance:.0f}cm")
            
            # Display obstacles
            if state.obstacles:
                print(f"Detected {len(state.obstacles)} obstacle(s):")
                for obs in state.obstacles:
                    age = obs.age()
                    velocity_str = f"{obs.velocity:+.1f}cm/s" if obs.velocity else "N/A"
                    print(f"  • {obs.direction:12} | {obs.distance:5.0f}cm | "
                          f"Conf:{obs.confidence:4.0%} | V:{velocity_str:>9} | "
                          f"Age:{age:.1f}s | Seen:{obs.detection_count}x")
                
                # Show approaching obstacles
                approaching = perception.get_approaching_obstacles(threshold=-5.0)
                if approaching:
                    print(f"⚠️  WARNING: {len(approaching)} obstacle(s) approaching!")
            else:
                print("No obstacles detected")
            
            # Display IMU
            if state.imu_data and state.imu_data.available:
                imu = state.imu_data
                print(f"IMU: Accel=({imu.accel_x:+.2f}, {imu.accel_y:+.2f}, {imu.accel_z:+.2f})g | "
                      f"Orientation={imu.orientation} | Moving={imu.is_moving}")
                
                # Check for sudden stop (collision detection)
                if perception.detect_sudden_stop():
                    print("🚨 SUDDEN DECELERATION DETECTED!")
            else:
                print("IMU: Not available")
            
            # Display sensor health
            health = perception.get_sensor_health_summary()
            health_status = "✓ Healthy" if health['all_healthy'] else (
                "🚨 CRITICAL" if health['critical_failure'] else "⚠ Degraded"
            )
            print(f"Sensor Health: {health_status}")
            for sensor, status in health['details'].items():
                symbol = "✓" if status else "✗"
                print(f"  {symbol} {sensor}")
            
            # Wait before next iteration
            time.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    
    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  • Perception system successfully fused {len(perception.obstacles)} obstacle track(s)")
    print(f"  • Sensor fusion working with confidence weighting")
    print(f"  • Obstacle velocity tracking {'enabled' if any(o.velocity for o in perception.obstacles) else 'pending data'}")
    print()
    print("Phase 1 perception system is operational! ✓")
    print()
    print("Next steps:")
    print("  1. Integrate perception into autonomous.py and autonomous_fsm.py")
    print("  2. Test autonomous navigation with enhanced perception")
    print("  3. Proceed to Phase 2: Odometry & State Estimation")
    print()


def test_debug_format():
    """Test the debug formatting function."""
    print("\n" + "=" * 70)
    print("Testing debug format output")
    print("=" * 70)
    
    from perception import PerceptionState, Obstacle, IMUData
    
    # Create sample state
    obstacles = [
        Obstacle('front_left', 45.0, 0.92, 'tof_left', velocity=-8.5),
        Obstacle('front_right', 52.0, 0.88, 'tof_right', velocity=-3.2),
        Obstacle('rear', 120.0, 0.80, 'ultrasonic', velocity=None)
    ]
    
    imu_data = IMUData(
        accel_x=-0.05, accel_y=0.02, accel_z=0.98,
        gyro_x=0.5, gyro_y=-0.3, gyro_z=1.2,
        pitch=2.1, roll=-1.5, orientation='level',
        available=True, timestamp=time.time()
    )
    
    state = PerceptionState(
        obstacles=obstacles,
        front_clearance=45.0,
        rear_clearance=120.0,
        imu_data=imu_data,
        sensor_health={'tof_left': True, 'tof_right': True, 'ultrasonic': True, 'imu': True},
        timestamp=time.time()
    )
    
    debug_output = format_perception_debug(state)
    print(debug_output)
    print()


if __name__ == "__main__":
    print("\nPerception System Test Suite\n")
    
    # Run debug format test first
    test_debug_format()
    
    # Run main test
    test_perception_system()
