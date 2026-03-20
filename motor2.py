"""
Dual Motor Control (motor2.py)
Drop-in replacement for motor.py that drives BOTH Motor A and Motor B
on a TB6612FNG H-bridge driver.

Motor A (original): AO1/AO2 outputs
  - PWMA = GP10, AIN1 = GP11, AIN2 = GP12

Motor B (additional): BO1/BO2 outputs
  - PWMB = GP28, BIN1 = GP27, BIN2 = GP26

Shared:
  - STBY = GP13  (enables both channels)

To use: in main.py change 'import motor' to 'import motor2 as motor'
"""

import math
import machine
import display

# ========== Motor A control pins (original) ==========
AIN1 = machine.Pin(11, machine.Pin.OUT)
AIN2 = machine.Pin(12, machine.Pin.OUT)
PWMA = machine.PWM(machine.Pin(10))

# ========== Motor B control pins (new) ==========
BIN1 = machine.Pin(27, machine.Pin.OUT)
BIN2 = machine.Pin(26, machine.Pin.OUT)
PWMB = machine.PWM(machine.Pin(28))

# ========== Shared standby pin ==========
STBY = machine.Pin(13, machine.Pin.OUT)

# Set PWM frequency for both channels
PWMA.freq(1000)
PWMB.freq(1000)

current_motor_speed = 0  # signed: + = forward, - = reverse


def update_motor():
    global current_motor_speed

    if -5 < current_motor_speed < 5:
        # Stop both motors
        STBY.low()
        PWMA.duty_u16(0)
        PWMB.duty_u16(0)
        AIN1.low()
        AIN2.low()
        BIN1.low()
        BIN2.low()
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
            # Forward: both motors same direction
            AIN1.high()
            AIN2.low()
            BIN1.high()
            BIN2.low()
        else:
            # Reverse: both motors same direction
            AIN1.low()
            AIN2.high()
            BIN1.low()
            BIN2.high()

        # Apply same PWM to both motors
        PWMA.duty_u16(speed_value)
        PWMB.duty_u16(speed_value)

    display_motor_status()


def display_motor_status():
    direction = "Forward" if current_motor_speed > 0 else "Reverse" if current_motor_speed < 0 else "Stopped"
    speed_text = f"{abs(current_motor_speed)} ({direction})"
    display.update_display(header="Dual Motor", text=speed_text)
    print(f"Dual Motor: {speed_text}")
