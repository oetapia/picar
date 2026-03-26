"""
motor_test2.py — DRV8871 PWM profile tester (Round 2)

Refined profiles based on Round 1 findings:
  - 20 kHz is silent + high torque but needs higher min_duty to start
  - 1 kHz moves easily but loses torque
  - 5 kHz is noisy and still struggles at low speed

Round 2 strategy: keep 20 kHz (silent, great torque) but raise the
duty floor so the motor overcomes static friction at 30%.  Also test
10–15 kHz as potential sweet spots for more top speed.

Hardware: DRV8871 on GP17 (IN1) / GP16 (IN2), 7.4 V 2S LiPo, 370 motor.
"""

import math
import time
import machine

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

# ── Round 2 Profiles ──
# (name, freq, min_duty, max_duty, curve)
PROFILES = [
    ("F: 20kHz high floor",  20000, 40000, 65535, "sqrt"),
    ("G: 20kHz higher floor", 20000, 45000, 65535, "sqrt"),
    ("H: 15kHz mid-range",   15000, 35000, 65535, "sqrt"),
    ("I: 10kHz mid-range",   10000, 30000, 65535, "sqrt"),
]

# Speed inputs (same as Round 1 for comparison)
SPEED_INPUTS = [30, 50, 75, 100]

# Timing
RUN_SECONDS   = 3
COAST_SECONDS = 2
PAUSE_SECONDS = 5


def compute_duty(speed_input, min_duty, max_duty, curve):
    if speed_input < 5:
        return 0
    normalized = (speed_input - 5) / 95.0
    if curve == "sqrt":
        normalized = math.sqrt(normalized) if normalized > 0 else 0
    return int(min_duty + normalized * (max_duty - min_duty))


def run_test():
    show("Motor Test 2", "Starting in 3s...")
    print("\n" + "=" * 55)
    print("  ROUND 2 — Refined DRV8871 profiles")
    print("=" * 55)
    time.sleep(3)

    for p_idx, (name, freq, min_d, max_d, curve) in enumerate(PROFILES):
        label = f"[{p_idx+1}/{len(PROFILES)}]"

        show(f"Profile {label}", name)
        print(f"\n{'='*55}")
        print(f"PROFILE {label}: {name}")
        print(f"  freq={freq} Hz  min_duty={min_d}  max_duty={max_d}  curve={curve}")

        # Show duty values up front so you know what to expect
        for s in SPEED_INPUTS:
            d = compute_duty(s, min_d, max_d, curve)
            print(f"    {s:3d}% → duty {d:5d} ({d*100/65535:.0f}%)")
        print(f"{'='*55}")
        time.sleep(2)

        set_freq(freq)

        for speed in SPEED_INPUTS:
            duty = compute_duty(speed, min_d, max_d, curve)
            pct = duty * 100 / 65535

            show(f"{name[:18]}", f"{speed}% → duty {duty} ({pct:.0f}%)")
            print(f"  ▶ Speed {speed:3d}%  →  duty_u16 = {duty:5d}  ({pct:.1f}%)")

            drive_forward(duty)
            time.sleep(RUN_SECONDS)

            coast()
            time.sleep(COAST_SECONDS)

        brake()
        time.sleep(0.3)
        coast()

        if p_idx < len(PROFILES) - 1:
            show("Pause", f"Next in {PAUSE_SECONDS}s")
            print(f"\n  ⏸  Pause {PAUSE_SECONDS}s ...\n")
            time.sleep(PAUSE_SECONDS)

    coast()
    show("Motor Test 2", "DONE!")
    print("\n✅  Round 2 complete!  Report back what you observed.")


if __name__ == "__main__":
    try:
        run_test()
    except KeyboardInterrupt:
        coast()
        show("Motor Test 2", "Cancelled")
        print("\n⛔  Test cancelled — motor stopped.")
