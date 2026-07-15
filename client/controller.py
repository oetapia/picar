"""
Xbox controller client for Picar — racing-game style controls.

Controls:
    RT (hold):          Accelerate forward (proportional to pressure)
    LT (hold):          Reverse (proportional to pressure)
    Left stick X-axis:  Proportional steering
    D-pad Left/Right:   Steer left/right (fixed angles)
    LB/RB:              Decrease/Increase max speed
    A:                  Brake (hard stop)
    X:                  Centre steering
    Y:                  Toggle gear
    B:                  Cycle lights (off -> front -> back -> both)
    Start:              Quit

Usage:
    python controller.py [--ip IP] [--port PORT] [--speed SPEED]
"""

import sys
import time
from pathlib import Path

import pygame

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


class XboxController:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No controller found")

        self.joy = pygame.joystick.Joystick(0)
        self.joy.init()

    def deadzone(self, value, dz=0.15):
        if abs(value) < dz:
            return 0.0

        if value > 0:
            return (value - dz) / (1 - dz)

        return (value + dz) / (1 - dz)

    def read(self):
        pygame.event.pump()

        return {
            # buttons
            "a": self.joy.get_button(0),
            "b": self.joy.get_button(1),
            "x": self.joy.get_button(2),
            "y": self.joy.get_button(3),

            "lb": self.joy.get_button(4),
            "rb": self.joy.get_button(5),

            "select": self.joy.get_button(6),
            "start": self.joy.get_button(7),
            "home": self.joy.get_button(8),

            # sticks
            "lx": self.deadzone(self.joy.get_axis(0)),
            "ly": -self.deadzone(self.joy.get_axis(1)),

            "rx": self.deadzone(self.joy.get_axis(3)),
            "ry": -self.deadzone(self.joy.get_axis(4)),

            # triggers normalized 0..1
            "lt": (self.joy.get_axis(2) + 1) / 2,
            "rt": (self.joy.get_axis(5) + 1) / 2,

            # dpad
            "dpad": self.joy.get_hat(0),
        }


class PicarXboxController:
    def __init__(self, ip=PICAR_IP, port=5000, base_speed=75,
                 left_angle=45, right_angle=135):
        self.client = PicarWsClientSync(ip, port)
        self.base_speed = base_speed
        self.left_angle = left_angle
        self.right_angle = right_angle
        self.current_speed = 0
        self.current_angle = 90
        self.light_state = "off"
        self._light_cycle = ["off", "front", "back", "both"]
        self._prev = {}

    def connect(self):
        print("Connecting to Picar...")
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

    def _button_pressed(self, state, key):
        return state.get(key) and not self._prev.get(key)

    def _adjust_speed(self, delta):
        self.base_speed = max(0, min(100, self.base_speed + delta))
        print(f"\rBase speed: {self.base_speed}" + " " * 20, end="")

    def _cycle_lights(self):
        idx = self._light_cycle.index(self.light_state)
        self.light_state = self._light_cycle[(idx + 1) % len(self._light_cycle)]
        self.client.set_lights(self.light_state)
        print(f"\rLights: {self.light_state}" + " " * 20, end="")

    def update(self, state):
        # RT = forward, LT = reverse (proportional)
        rt = state["rt"]
        lt = state["lt"]

        if rt > 0.05:
            speed = int(rt * self.base_speed)
            speed = max(10, speed)
            if speed != self.current_speed:
                self.client.set_motor(speed)
                self.current_speed = speed
        elif lt > 0.05:
            speed = int(lt * self.base_speed)
            speed = max(10, speed)
            if -speed != self.current_speed:
                self.client.set_motor(-speed)
                self.current_speed = -speed
        elif self.current_speed != 0:
            self.client.stop()
            self.current_speed = 0

        # Left stick X = proportional steering
        lx = state["lx"]
        if lx != 0:
            angle = 90 + int(lx * 90)
            angle = max(0, min(180, angle))
            if angle != self.current_angle:
                self.client.set_servo(angle)
                self.current_angle = angle
        elif self.current_angle != 90:
            self.client.set_servo(90)
            self.current_angle = 90

        # D-pad left/right: fixed-angle steering
        dpad_x = state["dpad"][0]
        if dpad_x == -1:
            self.client.set_servo(self.left_angle)
            self.current_angle = self.left_angle
        elif dpad_x == 1:
            self.client.set_servo(self.right_angle)
            self.current_angle = self.right_angle

        # Button events (edge-triggered)
        if self._button_pressed(state, "a"):
            self.client.brake()
            self.current_speed = 0
            print("\rBRAKE" + " " * 20, end="")

        if self._button_pressed(state, "x"):
            self.client.centre()
            self.current_angle = 90
            print("\rCentre" + " " * 20, end="")

        if self._button_pressed(state, "y"):
            self.client.toggle_gear()
            print("\rGear toggled" + " " * 20, end="")

        if self._button_pressed(state, "b"):
            self._cycle_lights()

        if self._button_pressed(state, "lb"):
            self._adjust_speed(-5)

        if self._button_pressed(state, "rb"):
            self._adjust_speed(5)

        self._prev = state

    def run(self):
        if not self.connect():
            return

        try:
            controller = XboxController()
        except RuntimeError as e:
            print(f"Controller error: {e}")
            return

        print(f"\nController: {controller.joy.get_name()}")
        self.client.send_text("Xbox Ready")

        print("\n" + "=" * 60)
        print("PICAR XBOX CONTROLLER (Racing Mode)")
        print("=" * 60)
        print(f"\n  RT (hold):       Accelerate (proportional)")
        print(f"  LT (hold):       Reverse (proportional)")
        print(f"  Left stick L/R:  Proportional steering")
        print(f"  D-pad L/R:       Fixed-angle steering")
        print(f"  RB/LB:           Speed up/down (max: {self.base_speed})")
        print(f"  A:               Brake")
        print(f"  X:               Centre steering")
        print(f"  Y:               Toggle gear")
        print(f"  B:               Cycle lights")
        print(f"  Start:           Quit")
        print("=" * 60)

        try:
            while True:
                state = controller.read()

                if state["start"]:
                    break

                self.update(state)
                time.sleep(0.02)

        except KeyboardInterrupt:
            pass

        self.client.stop()
        self.client.lights_off()
        self.client.disconnect()
        pygame.quit()
        print("\nDisconnected. Goodbye.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Picar Xbox controller")
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

    ctrl = PicarXboxController(
        ip=args.ip,
        port=args.port,
        base_speed=args.speed,
        left_angle=args.left_angle,
        right_angle=args.right_angle,
    )
    ctrl.run()


if __name__ == "__main__":
    main()
