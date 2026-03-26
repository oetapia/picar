"""
DRV8871 Motor Control (motor3.py)
Drop-in replacement for motor.py using a DRV8871 H-bridge driver
instead of the TB6612FNG.

DRV8871 specs:
  - Motor supply: 6.5V to 45V
  - Output current: 3.6A continuous
  - 2-pin PWM interface (no separate PWM + direction pins, no standby)

Control logic:
  Forward:  IN1 = PWM,  IN2 = LOW   → motor drives forward
  Reverse:  IN1 = LOW,  IN2 = PWM   → motor drives reverse
  Coast:    IN1 = LOW,  IN2 = LOW   → motor coasts to stop
  Brake:    IN1 = HIGH, IN2 = HIGH  → active braking

Hardware:
  - Battery: 7.4V 2S LiPo (6.5–8.4V range)
  - Motor: 370 type (~6–7.2V rated)
  - IN1 = GP17 (PWM)
  - IN2 = GP16 (PWM)

To use: in main.py change 'import motor' to 'import motor3 as motor'
"""

import math
import machine
import display

# DRV8871 control pins (both are PWM-capable)
IN1 = machine.PWM(machine.Pin(17))
IN2 = machine.PWM(machine.Pin(16))

# 20 kHz PWM — above audible range, well within DRV8871's 200 kHz max
IN1.freq(20000)
IN2.freq(20000)

current_motor_speed = 0  # signed: + = forward, - = reverse


def update_motor():
    global current_motor_speed

    if -5 < current_motor_speed < 5:
        # Coast stop: both pins LOW
        IN1.duty_u16(0)
        IN2.duty_u16(0)
    else:
        # Duty cycle range tuned for 370 motor on 7.4 V
        # min_duty keeps the motor from stalling at low speed inputs
        # max_duty kept under full to avoid over-driving the 370
        min_duty = 20000
        max_duty = 55000

        direction = 1 if current_motor_speed > 0 else -1
        speed_input = abs(current_motor_speed)

        # sqrt curve for smooth low-speed ramp-up
        normalized_linear = (speed_input - 5) / 95
        normalized_smooth = math.sqrt(normalized_linear) if normalized_linear > 0 else 0
        speed_value = int(min_duty + normalized_smooth * (max_duty - min_duty))

        if direction > 0:
            # Forward: PWM on IN1, IN2 held LOW
            IN1.duty_u16(speed_value)
            IN2.duty_u16(0)
        else:
            # Reverse: IN1 held LOW, PWM on IN2
            IN1.duty_u16(0)
            IN2.duty_u16(speed_value)

    display_motor_status()


def brake():
    """Active brake — shorts motor windings through the H-bridge."""
    IN1.duty_u16(65535)
    IN2.duty_u16(65535)


def display_motor_status():
    direction = "Forward" if current_motor_speed > 0 else "Reverse" if current_motor_speed < 0 else "Stopped"
    speed_text = f"{abs(current_motor_speed)} ({direction})"
    display.update_display(header="Motor DRV8871", text=speed_text)
    print(f"Motor: {speed_text}")
