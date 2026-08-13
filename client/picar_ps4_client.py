"""
PS4 controller client for Picar — racing-game style controls.

Controls:
    R2 (hold):          Accelerate forward (proportional to pressure)
    L2 (hold):          Reverse (proportional to pressure)
    Left stick X-axis:  Proportional steering
    D-pad Left/Right:   Steer left/right (fixed angles)
    L1/R1:              Decrease/Increase max speed
    Square:             Brake (hard stop)
    X:                  Centre steering
    Triangle:           Toggle gear
    Circle:             Cycle lights (auto -> off -> front -> back -> both)
    PS button:          Quit

Usage:
    python picar_ps4_client.py [--ip IP] [--port PORT] [--speed SPEED]
"""

import sys
import time
import threading
from pathlib import Path

# Import config for default IP
try:
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    import config
    PICAR_IP = config.car_ip
except (ImportError, AttributeError):
    print("Warning: Could not import config.py, using default IP")
    PICAR_IP = "192.168.178.59"

from picar_ws_client import PicarWsClientSync


JOYSTICK_MAX = 32767


class PicarPS4Controller:
    def __init__(self, ip=PICAR_IP, port=5000, base_speed=75,
                 left_angle=45, right_angle=135):
        self.client = PicarWsClientSync(ip, port)
        self.base_speed = base_speed
        self.left_angle = left_angle
        self.right_angle = right_angle
        self.current_speed = 0
        self.current_angle = 90
        # "auto" hands the lights back to the car, which points them the way it
        # is moving. The other entries take manual control until it comes round
        # to "auto" again.
        self.light_state = "auto"
        self._light_cycle = ["auto", "off", "front", "back", "both"]
        self._running = False

    def connect(self):
        print(f"Connecting to Picar...")
        if not self.client.connect():
            time.sleep(3)
            if not self.client.connected:
                print("Could not connect to Picar. Is the Pico running?")
                return False

        try:
            s = self.client.status()
            if s.get('success'):
                gear_str = "LOW" if s.get('gear_on') else "OFF"
                print(f"Connected. Motor: {s['motor_speed']}, "
                      f"Servo: {s['servo_angle']}, Gear: {gear_str}")
        except Exception as e:
            print(f"Connected but status error: {e}")

        return True

    def handle_input(self, action, value=0):
        if action == 'ps_button_press':
            print("\nPS button — quitting")
            self._running = False
            self.client.stop()
            self.client.lights_off()
            return

        # R2 = accelerate forward (proportional to trigger pressure)
        if action == 'R2_press':
            # Trigger range: ~0 to 32767, map to 0..base_speed
            speed = int((abs(value) / JOYSTICK_MAX) * self.base_speed)
            speed = max(10, speed)  # minimum to actually move
            self.client.set_motor(speed)
            self.current_speed = speed

        # L2 = reverse (proportional to trigger pressure)
        elif action == 'L2_press':
            speed = int((abs(value) / JOYSTICK_MAX) * self.base_speed)
            speed = max(10, speed)
            self.client.set_motor(-speed)
            self.current_speed = -speed

        # Left stick X: proportional steering
        elif action == 'L3_left':
            angle = 90 - int((abs(value) / JOYSTICK_MAX) * 90)
            angle = max(0, angle)
            self.client.set_servo(angle)
            self.current_angle = angle
        elif action == 'L3_right':
            angle = 90 + int((abs(value) / JOYSTICK_MAX) * 90)
            angle = min(180, angle)
            self.client.set_servo(angle)
            self.current_angle = angle
        elif action == 'L3_x_rest':
            self.client.set_servo(90)
            self.current_angle = 90

        # D-pad left/right: fixed-angle steering
        elif action == 'on_left_arrow_press':
            self.client.set_servo(self.left_angle)
            self.current_angle = self.left_angle
        elif action == 'on_right_arrow_press':
            self.client.set_servo(self.right_angle)
            self.current_angle = self.right_angle
        elif action == 'dpad_x_release':
            self.client.set_servo(90)
            self.current_angle = 90

        # L1/R1: decrease/increase max speed
        elif action == 'L1_press':
            self._adjust_speed(-5)
        elif action == 'R1_press':
            self._adjust_speed(5)

        # Buttons
        elif action == 'square_press':
            self.client.brake()
            self.current_speed = 0
            print("BRAKE")
        elif action == 'x_press':
            self.client.centre()
            self.current_angle = 90
            print("Centre")
        elif action == 'triangle_press':
            self.client.toggle_gear()
            print("Gear toggled")
        elif action == 'circle_press':
            self._cycle_lights()

        # Release triggers = stop motor (coast)
        elif action in ('R2_release', 'L2_release'):
            self.client.stop()
            self.current_speed = 0

    def _adjust_speed(self, delta):
        self.base_speed = max(0, min(100, self.base_speed + delta))
        print(f"Base speed: {self.base_speed}")

    def _cycle_lights(self):
        idx = self._light_cycle.index(self.light_state)
        self.light_state = self._light_cycle[(idx + 1) % len(self._light_cycle)]
        self.client.set_lights(self.light_state)
        print(f"Lights: {self.light_state}")

    def run(self):
        from ps4_control import MyController

        if not self.connect():
            return

        self._running = True

        print("\n" + "=" * 60)
        print("PICAR PS4 CONTROLLER (Racing Mode)")
        print("=" * 60)
        print(f"\n  R2 (hold):       Accelerate (proportional)")
        print(f"  L2 (hold):       Reverse (proportional)")
        print(f"  Left stick L/R:  Proportional steering")
        print(f"  D-pad L/R:       Fixed-angle steering")
        print(f"  R1/L1:           Speed up/down (max: {self.base_speed})")
        print(f"  Square:          Brake")
        print(f"  X:               Centre steering")
        print(f"  Triangle:        Toggle gear")
        print(f"  Circle:          Cycle lights")
        print(f"  PS button:       Quit")
        print("=" * 60)
        print("\nWaiting for PS4 controller...")

        while self._running:
            try:
                controller = MyController(
                    on_input_change=self.handle_input,
                    interface="/dev/input/js0",
                    connecting_using_ds4drv=False
                )
                print("PS4 controller connected!")
                self.client.send_text("PS4 Ready")
                controller.listen()
            except ConnectionError as e:
                print(f"Controller not found: {e}")
                print("Retrying in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Controller error: {e}")
                time.sleep(3)

        self.client.stop()
        self.client.lights_off()
        self.client.disconnect()
        print("Disconnected. Goodbye.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Picar PS4 controller")
    parser.add_argument("--ip", type=str, default=PICAR_IP,
                        help=f"Pico IP address (default: {PICAR_IP})")
    parser.add_argument("--port", type=int, default=5000,
                        help="Pico port (default: 5000)")
    parser.add_argument("--speed", type=int, default=75,
                        help="Base motor speed (0-100, default 75)")
    parser.add_argument("--left-angle", type=int, default=45,
                        help="Servo angle for left (default 45)")
    parser.add_argument("--right-angle", type=int, default=135,
                        help="Servo angle for right (default 135)")
    args = parser.parse_args()

    ctrl = PicarPS4Controller(
        ip=args.ip,
        port=args.port,
        base_speed=args.speed,
        left_angle=args.left_angle,
        right_angle=args.right_angle,
    )
    ctrl.run()


if __name__ == "__main__":
    main()
