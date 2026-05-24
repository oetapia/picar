import machine
import display

servo = machine.PWM(machine.Pin(22))
servo.freq(50)  # 50Hz standard

gear_on = False  # False = off (90°), True = low gear engaged (0°)


def set_servo_angle(angle):
    """Set servo to absolute angle 0-90"""
    pulse_width = 500 + (angle / 180.0) * 2000  # 500 to 2500 us
    duty = int((pulse_width / 20000.0) * 65535)
    servo.duty_u16(duty)


def set_gear(on):
    """Engage low gear (on=True -> 0°) or disengage (on=False -> 90°)"""
    global gear_on
    gear_on = bool(on)
    set_servo_angle(0 if gear_on else 90)


def toggle_gear():
    set_gear(not gear_on)


def display_gear():
    state = "LOW" if gear_on else "OFF"
    display.update_display(header="Gear", text=state)
    print(f"Gear: {state}")
