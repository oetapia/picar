import machine
import display

servo = machine.PWM(machine.Pin(22))
servo.freq(50)  # 50Hz standard

current_angle = 0  # -90 (left) to +90 (right), 0 = center


def set_servo_angle(angle):
    """Set servo to absolute angle 0-180"""
    pulse_width = 500 + (angle / 180.0) * 2000  # 500 to 2500 us
    duty = int((pulse_width / 20000.0) * 65535)
    servo.duty_u16(duty)


def set_direction(angle=None, percent=None):
    """Set steering direction using angle (-90 to 90) or percent (-100 to 100)"""
    global current_angle
    if percent is not None:
        angle = (max(-100, min(100, percent)) / 100) * 90
    elif angle is not None:
        angle = max(-90, min(90, angle))
    else:
        angle = 0
    current_angle = angle
    set_servo_angle(90 + angle)  # Map -90:90 -> 0:180


def display_servo():
    display.update_display(header="Servo Position", text=f'{current_angle:.0f}°')
    print(f"Servo angle: {current_angle:.0f}°")
