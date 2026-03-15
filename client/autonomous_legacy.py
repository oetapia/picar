import sys
import tty
import termios
import threading
import time

from picar_client import PicarClient

# ── driving parameters (ANTI-LAG TUNED) ──────────────────────────────
# CRITICAL: Reduced speeds to account for network/motor lag
CRUISE_SPEED       =  35   # conservative cruise (was 45) - ~40 cm/s
MEDIUM_SPEED       =  25   # moderate speed (was 30)
SLOW_SPEED         =  18   # slow speed (was 20)
CRAWL_SPEED        =  12   # very slow (was 15)
REVERSE_FAST       = -35   # fast reverse (was -40)
REVERSE_SLOW       = -22   # slow reverse (was -25)

# Steering angles - INCREASED for sharper turns (compensate for understeer)
STEER_LEFT         =  35   # hard left (was 50 - sharper turn)
STEER_SLIGHT_LEFT  =  65   # gentle left nudge (was 75)
STEER_RIGHT        = 145   # hard right (was 130 - sharper turn)
STEER_SLIGHT_RIGHT = 115   # gentle right nudge (was 105)
CENTRE             =  90

# Timing - AGGRESSIVE POLLING to minimize lag
POLL_INTERVAL      =  0.05 # FASTER: check every 2cm at cruise (was 0.08)

# ── distance thresholds (cm) - ANTI-LAG: LARGER MARGINS ──────────────
# CRITICAL: Increased thresholds to account for 250-400ms total lag
# At 40cm/s cruise: car travels 16cm during reaction delay!
# SAME EMERGENCY THRESHOLD FOR BOTH DIRECTIONS
EMERGENCY_STOP_DIST = 50   # 🚨 IMMEDIATE STOP - front OR rear, no questions asked
VERY_SAFE_DIST      = 90   # full cruise speed safe (was 80)
SAFE_DIST           = 60   # medium speed zone (was 50)
CAUTION_DIST        = 45   # slow speed zone (was 30) 
DANGER_DIST         = 35   # crawl speed (was 25)
CRITICAL_DIST       = 25   # must change direction NOW (was 20)

# Rear distance zones - MATCHED to front for consistency
REAR_SAFE_DIST      = 60   # safe to reverse at speed (was 55, match SAFE_DIST)
REAR_CAUTION_DIST   = 45   # slow reverse only (was 35, match CAUTION_DIST)
REAR_DANGER_DIST    = 35   # cannot reverse safely (was 25, match DANGER_DIST)

# Velocity tracking for predictive collision detection
APPROACH_RATE_THRESHOLD = 15  # cm/s - if closing faster than this, pre-brake


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
    
    ANTI-LAG Distance Zones (SAME for front AND rear):
    ────────────────────────────────────────────────────
    < 50cm: EMERGENCY    → immediate stop (both directions)
    > 90cm: VERY SAFE    → cruise speed forward (35%)
    > 60cm: REAR_SAFE    → fast reverse OK (-35%)
    60-90cm: SAFE        → medium forward (25%)
    45-60cm: CAUTION     → slow forward/reverse (18%/-22%)
    35-45cm: DANGER      → crawl speed (12%)
    < 35cm: CRITICAL     → must change direction
    
    Lag Analysis (Total: 250-400ms):
    - Sensor read: 20-50ms
    - Network HTTP: 50-150ms (WiFi/processing)
    - Motor response: 100-150ms (physical inertia)
    - At 40cm/s: travels 10-16cm during lag
    - Emergency threshold at 50cm provides 25-30cm safety margin
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread = None
        self._last_action_time = 0
        self._current_direction = "stopped"  # "forward", "backward", "stopped"
        self._last_front_dist = None
        self._last_measurement_time = None
        self._emergency_stop_active = False
        self._display_update_counter = 0  # Throttle display updates

    # ── public controls ──────────────────────────────────────────────

    def start(self):
        if self.autonomous:
            return
        self.autonomous = True
        self._last_action_time = time.time()
        self._current_direction = "stopped"
        self._display_update_counter = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        # Display startup message
        try:
            self.client.send_text("AUTO MODE\nStarting...")
        except:
            pass
        
        print("\r🚗 Autonomous ON - Bidirectional Navigation")
        print("\r   Physics-based collision avoidance active")

    def stop(self):
        self.autonomous = False
        self.client.stop()
        self.client.centre()
        self._current_direction = "stopped"
        
        # Clear display
        try:
            self.client.send_text("AUTO MODE\nStopped")
        except:
            pass
        
        print("\r🛑 Autonomous OFF - Vehicle stopped")

    # ── sensor loop (background thread) ─────────────────────────────

    def _loop(self):
        while self.autonomous:
            loop_start = time.time()
            
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
                
                # Calculate approach velocity for predictive collision detection
                current_time = time.time()
                front_clearance = min(left_dist, right_dist)
                approach_rate = 0
                
                if self._last_front_dist is not None and self._last_measurement_time is not None:
                    time_delta = current_time - self._last_measurement_time
                    if time_delta > 0:
                        # Negative rate = approaching obstacle
                        approach_rate = (front_clearance - self._last_front_dist) / time_delta
                
                self._last_front_dist = front_clearance
                self._last_measurement_time = current_time
                
                # 🚨 EMERGENCY STOP LOGIC - HIGHEST PRIORITY FOR BOTH DIRECTIONS
                
                # Forward emergency stop
                if self._current_direction == "forward" and front_clearance < EMERGENCY_STOP_DIST:
                    if not self._emergency_stop_active:
                        print(f"\r🚨 EMERGENCY STOP! Front:{front_clearance:.0f}cm - TOO CLOSE!")
                        self.client.stop()  # IMMEDIATE STOP
                        self._emergency_stop_active = True
                        self._current_direction = "stopped"
                        time.sleep(0.1)  # Brief pause to ensure stop command processed
                        continue
                
                # Reverse emergency stop - SAME LOGIC FOR REAR
                if self._current_direction == "backward" and rear_dist < EMERGENCY_STOP_DIST:
                    if not self._emergency_stop_active:
                        print(f"\r🚨 EMERGENCY STOP REVERSE! Rear:{rear_dist:.0f}cm - TOO CLOSE!")
                        self.client.stop()  # IMMEDIATE STOP
                        self._emergency_stop_active = True
                        self._current_direction = "stopped"
                        time.sleep(0.1)  # Brief pause to ensure stop command processed
                        continue
                
                # Predictive braking: if approaching too fast, pre-brake
                if self._current_direction == "forward" and approach_rate < -APPROACH_RATE_THRESHOLD:
                    print(f"\r⚡ PRE-BRAKE! Approaching at {-approach_rate:.0f}cm/s")
                    self.client.set_motor(CRAWL_SPEED)  # Immediate slow down
                    time.sleep(0.05)
                
                # Reset emergency flag if both directions cleared
                if front_clearance > EMERGENCY_STOP_DIST + 10 and rear_dist > EMERGENCY_STOP_DIST + 10:
                    self._emergency_stop_active = False
                
                # Update OLED display every 4 loops (~0.2s) to avoid lag
                self._display_update_counter += 1
                if self._display_update_counter >= 4:
                    self._display_update_counter = 0
                    self._update_display(left_dist, right_dist, rear_dist, front_clearance)
                
                # Make navigation decision (no blocking operations)
                self._navigate(left_dist, right_dist, rear_dist, approach_rate)

            except Exception as e:
                print(f"\r⚠️  Sensor error: {e}          ")
                self.client.stop()
                self._emergency_stop_active = False
                time.sleep(0.5)
                continue

            # Maintain consistent polling rate
            loop_duration = time.time() - loop_start
            sleep_time = max(0, POLL_INTERVAL - loop_duration)
            time.sleep(sleep_time)

    # ── bidirectional navigation logic ──────────────────────────────

    def _navigate(self, left_dist: float, right_dist: float, rear_dist: float, approach_rate: float):
        """
        Bidirectional navigation with ANTI-LAG measures and predictive collision detection.
        
        Args:
            left_dist: Front left ToF distance (cm)
            right_dist: Front right ToF distance (cm)
            rear_dist: Rear ultrasonic distance (cm)
            approach_rate: Rate of distance change (cm/s, negative = approaching)
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
        
        # If emergency stop was triggered, must clear to much safer distance before resuming
        if self._emergency_stop_active:
            # Check which direction triggered it and recover appropriately
            # Use EMERGENCY_STOP_DIST threshold for recovery (not SAFE_DIST) to avoid getting stuck
            if front_clearance < EMERGENCY_STOP_DIST + 5 and rear_clearance > REAR_CAUTION_DIST:
                # Front still too close - must reverse
                self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_SLOW)
                return
            elif rear_clearance < EMERGENCY_STOP_DIST + 5 and front_clearance > EMERGENCY_STOP_DIST + 5:
                # Rear still too close - must move forward
                self._move_forward(left_dist, right_dist, CRAWL_SPEED, "RECOVER")
                return
            elif front_clearance < EMERGENCY_STOP_DIST + 5 and rear_clearance < EMERGENCY_STOP_DIST + 5:
                # Both still dangerously close - stay stopped
                return
            # If we reach here, emergency cleared and normal navigation resumes
        
        # DECISION: Choose best direction based on clearance
        # Note: Thresholds are now LARGER to account for lag
        
        # Option 1: Front is very clear - prefer forward movement
        if front_clearance > VERY_SAFE_DIST:
            self._move_forward(left_dist, right_dist, CRUISE_SPEED, "CRUISE")
        
        # Option 2: Front is safe - medium speed
        elif front_clearance > SAFE_DIST:
            self._move_forward(left_dist, right_dist, MEDIUM_SPEED, "MEDIUM")
        
        # Option 3: Front is caution zone - slow down
        elif front_clearance > CAUTION_DIST:
            self._move_forward(left_dist, right_dist, SLOW_SPEED, "SLOW")
        
        # Option 4: Front in danger zone - crawl forward (prefer forward!)
        elif front_clearance > DANGER_DIST:
            # Only reverse if approaching VERY fast
            if approach_rate < -20 and rear_clearance > REAR_CAUTION_DIST:
                self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_SLOW)
            else:
                # Default: crawl forward in danger zone
                self._move_forward(left_dist, right_dist, CRAWL_SPEED, "CRAWL")
        
        # Option 5: Front critical (25-35cm) - still try crawl if approaching slowly
        elif front_clearance >= CRITICAL_DIST:
            # If approaching fast or very close, reverse
            if approach_rate < -15 or front_clearance < 30:
                if rear_clearance > REAR_CAUTION_DIST:
                    self._move_backward(left_dist, right_dist, rear_clearance, REVERSE_SLOW)
                else:
                    # Can't reverse, try very slow crawl
                    self._move_forward(left_dist, right_dist, CRAWL_SPEED, "CRAWL")
            else:
                # Approaching slowly, can still crawl
                self._move_forward(left_dist, right_dist, CRAWL_SPEED, "CRAWL")
        
        # Option 6: Front very critical (<25cm) - must reverse if possible
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
        """Move forward with intelligent steering - ANTI-LAG: reduced speeds."""
        # Skip if emergency stop active
        if self._emergency_stop_active:
            return
        
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
        
        # Only send commands if direction/speed changed
        if self._current_direction != "forward":
            self.client.set_servo(servo)
            self.client.set_motor(speed)
            self._current_direction = "forward"
        else:
            # Just update servo if needed (faster than motor command)
            self.client.set_servo(servo)
        
        min_dist = min(left_dist, right_dist)
        print(f"\r🟢 {mode} {steer_label} L:{left_dist:.0f} R:{right_dist:.0f} [{speed}%]", end="")

    def _move_backward(self, left_dist: float, right_dist: float, rear_dist: float, speed: int):
        """Move backward with steering away from front obstacles - ANTI-LAG: safety checks."""
        # CRITICAL: Don't reverse if rear is too close (emergency zone)
        if rear_dist < EMERGENCY_STOP_DIST:
            # Too close to reverse - emergency stop should have caught this
            if self._current_direction == "backward":
                self.client.stop()
                self._current_direction = "stopped"
                print(f"\r🚨 ABORT REVERSE! Rear:{rear_dist:.0f}cm", end="")
            return
        
        # Reduce speed if rear is getting close
        if rear_dist < REAR_CAUTION_DIST:
            speed = min(speed, -18)  # Cap at slow reverse speed
        
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

    def _update_display(self, left_dist: float, right_dist: float, rear_dist: float, front_clearance: float):
        """Update OLED display with sensor distances - non-blocking."""
        try:
            # Format distances for display
            left_str = f"{left_dist:.0f}" if left_dist < 200 else "---"
            right_str = f"{right_dist:.0f}" if right_dist < 200 else "---"
            rear_str = f"{rear_dist:.0f}" if rear_dist < 200 else "---"
            
            # Determine status emoji/symbol
            if self._emergency_stop_active:
                status = "STOP!"
            elif front_clearance > VERY_SAFE_DIST:
                status = "CRUISE"
            elif front_clearance > SAFE_DIST:
                status = "MEDIUM"
            elif front_clearance > CAUTION_DIST:
                status = "SLOW"
            elif front_clearance > DANGER_DIST:
                status = "CRAWL"
            else:
                status = "DANGER"
            
            # Build display text (4 lines max for typical OLED)
            display_text = f"AUTO: {status}\n"
            display_text += f"F: L{left_str} R{right_str}\n"
            display_text += f"Rear: {rear_str}cm\n"
            
            # Add direction indicator
            if self._current_direction == "forward":
                display_text += "Dir: FWD"
            elif self._current_direction == "backward":
                display_text += "Dir: REV"
            else:
                display_text += "Dir: ---"
            
            # Send to display (non-blocking, don't wait for response)
            self.client.send_text(display_text)
        except:
            # Silently fail - don't let display errors affect navigation
            pass


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
