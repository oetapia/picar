"""
Dual Motor Control (motor2.py) — N20 Geared Motors
Drop-in replacement for motor.py that drives BOTH Motor A and Motor B
on a TB6612FNG H-bridge driver, with per-motor speed control and bias trim.

Motor A: AO1/AO2 outputs
  - PWMA = GP10, AIN1 = GP11, AIN2 = GP12

Motor B: BO1/BO2 outputs
  - PWMB = GP28, BIN1 = GP27, BIN2 = GP26

Shared:
  - STBY = GP13  (enables both channels)

Profile tuned for N20 geared DC motors:
  - 500 Hz PWM (less gearbox whine)
  - 30% min duty (gearing provides startup torque)
  - 100% max duty (gearbox already limits RPM)

API:
  Backward-compatible:
    current_motor_speed   — signed speed for both motors (legacy)
    update_motor()        — apply current_motor_speed to both

  Decoupled:
    set_motor_speeds(a, b)  — individual motor speeds (-100..100)
    set_trim(a_bias, b_bias) — persistent per-motor bias (-20..20)
    get_motor_state()        — full state dict for API

To use: in main.py change 'import motor' to 'import motor2 as motor'
"""

import math
import machine
import display

# ========== Motor A control pins ==========
AIN1 = machine.Pin(11, machine.Pin.OUT)
AIN2 = machine.Pin(12, machine.Pin.OUT)
PWMA = machine.PWM(machine.Pin(10))

# ========== Motor B control pins ==========
BIN1 = machine.Pin(27, machine.Pin.OUT)
BIN2 = machine.Pin(26, machine.Pin.OUT)
PWMB = machine.PWM(machine.Pin(28))

# ========== Shared standby pin ==========
STBY = machine.Pin(13, machine.Pin.OUT)

# ========== N20 Motor Profile ==========
PWM_FREQ = 500       # Hz — lower freq reduces gearbox whine
MIN_DUTY = 20000     # ~30% — N20 gearing provides enough startup torque
MAX_DUTY = 65535     # 100% — gearbox limits RPM, use full range
DEAD_ZONE = 5        # speed values below ±5 → stop

PWMA.freq(PWM_FREQ)
PWMB.freq(PWM_FREQ)

# ========== Motor State ==========
current_motor_speed = 0      # signed: + = forward, - = reverse (legacy, both motors)
current_motor_a_speed = 0    # Motor A individual speed (-100..100)
current_motor_b_speed = 0    # Motor B individual speed (-100..100)
motor_a_bias = 0             # persistent trim for Motor A (-20..20)
motor_b_bias = 0             # persistent trim for Motor B (-20..20)
_decoupled_mode = False      # True when using individual motor speeds


def _speed_to_duty(speed_input):
    """Convert absolute speed (0-100) to PWM duty using sqrt curve.
    
    The sqrt curve gives finer control at low speeds where N20
    geared motors are most useful.
    """
    if speed_input < DEAD_ZONE:
        return 0
    normalized_linear = (speed_input - DEAD_ZONE) / (100 - DEAD_ZONE)
    normalized_smooth = math.sqrt(normalized_linear) if normalized_linear > 0 else 0
    return int(MIN_DUTY + normalized_smooth * (MAX_DUTY - MIN_DUTY))


def _apply_single_motor(in1, in2, pwm, speed):
    """Drive one motor channel at the given signed speed."""
    abs_speed = abs(speed)
    duty = _speed_to_duty(abs_speed)

    if duty == 0:
        in1.low()
        in2.low()
        pwm.duty_u16(0)
    else:
        if speed > 0:
            in1.high()
            in2.low()
        else:
            in1.low()
            in2.high()
        pwm.duty_u16(duty)


def update_motor():
    """Apply current_motor_speed to BOTH motors (backward-compatible).
    
    Adds per-motor bias on top of the shared speed. This is the function
    called by main.py, proximity_guard.py, etc.
    """
    global current_motor_a_speed, current_motor_b_speed, _decoupled_mode
    _decoupled_mode = False

    # Compute per-motor speed with bias
    a_speed = max(-100, min(100, current_motor_speed + motor_a_bias))
    b_speed = max(-100, min(100, current_motor_speed + motor_b_bias))

    current_motor_a_speed = a_speed
    current_motor_b_speed = b_speed

    _apply_motors(a_speed, b_speed)
    display_motor_status()


def set_motor_speeds(a=None, b=None):
    """Set individual motor speeds (-100..100) for differential control.
    
    Args:
        a: Motor A speed (None = unchanged)
        b: Motor B speed (None = unchanged)
    """
    global current_motor_a_speed, current_motor_b_speed
    global current_motor_speed, _decoupled_mode
    _decoupled_mode = True

    if a is not None:
        current_motor_a_speed = max(-100, min(100, a + motor_a_bias))
    if b is not None:
        current_motor_b_speed = max(-100, min(100, b + motor_b_bias))

    # Update legacy speed as average (for status/proximity_guard compat)
    current_motor_speed = (current_motor_a_speed + current_motor_b_speed) // 2

    _apply_motors(current_motor_a_speed, current_motor_b_speed)
    display_motor_status()


def set_trim(a_bias=None, b_bias=None):
    """Set persistent per-motor bias to compensate for motor mismatch.
    
    Args:
        a_bias: Motor A trim offset (-20..20), None = unchanged
        b_bias: Motor B trim offset (-20..20), None = unchanged
    """
    global motor_a_bias, motor_b_bias
    if a_bias is not None:
        motor_a_bias = max(-20, min(20, a_bias))
    if b_bias is not None:
        motor_b_bias = max(-20, min(20, b_bias))


def _apply_motors(a_speed, b_speed):
    """Low-level: drive both motor channels."""
    # If both motors are effectively stopped, disable standby
    if -DEAD_ZONE < a_speed < DEAD_ZONE and -DEAD_ZONE < b_speed < DEAD_ZONE:
        STBY.low()
        PWMA.duty_u16(0)
        PWMB.duty_u16(0)
        AIN1.low()
        AIN2.low()
        BIN1.low()
        BIN2.low()
    else:
        STBY.high()
        _apply_single_motor(AIN1, AIN2, PWMA, a_speed)
        _apply_single_motor(BIN1, BIN2, PWMB, b_speed)


def get_motor_state():
    """Return full motor state dict for API responses."""
    return {
        'motor_a_speed': current_motor_a_speed,
        'motor_b_speed': current_motor_b_speed,
        'motor_speed': current_motor_speed,
        'motor_a_bias': motor_a_bias,
        'motor_b_bias': motor_b_bias,
        'decoupled': _decoupled_mode,
        'profile': {
            'type': 'N20 geared',
            'pwm_freq': PWM_FREQ,
            'min_duty_pct': round(MIN_DUTY / 65535 * 100),
            'max_duty_pct': round(MAX_DUTY / 65535 * 100),
        }
    }


def display_motor_status():
    if _decoupled_mode:
        text = f"A:{current_motor_a_speed} B:{current_motor_b_speed}"
        header = "Dual Motor"
    else:
        direction = "Forward" if current_motor_speed > 0 else "Reverse" if current_motor_speed < 0 else "Stopped"
        text = f"{abs(current_motor_speed)} ({direction})"
        header = "Dual Motor"
    display.update_display(header=header, text=text)
    print(f"Dual Motor: A={current_motor_a_speed} B={current_motor_b_speed}")
