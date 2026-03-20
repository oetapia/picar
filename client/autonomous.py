"""
Autonomous Navigation - Perception-Powered

Enhanced with perception system for:
- Sensor fusion with confidence weighting
- IMU-validated motion detection
- Obstacle tracking with velocity
- Predictive collision avoidance

The original monolithic version is preserved in autonomous_legacy.py.

Key improvements:
- Uses perception system for advanced sensor fusion
- IMU integration prevents false obstacle detection
- Obstacle velocity tracking for better prediction
- Much smaller file (~300 lines vs 600)
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
        
        print("\r🚗 Autonomous ON - Perception-Powered")
        print("\r   Sensor fusion + IMU + Obstacle tracking active")

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
        """Main navigation loop with perception system."""
        while self.autonomous:
            loop_start = time.time()
            
            try:
                # Read all sensors via perception system
                perception_state = hooks.read_perception_state(self.client)
                if perception_state is None:
                    print("\r⚠️  Critical sensors unavailable")
                    hooks.execute_stop(self.client)
                    time.sleep(0.5)
                    continue
                
                # Extract left/right distances from perception obstacles
                left_obs = perception_state.get_obstacle_by_direction('front_left')
                right_obs = perception_state.get_obstacle_by_direction('front_right')
                left = left_obs.distance if left_obs else 999
                right = right_obs.distance if right_obs else 999
                rear = perception_state.rear_clearance
                front_clearance = perception_state.front_clearance
                
                # PRIORITY 1: Emergency checks (perception-aware)
                if hooks.check_emergency_forward_perception(perception_state, self._current_direction):
                    print(f"\r🚨 EMERGENCY STOP! Front:{front_clearance:.0f}cm")
                    hooks.execute_stop(self.client)
                    self._emergency_stop_active = True
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue
                
                if hooks.check_emergency_reverse(self._current_direction, rear):
                    print(f"\r🚨 EMERGENCY STOP REVERSE! Rear:{rear:.0f}cm")
                    hooks.execute_stop(self.client)
                    self._emergency_stop_active = True
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue
                
                # Terrain safety checks (steep incline / tip-over risk)
                if hooks.check_lateral_tilt_danger(perception_state):
                    print(f"\r🚨 TILT DANGER! Roll:{perception_state.terrain_roll:.0f}° — STOP")
                    hooks.execute_stop(self.client)
                    self._emergency_stop_active = True
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue

                if hooks.check_steep_incline(perception_state):
                    print(f"\r🚨 STEEP INCLINE! Pitch:{perception_state.terrain_incline:.0f}° — STOP")
                    hooks.execute_stop(self.client)
                    self._current_direction = "stopped"
                    time.sleep(0.1)
                    continue

                # Predictive braking (perception-aware with velocity)
                if hooks.check_pre_brake_perception(perception_state, self._current_direction):
                    approaching_obs = [o for o in perception_state.obstacles if o.velocity and o.velocity < -hooks.APPROACH_RATE_THRESHOLD]
                    if approaching_obs:
                        vel = approaching_obs[0].velocity
                        print(f"\r⚡ PRE-BRAKE! Obstacle approaching at {-vel:.0f}cm/s")
                    hooks.execute_pre_brake(self.client)
                    time.sleep(0.05)
                
                # Clear emergency flag if safe
                if hooks.should_clear_emergency(front_clearance, rear):
                    self._emergency_stop_active = False
                
                # Update display (throttled)
                self._display_update_counter += 1
                if self._display_update_counter >= 4:
                    self._display_update_counter = 0
                    self._update_display_perception(perception_state)
                
                # Navigate using perception state
                self._navigate_perception(perception_state, left, right, rear)
                
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

    def _navigate_perception(self, state, left: float, right: float, rear: float):
        """Navigation decision logic using perception state."""
        front_clearance = state.front_clearance
        rear_clearance = state.rear_clearance
        
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
        
        # DECISION TREE (using perception-aware hooks)
        if hooks.should_cruise_forward_perception(state):
            self._move_forward(left, right, hooks.CRUISE_SPEED, "CRUISE", state)
        
        elif hooks.should_medium_forward_perception(state):
            self._move_forward(left, right, hooks.MEDIUM_SPEED, "MEDIUM", state)
        
        elif hooks.should_slow_forward_perception(state):
            self._move_forward(left, right, hooks.SLOW_SPEED, "SLOW", state)
        
        elif hooks.should_crawl_forward_perception(state):
            # Check if should reverse instead (perception-aware)
            if hooks.should_tactical_reverse_perception(state):
                self._move_backward(left, right, rear_clearance, hooks.REVERSE_SLOW)
            else:
                self._move_forward(left, right, hooks.CRAWL_SPEED, "CRAWL", state)
        
        elif hooks.should_emergency_reverse(front_clearance, rear_clearance):
            self._move_backward(left, right, rear_clearance, hooks.REVERSE_SLOW)
        
        else:
            # No safe forward movement and not critical enough for reverse - STOP
            if self._current_direction != "stopped":
                hooks.execute_stop(self.client)
                self._current_direction = "stopped"
                print(f"\r⚠️ No safe path: F:{front_clearance:.0f}cm R:{rear_clearance:.0f}cm")

    def _move_forward(self, left: float, right: float, speed: int, mode: str,
                      perception_state=None):
        """Execute forward movement using hooks with terrain compensation."""
        if self._emergency_stop_active:
            return
        
        # Terrain-aware speed adjustment (uphill boost / downhill reduction)
        if perception_state is not None:
            speed = hooks.adjust_speed_for_terrain(speed, perception_state)
        
        hooks.execute_forward(self.client, speed, left, right)
        self._current_direction = "forward"
        
        servo, steer_label = hooks.calculate_steering(left, right)
        status = hooks.format_console_status(mode, steer_label, left, right, speed)
        if perception_state is not None:
            terrain_tag = hooks.format_terrain_status(perception_state)
            if terrain_tag:
                status += f" {terrain_tag}"
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

    def _update_display_perception(self, state):
        """Update OLED display with perception data."""
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
        
        display_text = hooks.format_display_text(
            sensor_data,
            self._current_direction,
            self._emergency_stop_active
        )
        
        # Add perception info
        high_conf = len([o for o in state.obstacles if o.confidence >= 0.8])
        if high_conf > 0:
            display_text += f"\nConf:{high_conf}"
        
        # Add terrain info when on a slope
        terrain_tag = hooks.format_terrain_status(state)
        if terrain_tag:
            display_text += f"\n{terrain_tag}"
        
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
    print("PICAR AUTONOMOUS MODE - Perception-Powered")
    print("="*70)
    print("\nControls:")
    print("  G       — Start autonomous mode")
    print("  SPACE   — Stop autonomous mode")
    print("  Q       — Quit")
    print("="*70)
    print("\nFeatures:")
    print("  ✓ Sensor fusion with confidence weighting")
    print("  ✓ IMU-validated motion detection")
    print("  ✓ Obstacle tracking with velocity")
    print("  ✓ Predictive collision avoidance")
    print(f"  ✓ Terrain-aware speed (uphill boost ≤{hooks.MAX_INCLINE_BOOST}%, "
          f"steep limit {hooks.STEEP_INCLINE_LIMIT:.0f}°, "
          f"tilt limit {hooks.LATERAL_TILT_LIMIT:.0f}°)")
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
