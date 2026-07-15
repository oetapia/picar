import pygame


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
