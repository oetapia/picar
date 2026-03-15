import math
import machine
import display

# Motor control pins
AIN1 = machine.Pin(11, machine.Pin.OUT)
AIN2 = machine.Pin(12, machine.Pin.OUT)
PWMA = machine.PWM(machine.Pin(10))
STBY = machine.Pin(13, machine.Pin.OUT)

PWMA.freq(1000)

current_motor_speed = 0  # signed: + = forward, - = reverse


def update_motor():
    global current_motor_speed

    if -5 < current_motor_speed < 5:
        STBY.low()
        PWMA.duty_u16(0)
        AIN1.low()
        AIN2.low()
    else:
        STBY.high()

        min_duty = 25000
        max_duty = 60000

        direction = 1 if current_motor_speed > 0 else -1
        speed_input = abs(current_motor_speed)

        normalized_linear = (speed_input - 5) / 95
        normalized_smooth = math.sqrt(normalized_linear) if normalized_linear > 0 else 0
        speed_value = int(min_duty + normalized_smooth * (max_duty - min_duty))

        if direction > 0:
            AIN1.high()
            AIN2.low()
        else:
            AIN1.low()
            AIN2.high()

        PWMA.duty_u16(speed_value)

    display_motor_status()


def display_motor_status():
    direction = "Forward" if current_motor_speed > 0 else "Reverse" if current_motor_speed < 0 else "Stopped"
    speed_text = f"{abs(current_motor_speed)} ({direction})"
    display.update_display(header="Motor Status", text=speed_text)
    print(f"Motor: {speed_text}")
