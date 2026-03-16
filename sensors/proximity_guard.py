"""
Proximity Guard — Pico-Side Emergency Stop (Zero WiFi Latency)

This module runs entirely on the Pico W, reading ToF + ultrasonic sensor
caches and cutting motor power directly when an obstacle is too close.

Latency comparison:
  Client-side (WiFi):  Sensor → HTTP → WiFi → Client → WiFi → HTTP → Motor  ≈ 200-400 ms
  Pico-side (local):   Sensor cache → Guard check → Motor GPIO               ≈ 1-5 ms

The guard does NOT replace the client-side FSM — it is a safety net that
catches the cases where WiFi latency would cause a collision.

Design:
- Reads from the existing sensor monitor caches (dual_tof, hcsr04)
- Checks distance against a hard-coded emergency threshold
- Cuts motor power via the motor module directly
- Runs as an async task alongside the HTTP server
- Does NOT interfere with normal driving if clearance is OK
- Logs interventions so the client FSM can detect them

Usage in main.py:
    from sensors import proximity_guard
    asyncio.create_task(proximity_guard.monitor())
"""

import time
import uasyncio as asyncio

# These imports are Pico-side modules (not client-side)
import motor
from sensors import dual_tof
from sensors import hcsr04

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Hard emergency stop distance (cm).
# This is the absolute last line of defence — if any front sensor reads
# below this AND the motor is driving forward, cut power immediately.
# Deliberately conservative: vehicle length (34cm) means at 55% speed
# (~50 cm/s) with 1ms reaction time we only travel 0.05 cm.  But
# sensor noise can spike, so we use a sensible 15 cm.
FRONT_EMERGENCY_CM = 15.0

# Rear emergency distance when reversing
REAR_EMERGENCY_CM = 12.0

# How often to check (ms).  50 ms = 20 Hz, matches sensor update rate.
CHECK_INTERVAL_MS = 50

# Cooldown after an intervention (ms).
# Prevents the guard from oscillating if the client immediately
# re-sends a motor command.
INTERVENTION_COOLDOWN_MS = 500


# ═══════════════════════════════════════════════════════════════════
# STATE
# ═══════════════════════════════════════════════════════════════════

_state = {
    "enabled": True,
    "interventions": 0,          # total emergency stops triggered
    "last_intervention_ms": 0,   # ticks_ms of last intervention
    "last_front_cm": None,
    "last_rear_cm": None,
}


# ═══════════════════════════════════════════════════════════════════
# CORE LOGIC
# ═══════════════════════════════════════════════════════════════════

def _cut_motor():
    """Immediately stop the motor via direct GPIO — no HTTP involved."""
    motor.current_motor_speed = 0
    motor.update_motor()


def _check_forward_emergency() -> bool:
    """
    Check if any front sensor reads below the emergency threshold
    while the motor is driving forward.
    
    Returns True if intervention was triggered.
    """
    if motor.current_motor_speed <= 0:
        return False  # not moving forward

    tof = dual_tof.get_state()
    if not tof.get("available"):
        return False

    left = tof.get("left_distance_cm")
    right = tof.get("right_distance_cm")

    # Update tracking
    if left is not None:
        _state["last_front_cm"] = left
    if right is not None and (left is None or right < left):
        _state["last_front_cm"] = right

    # Check both sensors — either one below threshold triggers stop
    front_too_close = False
    if left is not None and left < FRONT_EMERGENCY_CM:
        front_too_close = True
    if right is not None and right < FRONT_EMERGENCY_CM:
        front_too_close = True

    if front_too_close:
        _cut_motor()
        _state["interventions"] += 1
        _state["last_intervention_ms"] = time.ticks_ms()
        dist = min(d for d in [left, right] if d is not None)
        print(f"⛔ PROXIMITY GUARD: front emergency stop! dist={dist:.0f}cm < {FRONT_EMERGENCY_CM}cm")
        return True

    return False


def _check_reverse_emergency() -> bool:
    """
    Check if rear sensor reads below emergency threshold
    while the motor is reversing.
    
    Returns True if intervention was triggered.
    """
    if motor.current_motor_speed >= 0:
        return False  # not reversing

    us = hcsr04.get_state()
    rear = us.get("distance_cm")
    _state["last_rear_cm"] = rear

    if rear is not None and rear < REAR_EMERGENCY_CM:
        _cut_motor()
        _state["interventions"] += 1
        _state["last_intervention_ms"] = time.ticks_ms()
        print(f"⛔ PROXIMITY GUARD: rear emergency stop! dist={rear:.0f}cm < {REAR_EMERGENCY_CM}cm")
        return True

    return False


# ═══════════════════════════════════════════════════════════════════
# ASYNC MONITOR
# ═══════════════════════════════════════════════════════════════════

async def monitor():
    """
    Background task: continuously check proximity and cut motor if needed.
    
    Start this alongside the other sensor monitors in main.py:
        asyncio.create_task(proximity_guard.monitor())
    """
    print("Proximity Guard: starting (local emergency stop, zero WiFi latency)")
    print(f"  Front threshold: {FRONT_EMERGENCY_CM} cm")
    print(f"  Rear threshold:  {REAR_EMERGENCY_CM} cm")
    print(f"  Check rate:      {1000 // CHECK_INTERVAL_MS} Hz")

    while True:
        if _state["enabled"]:
            # Cooldown check
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, _state["last_intervention_ms"])
            if elapsed >= INTERVENTION_COOLDOWN_MS:
                _check_forward_emergency()
                _check_reverse_emergency()

        await asyncio.sleep_ms(CHECK_INTERVAL_MS)


# ═══════════════════════════════════════════════════════════════════
# API (for HTTP status endpoint)
# ═══════════════════════════════════════════════════════════════════

def get_state() -> dict:
    """Get proximity guard state for API access."""
    return dict(_state)


def set_enabled(enabled: bool):
    """Enable/disable the guard (e.g. for calibration)."""
    _state["enabled"] = enabled
    print(f"Proximity Guard: {'enabled' if enabled else 'disabled'}")
