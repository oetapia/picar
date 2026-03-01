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
POLL_INTERVAL      =  0.1  # seconds between sensor polls
CORRECTION_HOLD    =  0.5  # seconds to hold a steering correction
REVERSE_TIMEOUT    =  0.8  # max seconds to reverse before re-evaluating


class AutonomousDriver:
    """
    Uses all four corner IR sensors to navigate.

    Sensor combinations → inferred situation → reaction
    ────────────────────────────────────────────────────
    all clear              → full speed ahead, centred
    lf only                → gentle right nudge  (obstacle front-left)
    rf only                → gentle left nudge   (obstacle front-right)
    lf + lb (left wall)    → steer hard right    (wall along the left side)
    rf + rb (right wall)   → steer hard left     (wall along the right side)
    lf + rf (front wall)   → guided reverse      (steer based on which back side is clearer)
    lf + rf + any back     → stop               (no safe escape route)
    """

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread = None
        self._last_state = None

    # ── public controls ──────────────────────────────────────────────

    def start(self):
        if self.autonomous:
            return
        self.autonomous = True
        self._last_state = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("\rAutonomous ON                    ")

    def stop(self):
        self.autonomous = False
        self.client.stop()
        self.client.centre()
        print("\rAutonomous OFF                   ")

    # ── sensor loop (background thread) ─────────────────────────────

    def _loop(self):
        while self.autonomous:
            try:
                sensors = self.client.get_sensors()
                lf = sensors.get("left_front",  False)
                rf = sensors.get("right_front", False)
                lb = sensors.get("left_back",   False)
                rb = sensors.get("right_back",  False)
                state = (lf, rf, lb, rb)

                if state != self._last_state:
                    self._last_state = state
                    did_maneuver = self._react(lf, rf, lb, rb)
                    # Force re-evaluation after a timed maneuver — the world
                    # has changed and we need fresh sensors regardless of
                    # whether the state tuple matches the pre-maneuver reading.
                    if did_maneuver:
                        self._last_state = None

            except Exception as e:
                print(f"\rSensor error: {e}   ")
                time.sleep(0.5)
                continue

            time.sleep(POLL_INTERVAL)

    # ── decision logic ───────────────────────────────────────────────

    def _react(self, lf: bool, rf: bool, lb: bool, rb: bool) -> bool:
        """
        React to the current sensor snapshot.
        Returns True if a timed maneuver was performed (caller resets state).
        """
        both_front = lf and rf
        left_wall  = lf and lb   # obstacle on both left corners → wall
        right_wall = rf and rb   # obstacle on both right corners → wall

        if both_front and (lb or rb):
            # Front blocked, no safe reverse direction
            self.client.set_motor(0)
            self.client.centre()
            print("\rTrapped — stopping             ")
            return False

        if both_front:
            # Front wall — reverse with live steering guidance
            self._reverse_guided(lb, rb)
            return True

        if left_wall:
            # Wall running along the left side — steer hard away
            self.client.set_motor(CORRECTION_SPEED)
            self.client.set_servo(STEER_RIGHT)
            print("\rLeft wall — hard right         ")
            time.sleep(CORRECTION_HOLD)
            return True

        if right_wall:
            # Wall running along the right side — steer hard away
            self.client.set_motor(CORRECTION_SPEED)
            self.client.set_servo(STEER_LEFT)
            print("\rRight wall — hard left         ")
            time.sleep(CORRECTION_HOLD)
            return True

        if lf:
            # Single front-left obstacle — gentle nudge right
            self.client.set_motor(CORRECTION_SPEED)
            self.client.set_servo(STEER_SLIGHT_RIGHT)
            print("\rFront-left — nudging right     ")
            time.sleep(CORRECTION_HOLD)
            return True

        if rf:
            # Single front-right obstacle — gentle nudge left
            self.client.set_motor(CORRECTION_SPEED)
            self.client.set_servo(STEER_SLIGHT_LEFT)
            print("\rFront-right — nudging left     ")
            time.sleep(CORRECTION_HOLD)
            return True

        # All clear — full speed ahead
        self.client.set_servo(CENTRE)
        self.client.set_motor(DRIVE_SPEED)
        print("\rAll clear — forward            ")
        return False

    def _reverse_guided(self, lb: bool, rb: bool):
        """
        Reverse while actively steering the nose away from the front obstacle.

        Steering logic: reversing left swings the nose right (and vice versa),
        so we steer toward whichever back corner is clearer to maximise escape
        angle. Back sensors are polled live to abort if we hit something behind.
        """
        if lb and not rb:
            # Back-left blocked → steer right while reversing (nose swings left, away from left obstacle)
            steer = STEER_RIGHT
        elif rb and not lb:
            # Back-right blocked → steer left while reversing (nose swings right, away from right obstacle)
            steer = STEER_LEFT
        else:
            # Both clear or both blocked — default: swing nose right
            steer = STEER_RIGHT

        self.client.set_motor(REVERSE_SPEED)
        self.client.set_servo(steer)
        print("\rFront wall — reversing         ")

        deadline = time.time() + REVERSE_TIMEOUT
        while self.autonomous and time.time() < deadline:
            time.sleep(0.1)
            try:
                s = self.client.get_sensors()
                lb_now = s.get("left_back",  False)
                rb_now = s.get("right_back", False)
                if lb_now or rb_now:
                    # Something appeared behind us — stop immediately
                    print("\rBack sensor hit — aborting     ")
                    break
            except Exception:
                break

        if self.autonomous:
            self.client.set_motor(0)
            self.client.centre()


def main():
    client = PicarClient()
    driver = AutonomousDriver(client)

    print(f"Connecting to Picar at {client.base_url}...")
    try:
        s = client.status()
        print(f"Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except Exception:
        print(f"Could not connect to {client.base_url}. Is the Pico running?")
        return

    print("\nControls:")
    print("  g     — Start autonomous mode")
    print("  w     — Forward  (manual)")
    print("  s     — Reverse  (manual)")
    print("  a     — Steer left  (manual)")
    print("  d     — Steer right (manual)")
    print("  c     — Centre servo")
    print("  i     — Read IR sensors")
    print("  SPACE — Stop (also exits autonomous mode)")
    print("  q     — Quit")
    print()

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = sys.stdin.read(1)

            if key == "q":
                if driver.autonomous:
                    driver.stop()
                else:
                    client.stop()
                print("\r\nStopped. Goodbye.")
                break

            elif key == " ":
                if driver.autonomous:
                    driver.stop()
                else:
                    client.stop()
                    print("\rStopped                        ")

            elif key == "g":
                driver.start()

            elif not driver.autonomous:
                # Manual controls — only active when autonomous mode is off
                if key == "w":
                    r = client.set_motor(DRIVE_SPEED)
                    print(f"\rForward: {r.get('message', '')}")
                elif key == "s":
                    r = client.set_motor(REVERSE_SPEED)
                    print(f"\rReverse: {r.get('message', '')}")
                elif key == "a":
                    r = client.set_servo(STEER_LEFT)
                    print(f"\rLeft: {r.get('message', '')}")
                elif key == "d":
                    r = client.set_servo(STEER_RIGHT)
                    print(f"\rRight: {r.get('message', '')}")
                elif key == "c":
                    r = client.centre()
                    print(f"\rCentre: {r.get('message', '')}")
                elif key == "i":
                    r  = client.get_sensors()
                    lf = "BLOCKED" if r.get("left_front")  else "clear"
                    rf = "BLOCKED" if r.get("right_front") else "clear"
                    lb = "BLOCKED" if r.get("left_back")   else "clear"
                    rb = "BLOCKED" if r.get("right_back")  else "clear"
                    print(f"\rIR — front L:{lf} R:{rf}  back L:{lb} R:{rb}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
