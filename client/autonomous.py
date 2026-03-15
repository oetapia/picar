import sys
import tty
import termios
import threading
import time

from picar_client import PicarClient

# ── driving parameters (physics-based) ───────────────────────────────
# Speed settings - progressive control based on clearance
CRUISE_SPEED       =  45   # full speed when clear (>80cm) - ~50 cm/s
MEDIUM_SPEED       =  30   # moderate speed for caution zone (50-80cm)
SLOW_SPEED         =  20   # slow speed for warning zone (30-50cm)
CRAWL_SPEED        =  15   # very slow for tight navigation (<30cm)
REVERSE_FAST       = -40   # fast reverse when rear clear (>50cm)
REVERSE_SLOW       = -25   # slow reverse in caution zone (30-50cm)

# Steering angles
STEER_LEFT         =  50   # hard left
STEER_SLIGHT_LEFT  =  75   # gentle left nudge
STEER_RIGHT        = 130   # hard right
STEER_SLIGHT_RIGHT = 105   # gentle right nudge
CENTRE             =  90

# Timing - faster response for better reaction
POLL_INTERVAL      =  0.08 # seconds between sensor polls (~4cm at cruise)
MIN_MANEUVER_TIME  =  0.3  # minimum time to hold a direction change

# ── distance thresholds (cm) - physics-based stopping distances ──────
# Front distance zones (accounting for 250-350ms reaction time)
VERY_SAFE_DIST     = 80    # full cruise speed safe
SAFE_DIST          = 50    # medium speed zone
CAUTION_DIST       = 30    # slow speed zone
DANGER_DIST        = 25    # prepare to change direction
CRITICAL_DIST      = 20    # must change direction immediately

# Rear distance zones
REAR_SAFE_DIST     = 50    # safe to reverse at speed
REAR_CAUTION_DIST  = 30    # slow reverse only
REAR_DANGER_DIST   = 20    # cannot reverse safely

# Clearance scoring weights
MIN_SAFE_SCORE     = 40    # minimum clearance to move in any direction


class AutonomousDriver:
    """
    Bidirectional autonomous navigation using physics-based collision avoidance.

    Sensors:
    ────────────────────────────────────────────────────
    - Dual VL53L0X ToF (front left & right): distance measurements in cm
    - HC-SR04 Ultrasonic (rear): distance measurement in cm
    - Continuous 360° awareness for optimal path selection

    Navigation Strategy:
    ────────────────────────────────────────────────────
    1. Every loop: evaluate clearance in BOTH directions
    2. Choose direction with best clearance score
    3. Progressive speed control based on obstacle distance
    4. No blocking operations - continuous sensor monitoring
    5. Instant direction changes when needed
    
    Distance Zones (based on reaction time physics):
    ────────────────────────────────────────────────────
    > 80cm: VERY SAFE    → cruise speed (45%)
    50-80cm: SAFE        → medium speed (30%)
    30-50cm: CAUTION     → slow speed (20%)
    25-30cm: DANGER      → crawl/evaluate direction
    < 25cm: CRITICAL     → change direction immediately
    
    Reaction time: ~250-350ms (sensor + network + motor)
    At cruise speed: car travels ~17cm during reaction
    Therefore: detect at 25cm to stop at ~8cm minimum
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread = None
        self._last_action_time = 0
        self._current_direction = "stopped"  # "forward", "backward", "stopped"

    # ── public controls ──────────────────────────────────────────────

    def start(self):
        if self.autonomous:
            return
        self.autonomous = True
        self._last_action_time = time.time()
        self._current_direction = "stopped"
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("\r🚗 Autonomous ON - Bidirectional Navigation")
        print("\r   Physics-based collision avoidance active")

    def stop(self):
        self.autonomous = False
        self.client.stop()
        self.client.centre()
        self._current_direction = "stopped"
        print("\r🛑 Autonomous OFF - Vehicle stopped")

    # ── sensor loop (background thread) ─────────────────────────────

    def _loop(self):
        while self.autonomous:
            try:
                # Get all sensor readings
                tof = self.client.get_tof()
                ultrasonic = self.client.get_ultrasonic()
                
                # Validate ToF sensors
                if not tof.get('success'):
                    print("\r⚠️  ToF sensors unavailable - stopping")
                    self.client.stop()
                    time.sleep(0.5)
                    continue
                
                # Extract front distances
                left_dist = tof.get('left_distance_cm')
                right_dist = tof.get('right_distance_cm')
                
                # Handle None values (sensor failures)
                if left_dist is None:
                    left_dist = 999
                if right_dist is None:
                    right_dist = 999
                
                # Extract rear distance
                rear_dist = 999  # Default: assume clear
                if ultrasonic.get('success') and ultrasonic.get('in_range'):
                    rear_dist = ultrasonic.get('distance_cm', 999)
                
                # Make navigation decision (no blocking operations)
                self._navigate(left_dist, right_dist, rear_dist)

            except Exception as e:
                print(f"\r⚠️  Sensor error: {e}          ")
                self.client.stop()
                time.sleep(0.5)
                continue

            time.sleep(POLL_INTERVAL)

    # ── bidirectional navigation logic ──────────────────────────────

    def _navigate(self, left_dist: float, right_dist: float, rear_dist: float):
        """
        Bidirectional navigation with continuous path evaluation.
        Choose direction with best clearance, no blocking operations.
        
        Args:
            left_dist: Front left ToF distance (cm)
            right_dist: Front right ToF distance (cm)
            rear_dist: Rear ultrasonic distance (cm)
        """
        # Calculate clearance scores
        front_clearance = min(left_dist, right_dist)  # Worst case matters
        rear_clearance = rear_dist
        
        # CRITICAL: Too close on all sides - TRAPPED
        if front_clearance < CRITICAL_DIST and rear_clearance < REAR_DANGER_DIST:
            if self._current_direction != "stopped":
                self.client.stop()
                self.client.centre()
                self._current_direction = "stopped"
                print(f"\r🚨 TRAPPED! F:{front_clearance:.0f}cm R:{rear_clearance:.0f}cm")
            return
        
        # DECISION: Choose best direction based on clearance
        
        # Option 1: Front is very clear - prefer forward movement
        if front_clearance > VERY_SAFE_DIST:
            self._move_forward(left_dist, right_dist, CRUISE_SPEED, "CRUISE")
        
        # Option 2: Front is safe/caution - continue forward with appropriate speed
        elif front_clearance > CAUTION_DIST:
            if front_clearance > SAFE_DIST:
                self._move_forward(left_dist, right_dist, MEDIUM_SPEED, "MEDIUM")
            else:
                self._move_forward(left_dist, right_dist, SLOW_SPEED, "SLOW")
        
        # Option 3: Front danger zone - can we reverse instead?
        elif front_clearance < DANGER_DIST and rear_clearance > REAR_SAFE_DIST:
            # Rear is much clearer - reverse away
            self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_FAST)
        
        # Option 4: Front in danger, rear somewhat clear - slow reverse
        elif front_clearance < DANGER_DIST and rear_clearance > REAR_CAUTION_DIST:
            self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_SLOW)
        
        # Option 5: Front tight but navigable - crawl forward with steering
        elif front_clearance >= CRITICAL_DIST:
            self._move_forward(left_dist, right_dist, CRAWL_SPEED, "CRAWL")
        
        # Option 6: Everything tight - try gentle reverse if possible
        elif rear_clearance > REAR_DANGER_DIST:
            self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_SLOW)
        
        # Option 7: No good options - stop
        else:
            if self._current_direction != "stopped":
                self.client.stop()
                self.client.centre()
                self._current_direction = "stopped"
                print(f"\r⚠️ No safe path: F:{front_clearance:.0f}cm R:{rear_clearance:.0f}cm")

    def _move_forward(self, left_dist: float, right_dist: float, speed: int, mode: str):
        """Move forward with intelligent steering based on side clearances."""
        # Determine steering based on which side has more clearance
        clearance_diff = abs(left_dist - right_dist)
        
        if clearance_diff > 15:  # Significant difference
            if left_dist < right_dist:
                # Left side tighter - steer right
                if clearance_diff > 30:
                    servo = STEER_RIGHT
                    steer_label = "→→"
                else:
                    servo = STEER_SLIGHT_RIGHT
                    steer_label = "→"
            else:
                # Right side tighter - steer left
                if clearance_diff > 30:
                    servo = STEER_LEFT
                    steer_label = "←←"
                else:
                    servo = STEER_SLIGHT_LEFT
                    steer_label = "←"
        else:
            # Both sides similar - go straight
            servo = CENTRE
            steer_label = "↑"
        
        self.client.set_servo(servo)
        self.client.set_motor(speed)
        self._current_direction = "forward"
        
        min_dist = min(left_dist, right_dist)
        print(f"\r🟢 {mode} {steer_label} L:{left_dist:.0f} R:{right_dist:.0f} [{speed}%]", end="")

    def _move_backward(self, left_dist: float, right_dist: float, rear_dist: float, speed: int):
        """Move backward with steering away from front obstacles."""
        # Steer to open up escape angle for next forward movement
        if abs(left_dist - right_dist) > 10:
            if left_dist < right_dist:
                # Left blocked more - steer right (nose goes left when reversing)
                servo = STEER_RIGHT
                steer_label = "⤴"
            else:
                # Right blocked more - steer left (nose goes right when reversing)
                servo = STEER_LEFT
                steer_label = "⤵"
        else:
            # Center steering for straight reverse
            servo = CENTRE
            steer_label = "↓"
        
        self.client.set_servo(servo)
        self.client.set_motor(speed)
        self._current_direction = "backward"
        
        print(f"\r🔵 REVERSE {steer_label} Rear:{rear_dist:.0f}cm [{speed}%]", end="")



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
