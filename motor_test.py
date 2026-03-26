"""
motor_test.py — DRV8871 PWM profile tester

Cycles through multiple PWM profiles at several speed inputs.
Run directly on the Pico (no server needed).  Observe the car
at each step and report back which profile felt best.

Hardware: DRV8871 on GP17 (IN1) / GP16 (IN2), 7.4 V 2S LiPo, 370 motor.

Usage:  Upload to Pico and run.  The OLED display + serial console
        show which profile and speed are active.
"""

import math
import time
import machine

# ── Try to use the OLED display; fall back to print-only ──
try:
    import display
    HAS_DISPLAY = True
except Exception:
    HAS_DISPLAY = False

def show(header, text):
    print(f"[{header}] {text}")
    if HAS_DISPLAY:
        try:
            display.update_display(header=header, text=text)
        except Exception:
            pass

# ── DRV8871 pins ──
IN1 = machine.PWM(machine.Pin(17))
IN2 = machine.PWM(machine.Pin(16))

def set_freq(freq):
    IN1.freq(freq)
    IN2.freq(freq)

def coast():
    IN1.duty_u16(0)
    IN2.duty_u16(0)

def brake():
    IN1.duty_u16(65535)
    IN2.duty_u16(65535)

def drive_forward(duty):
    IN1.duty_u16(duty)
    IN2.duty_u16(0)

# ── Profiles ──
# Each profile: (name, freq, min_duty, max_duty, curve)
# curve: "sqrt" or "linear"
PROFILES = [
    ("A: 20kHz baseline",  20000, 20000, 55000, "sqrt"),
    ("B: 5kHz same duty",   5000, 20000, 55000, "sqrt"),
    ("C: 5kHz full range",  5000, 28000, 65535, "sqrt"),
    ("D: 1kHz TB6612 match", 1000, 25000, 60000, "sqrt"),
    ("E: 5kHz linear",      5000, 25000, 65535, "linear"),
]

# Speed inputs to test (percent, 0-100 scale same as API)
SPEED_INPUTS = [30, 50, 75, 100]

# Timing
RUN_SECONDS   = 3   # how long each speed runs
COAST_SECONDS = 2   # pause between speeds
PAUSE_SECONDS = 5   # pause between profiles


def compute_duty(speed_input, min_duty, max_duty, curve):
    """Convert a 0-100 speed input to a duty_u16 value."""
    if speed_input < 5:
        return 0
    normalized = (speed_input - 5) / 95.0
    if curve == "sqrt":
        normalized = math.sqrt(normalized) if normalized > 0 else 0
    # "linear" leaves normalized as-is
    return int(min_duty + normalized * (max_duty - min_duty))


def run_test():
    show("Motor Test", "Starting in 3s...")
    time.sleep(3)

    for p_idx, (name, freq, min_d, max_d, curve) in enumerate(PROFILES):
        profile_label = f"[{p_idx+1}/{len(PROFILES)}]"

        show(f"Profile {profile_label}", name)
        print(f"\n{'='*50}")
        print(f"PROFILE {profile_label}: {name}")
        print(f"  freq={freq} Hz  min_duty={min_d}  max_duty={max_d}  curve={curve}")
        print(f"{'='*50}")
        time.sleep(2)

        set_freq(freq)

        for speed in SPEED_INPUTS:
            duty = compute_duty(speed, min_d, max_d, curve)
            pct = duty * 100 / 65535

            show(f"{name[:18]}", f"{speed}% → duty {duty} ({pct:.0f}%)")
            print(f"  Speed {speed:3d}%  →  duty_u16 = {duty:5d}  ({pct:.1f}% of full)")

            drive_forward(duty)
            time.sleep(RUN_SECONDS)

            # Coast between speeds
            coast()
            time.sleep(COAST_SECONDS)

        # Brake at end of profile
        brake()
        time.sleep(0.3)
        coast()

        if p_idx < len(PROFILES) - 1:
            show("Pause", f"Next profile in {PAUSE_SECONDS}s")
            print(f"\n  ⏸  Pause {PAUSE_SECONDS}s before next profile...\n")
            time.sleep(PAUSE_SECONDS)

    # Done
    coast()
    show("Motor Test", "DONE!")
    print("\n✅  All profiles complete.  Report back what you observed!")


if __name__ == "__main__":
    try:
        run_test()
    except KeyboardInterrupt:
        coast()
        show("Motor Test", "Cancelled")
        print("\n⛔  Test cancelled — motor stopped.")
