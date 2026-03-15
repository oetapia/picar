import sys
import tty
import termios
import threading
import time

from picar_client import PicarClient

# ── driving parameters ───────────────────────────────────────────────
DRIVE_SPEED        =  55   # normal cruising speed
CORRECTION_SPEED   =  35   # slower speed while steering around an obstacle
REVERSE_SPEED      = -50
STEER_LEFT         =  50   # hard left
STEER_SLIGHT_LEFT  =  75   # gentle left nudge
STEER_RIGHT        = 130   # hard right
STEER_SLIGHT_RIGHT = 105   # gentle right nudge
CENTRE             =  90
POLL_INTERVAL      =  0.15 # seconds between sensor polls
CORRECTION_HOLD    =  0.5  # seconds to hold a steering correction
REVERSE_TIMEOUT    =  1.0  # max seconds to reverse before re-evaluating

# ── distance thresholds (cm) ─────────────────────────────────────────
TOF_STOP_DISTANCE    = 15  # stop if either front sensor detects obstacle closer than this
TOF_SLOW_DISTANCE    = 30  # reduce speed if obstacle detected within this range
TOF_STEER_DISTANCE   = 40  # start steering correction at this distance
ULTRASONIC_STOP_DIST = 20  # stop reversing if rear obstacle closer than this
ULTRASONIC_WARN_DIST = 40  # warning zone for rear obstacles


class AutonomousDriver:
    """
    Uses ToF (Time-of-Flight) sensors for front obstacle detection and
    ultrasonic sensor for rear obstacle detection.

    Sensors:
    ────────────────────────────────────────────────────
    - Dual VL53L0X ToF (front left & right): distance measurements in cm
    - HC-SR04 Ultrasonic (rear): distance measurement in cm
    - MPU-6050 Accelerometer (optional): tilt/orientation awareness

    Navigation logic:
    ────────────────────────────────────────────────────
    Front distances > 40cm        → full speed ahead, centred
    Left < 40cm                   → gentle right nudge
    Right < 40cm                  → gentle left nudge
    Both < 30cm                   → slow down
    Both < 15cm                   → reverse with guidance
    Rear < 20cm while reversing   → stop immediately
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread = None
        self._last_distances = None

    # ── public controls ──────────────────────────────────────────────

    def start(self):
        if self.autonomous:
            return
        self.autonomous = True
        self._last_distances = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("\r🚗 Autonomous ON - Using ToF + Ultrasonic sensors")

    def stop(self):
        self.autonomous = False
        self.client.stop()
        self.client.centre()
        print("\r🛑 Autonomous OFF                ")

    # ── sensor loop (background thread) ─────────────────────────────

    def _loop(self):
        while self.autonomous:
            try:
                # Get ToF sensors (front left and right)
                tof = self.client.get_tof()
                
                if not tof.get('success'):
                    print("\r⚠️  ToF sensors unavailable    ")
                    time.sleep(0.5)
                    continue
                
                left_dist = tof.get('left_distance_cm')
                right_dist = tof.get('right_distance_cm')
                
                # Handle None values (sensor read failures)
                if left_dist is None:
                    left_dist = 999  # Assume clear if sensor fails
                if right_dist is None:
                    right_dist = 999  # Assume clear if sensor fails
                
                # Check if distances changed significantly (> 5cm change)
                distances = (left_dist, right_dist)
                if self._last_distances is None or \
                   abs(left_dist - self._last_distances[0]) > 5 or \
                   abs(right_dist - self._last_distances[1]) > 5:
                    
                    self._last_distances = distances
                    did_maneuver = self._react(left_dist, right_dist)
                    
                    # Force re-evaluation after a timed maneuver
                    if did_maneuver:
                        self._last_distances = None

            except Exception as e:
                print(f"\r⚠️  Sensor error: {e}          ")
                time.sleep(0.5)
                continue

            time.sleep(POLL_INTERVAL)

    # ── decision logic ───────────────────────────────────────────────

    def _react(self, left_dist: float, right_dist: float) -> bool:
        """
        React to current ToF distance measurements.
        Returns True if a timed maneuver was performed (caller resets state).
        
        Args:
            left_dist: Distance in cm from left front ToF sensor
            right_dist: Distance in cm from right front ToF sensor
        """
        min_dist = min(left_dist, right_dist)
        
        # CRITICAL: Both sensors detect very close obstacle - must reverse
        if min_dist < TOF_STOP_DISTANCE:
            print(f"\r🚨 STOP! Front obstacle {min_dist:.0f}cm - reversing")
            self._reverse_guided(left_dist, right_dist)
            return True
        
        # WARNING: Close obstacle - slow down and steer away
        if min_dist < TOF_SLOW_DISTANCE:
            # Determine which side is clearer
            if left_dist < right_dist:
                # Obstacle closer on left - steer right
                self.client.set_motor(CORRECTION_SPEED)
                self.client.set_servo(STEER_RIGHT)
                print(f"\r⚠️  L:{left_dist:.0f}cm R:{right_dist:.0f}cm - hard right")
            else:
                # Obstacle closer on right - steer left
                self.client.set_motor(CORRECTION_SPEED)
                self.client.set_servo(STEER_LEFT)
                print(f"\r⚠️  L:{left_dist:.0f}cm R:{right_dist:.0f}cm - hard left")
            time.sleep(CORRECTION_HOLD)
            return True
        
        # CAUTION: Obstacle detected - gentle correction
        if left_dist < TOF_STEER_DISTANCE or right_dist < TOF_STEER_DISTANCE:
            if left_dist < right_dist:
                # Obstacle on left - nudge right
                self.client.set_motor(CORRECTION_SPEED)
                self.client.set_servo(STEER_SLIGHT_RIGHT)
                print(f"\r↗️  L:{left_dist:.0f}cm R:{right_dist:.0f}cm - nudge right")
            else:
                # Obstacle on right - nudge left
                self.client.set_motor(CORRECTION_SPEED)
                self.client.set_servo(STEER_SLIGHT_LEFT)
                print(f"\r↖️  L:{left_dist:.0f}cm R:{right_dist:.0f}cm - nudge left")
            time.sleep(CORRECTION_HOLD)
            return True
        
        # ALL CLEAR - full speed ahead
        self.client.set_servo(CENTRE)
        self.client.set_motor(DRIVE_SPEED)
        print(f"\r✅ Clear L:{left_dist:.0f}cm R:{right_dist:.0f}cm - forward")
        return False

    def _reverse_guided(self, left_dist: float, right_dist: float):
        """
        Reverse while actively steering away from the front obstacle.
        
        Steering logic: steer toward the side with more clearance to maximize
        escape angle. Monitor rear ultrasonic sensor to avoid backing into obstacles.
        
        Args:
            left_dist: Distance in cm from left front ToF sensor
            right_dist: Distance in cm from right front ToF sensor
        """
        # Determine steering direction based on which front side has more clearance
        if left_dist < right_dist:
            # Right side is clearer - steer right while reversing
            steer = STEER_RIGHT
            print(f"\r⬅️  Reversing right (clearer)")
        else:
            # Left side is clearer - steer left while reversing
            steer = STEER_LEFT
            print(f"\r➡️  Reversing left (clearer)")
        
        self.client.set_motor(REVERSE_SPEED)
        self.client.set_servo(steer)
        
        deadline = time.time() + REVERSE_TIMEOUT
        while self.autonomous and time.time() < deadline:
            time.sleep(0.1)
            try:
                # Check rear ultrasonic sensor
                ultrasonic = self.client.get_ultrasonic()
                if ultrasonic.get('success') and ultrasonic.get('in_range'):
                    rear_dist = ultrasonic.get('distance_cm', 999)
                    if rear_dist < ULTRASONIC_STOP_DIST:
                        print(f"\r🚨 Rear obstacle {rear_dist:.0f}cm - stopping!")
                        break
                    elif rear_dist < ULTRASONIC_WARN_DIST:
                        print(f"\r⚠️  Rear {rear_dist:.0f}cm - caution")
            except Exception:
                # If ultrasonic fails, continue with timeout-based reversal
                pass
        
        if self.autonomous:
            self.client.set_motor(0)
            self.client.centre()


def main():
    client = PicarClient()
    driver = AutonomousDriver(client)

    print(f"Connecting to Picar at {client.base_url}...")
    try:
        s = client.status()
        print(f"✓ Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except Exception:
        print(f"✗ Could not connect to {client.base_url}. Is the Pico running?")
        return

    # Test sensor availability
    print("\n📡 Checking sensors...")
    try:
        tof = client.get_tof()
        if tof.get('success'):
            left = tof.get('left_distance_cm', 'N/A')
            right = tof.get('right_distance_cm', 'N/A')
            print(f"  ✓ ToF sensors: L={left}cm R={right}cm")
        else:
            print(f"  ✗ ToF sensors: Not available")
    except Exception as e:
        print(f"  ✗ ToF sensors: Error - {e}")
    
    try:
        ultrasonic = client.get_ultrasonic()
        if ultrasonic.get('success'):
            if ultrasonic.get('in_range'):
                dist = ultrasonic.get('distance_cm', 'N/A')
                print(f"  ✓ Ultrasonic (rear): {dist}cm")
            else:
                print(f"  ✓ Ultrasonic (rear): All clear")
        else:
            print(f"  ⚠️  Ultrasonic: Not available")
    except Exception as e:
        print(f"  ⚠️  Ultrasonic: Error - {e}")
    
    try:
        accel = client.get_accelerometer()
        if accel.get('success'):
            orientation = accel.get('orientation', 'unknown')
            print(f"  ✓ Accelerometer: {orientation}")
        else:
            print(f"  ⚠️  Accelerometer: Not available")
    except Exception as e:
        print(f"  ⚠️  Accelerometer: Error - {e}")

    print("\n" + "="*70)
    print("PICAR AUTONOMOUS MODE - ToF + Ultrasonic Navigation")
    print("="*70)
    print("\nControls:")
    print("  G       — Start autonomous mode")
    print("  W       — Forward  (manual)")
    print("  S       — Reverse  (manual)")
    print("  A       — Steer left  (manual)")
    print("  D       — Steer right (manual)")
    print("  C       — Centre servo")
    print("  T       — Read ToF sensors")
    print("  U       — Read ultrasonic sensor")
    print("  1       — Read accelerometer")
    print("  4       — Read all sensors")
    print("  SPACE   — Stop (also exits autonomous mode)")
    print("  Q       — Quit")
    print("="*70)
    print()

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = sys.stdin.read(1).lower()

            if key == "q":
                if driver.autonomous:
                    driver.stop()
                else:
                    client.stop()
                print("\r\n✓ Stopped. Goodbye.\n")
                break

            elif key == " ":
                if driver.autonomous:
                    driver.stop()
                else:
                    client.stop()
                    print("\r🛑 Stopped                      ")

            elif key == "g":
                driver.start()

            elif not driver.autonomous:
                # Manual controls — only active when autonomous mode is off
                if key == "w":
                    r = client.set_motor(DRIVE_SPEED)
                    print(f"\r⬆️  Forward: {r.get('message', '')}")
                elif key == "s":
                    r = client.set_motor(REVERSE_SPEED)
                    print(f"\r⬇️  Reverse: {r.get('message', '')}")
                elif key == "a":
                    r = client.set_servo(STEER_LEFT)
                    print(f"\r⬅️  Left: {r.get('message', '')}")
                elif key == "d":
                    r = client.set_servo(STEER_RIGHT)
                    print(f"\r➡️  Right: {r.get('message', '')}")
                elif key == "c":
                    r = client.centre()
                    print(f"\r↕️  Centre: {r.get('message', '')}")
                elif key == "t":
                    # Read ToF sensors
                    from picar_client import format_tof
                    r = client.get_tof()
                    print(f"\r{format_tof(r)}")
                elif key == "u":
                    # Read ultrasonic sensor
                    from picar_client import format_ultrasonic
                    r = client.get_ultrasonic()
                    print(f"\r{format_ultrasonic(r)}")
                elif key == "1":
                    # Read accelerometer
                    from picar_client import format_accelerometer
                    r = client.get_accelerometer()
                    print(f"\r{format_accelerometer(r)}")
                elif key == "4":
                    # Read all sensors
                    from picar_client import format_tof, format_ultrasonic, format_accelerometer
                    sensors = client.get_all_sensors()
                    print("\r\n" + "="*70)
                    print(format_accelerometer(sensors.get('accelerometer', {})))
                    print(format_tof(sensors.get('tof', {})))
                    print(format_ultrasonic(sensors.get('ultrasonic', {})))
                    print("="*70)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
