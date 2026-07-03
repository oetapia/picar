import subprocess
import time
from pyPS4Controller.controller import Controller


def is_bluetooth_device_connected():
    time.sleep(1)
    result = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error checking devices: {result.stderr}")
        return False
    return any("Wireless Controller" in line for line in result.stdout.split('\n'))


def request_bluetooth_pairing():
    print("No Bluetooth device detected. Please connect your PS4 controller.")


class MyController(Controller):
    def __init__(self, interface, connecting_using_ds4drv, on_input_change=None):
        if is_bluetooth_device_connected():
            print("Bluetooth device connected.")
        else:
            request_bluetooth_pairing()
            raise ConnectionError("No Bluetooth device connected. Please pair your PS4 controller.")

        super().__init__(interface=interface, connecting_using_ds4drv=connecting_using_ds4drv)
        self.on_input_change = on_input_change
        self.deadzone = 20000

    def on_R3_x_at_rest(self):
        if callable(self.on_input_change):
            self.on_input_change('R3_rest')

    def on_L3_y_at_rest(self):
        if callable(self.on_input_change):
            self.on_input_change('L3_rest')

    def on_up_arrow_press(self):
        if callable(self.on_input_change):
            self.on_input_change('on_up_arrow_press')

    def on_up_arrow_release(self):
        pass

    def on_down_arrow_press(self):
        if callable(self.on_input_change):
            self.on_input_change('on_down_arrow_press')

    def on_up_down_arrow_release(self):
        if callable(self.on_input_change):
            self.on_input_change('dpad_y_release')

    def on_left_arrow_press(self):
        if callable(self.on_input_change):
            self.on_input_change('on_left_arrow_press')

    def on_right_arrow_press(self):
        if callable(self.on_input_change):
            self.on_input_change('on_right_arrow_press')

    def on_left_right_arrow_release(self):
        if callable(self.on_input_change):
            self.on_input_change('dpad_x_release')

    def on_x_press(self):
        if callable(self.on_input_change):
            self.on_input_change('x_press')

    def on_x_release(self):
        pass

    def on_circle_press(self):
        if callable(self.on_input_change):
            self.on_input_change('circle_press')

    def on_circle_release(self):
        pass

    def on_triangle_press(self):
        if callable(self.on_input_change):
            self.on_input_change('triangle_press')

    def on_triangle_release(self):
        pass

    def on_square_press(self):
        if callable(self.on_input_change):
            self.on_input_change('square_press')

    def on_square_release(self):
        pass

    def on_playstation_button_press(self):
        if callable(self.on_input_change):
            self.on_input_change('ps_button_press')

    def on_playstation_button_release(self):
        pass

    def on_L1_press(self):
        if callable(self.on_input_change):
            self.on_input_change('L1_press')

    def on_R1_press(self):
        if callable(self.on_input_change):
            self.on_input_change('R1_press')

    def on_L2_press(self, value):
        if callable(self.on_input_change):
            self.on_input_change('L2_press', value)

    def on_L2_release(self):
        if callable(self.on_input_change):
            self.on_input_change('L2_release')

    def on_R2_press(self, value):
        if callable(self.on_input_change):
            self.on_input_change('R2_press', value)

    def on_R2_release(self):
        if callable(self.on_input_change):
            self.on_input_change('R2_release')

    def on_L3_press(self):
        if callable(self.on_input_change):
            self.on_input_change('L3_press')

    def on_R3_press(self):
        if callable(self.on_input_change):
            self.on_input_change('R3_press')

    def on_L3_x_at_rest(self):
        if callable(self.on_input_change):
            self.on_input_change('L3_x_rest')

    def on_R3_y_at_rest(self):
        if callable(self.on_input_change):
            self.on_input_change('R3_y_rest')

    def on_L3_left(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('L3_left', value)

    def on_L3_right(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('L3_right', value)

    def on_L3_up(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('L3_up', value)

    def on_L3_down(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('L3_down', value)

    def on_R3_left(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('R3_left', value)

    def on_R3_right(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('R3_right', value)

    def on_R3_up(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('R3_up', value)

    def on_R3_down(self, value):
        if abs(value) > self.deadzone:
            if callable(self.on_input_change):
                self.on_input_change('R3_down', value)


if __name__ == "__main__":
    controller = MyController(interface="/dev/input/js0", connecting_using_ds4drv=False)
    controller.listen()
