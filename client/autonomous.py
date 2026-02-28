import sys
import tty
import termios
import threading
import time

from picar_client import PicarClient

# ── driving parameters ───────────────────────────────────────────────
DRIVE_SPEED   =  65
REVERSE_SPEED = -65
STEER_LEFT    =  50   # servo angle: left turn
STEER_RIGHT   = 130   # servo angle: right turn
CENTRE        =  90
POLL_INTERVAL =  0.1  # seconds between sensor polls


class AutonomousDriver:
    """Polls IR sensors in a background thread and steers accordingly."""

    def __init__(self, client: PicarClient):
        self.client = client
        self.autonomous = False
        self._thread = None
        self._last_state = None   # (left, right) tuple — skip redundant API calls

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
                left  = sensors.get("left_front",  False)
                right = sensors.get("right_front", False)
                state = (left, right)

                if state != self._last_state:
                    self._react(left, right)
                    self._last_state = state

            except Exception as e:
                print(f"\rSensor error: {e}   ")
                time.sleep(0.5)
                continue

            time.sleep(POLL_INTERVAL)

    def _react(self, left: bool, right: bool):
        """Adjust motor and servo based on the current sensor state."""
        if left and right:
            # Dead end — reverse and swing right to escape
            self.client.set_motor(REVERSE_SPEED)
            self.client.set_servo(STEER_RIGHT)
            print("\rBoth blocked — reversing       ")
            time.sleep(0.7)
            if self.autonomous:
                self.client.centre()
        elif left:
            # Obstacle on left → steer right
            self.client.set_servo(STEER_RIGHT)
            self.client.set_motor(DRIVE_SPEED)
            print("\rLeft blocked — turning right   ")
        elif right:
            # Obstacle on right → steer left
            self.client.set_servo(STEER_LEFT)
            self.client.set_motor(DRIVE_SPEED)
            print("\rRight blocked — turning left   ")
        else:
            # All clear → straight ahead
            self.client.set_servo(CENTRE)
            self.client.set_motor(DRIVE_SPEED)
            print("\rAll clear — going forward      ")


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
                    r = client.get_sensors()
                    l  = "BLOCKED" if r.get("left_front")  else "clear"
                    ri = "BLOCKED" if r.get("right_front") else "clear"
                    print(f"\rIR — left: {l}, right: {ri}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
