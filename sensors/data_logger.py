"""
Sensor Data Logger — Logging Profile for Modeling

Records timestamped snapshots of all sensor + actuator state at a
configurable interval. Designed for later offline modeling of:
  - Speed calibration (motor % → actual cm/s)
  - Braking / deceleration curves
  - Steering response (servo angle → yaw rate)
  - Terrain compensation (incline vs speed loss)

Architecture:
  - Samples are stored as compact lists in RAM while recording
  - On stop(), the buffer is flushed to /log_profile.json on flash
  - download_and_erase() streams the file back and deletes it locally

Memory budget (Pico W — 264 KB RAM):
  - Each sample = 14 numbers × ~8 bytes ≈ 112 bytes as list
  - 1000 samples ≈ 112 KB — safe with headroom for the rest of the app
  - Default max: 1000 samples at 10 Hz = 100 seconds of recording
"""

import time
import json
import uasyncio as asyncio

# ── Field order (compact list, not dict, to save RAM) ────────────
FIELDS = [
    "ts",        # 0  relative ms from recording start
    "ax",        # 1  accelerometer x (g)
    "ay",        # 2  accelerometer y (g)
    "az",        # 3  accelerometer z (g)
    "gx",        # 4  gyroscope x (°/s)
    "gy",        # 5  gyroscope y (°/s)
    "gz",        # 6  gyroscope z (°/s)
    "pitch",     # 7  tilt pitch (°)
    "roll",      # 8  tilt roll (°)
    "tof_l",     # 9  ToF left distance (cm)
    "tof_r",     # 10 ToF right distance (cm)
    "us_rear",   # 11 ultrasonic rear distance (cm)
    "motor",     # 12 motor speed (signed %)
    "servo",     # 13 servo angle (0-180)
]

LOG_FILE = "/log_profile.json"

# ── Defaults ─────────────────────────────────────────────────────
DEFAULT_INTERVAL_MS = 100   # 10 Hz
DEFAULT_MAX_SAMPLES = 1000  # ~100 s at 10 Hz
MAX_ALLOWED_SAMPLES = 3000  # hard ceiling (RAM safety)


# ═════════════════════════════════════════════════════════════════
# MODULE STATE
# ═════════════════════════════════════════════════════════════════

_recording = False
_buffer = []           # list of lists (compact samples)
_start_time = 0        # time.ticks_ms() at recording start
_start_epoch = 0       # time.time() at recording start (for metadata)
_interval_ms = DEFAULT_INTERVAL_MS
_max_samples = DEFAULT_MAX_SAMPLES
_file_ready = False    # True when a log file is available for download


# ═════════════════════════════════════════════════════════════════
# PUBLIC API
# ═════════════════════════════════════════════════════════════════

def start(interval_ms=None, max_samples=None):
    """
    Begin recording sensor data.

    Args:
        interval_ms: Sampling interval in milliseconds (default 100 → 10 Hz)
        max_samples: Maximum samples before auto-stop (default 1000)

    Returns:
        dict with status info
    """
    global _recording, _buffer, _start_time, _start_epoch
    global _interval_ms, _max_samples, _file_ready

    if _recording:
        return {"success": False, "message": "Already recording"}

    _interval_ms = max(50, interval_ms or DEFAULT_INTERVAL_MS)
    _max_samples = min(MAX_ALLOWED_SAMPLES, max(10, max_samples or DEFAULT_MAX_SAMPLES))

    _buffer = []
    _start_time = time.ticks_ms()
    _start_epoch = time.time()
    _recording = True
    _file_ready = False

    print(f"DataLogger: recording started (interval={_interval_ms}ms, max={_max_samples})")
    return {
        "success": True,
        "message": "Recording started",
        "interval_ms": _interval_ms,
        "max_samples": _max_samples,
    }


def stop():
    """
    Stop recording and flush buffer to flash.

    Returns:
        dict with status info
    """
    global _recording, _file_ready

    if not _recording:
        return {"success": False, "message": "Not recording"}

    _recording = False
    count = len(_buffer)
    duration_s = time.ticks_diff(time.ticks_ms(), _start_time) / 1000.0

    # Flush to file
    _flush_to_file()
    _file_ready = True

    print(f"DataLogger: stopped — {count} samples, {duration_s:.1f}s → {LOG_FILE}")
    return {
        "success": True,
        "message": f"Stopped. {count} samples saved.",
        "sample_count": count,
        "duration_s": round(duration_s, 1),
        "file": LOG_FILE,
    }


def get_status():
    """Get current logger status."""
    count = len(_buffer)
    if _recording:
        elapsed_ms = time.ticks_diff(time.ticks_ms(), _start_time)
        return {
            "recording": True,
            "sample_count": count,
            "max_samples": _max_samples,
            "elapsed_s": round(elapsed_ms / 1000.0, 1),
            "interval_ms": _interval_ms,
            "file_ready": False,
        }
    else:
        return {
            "recording": False,
            "sample_count": count,
            "file_ready": _file_ready,
        }


def download_and_erase():
    """
    Read the log file, delete it, and return the contents.

    Returns:
        dict with the full log data, or error
    """
    global _file_ready

    if _recording:
        return {"success": False, "message": "Stop recording first"}

    if not _file_ready:
        return {"success": False, "message": "No log file available"}

    try:
        import os
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
        os.remove(LOG_FILE)
        _file_ready = False
        print(f"DataLogger: log downloaded and erased from flash")
        data["success"] = True
        return data
    except OSError:
        _file_ready = False
        return {"success": False, "message": "Log file not found"}


def clear():
    """Erase the stored log file without downloading."""
    global _file_ready, _buffer

    if _recording:
        return {"success": False, "message": "Stop recording first"}

    try:
        import os
        os.remove(LOG_FILE)
    except OSError:
        pass

    _buffer = []
    _file_ready = False
    print("DataLogger: log cleared")
    return {"success": True, "message": "Log cleared"}


# ═════════════════════════════════════════════════════════════════
# BACKGROUND SAMPLER (async task)
# ═════════════════════════════════════════════════════════════════

async def monitor():
    """
    Background coroutine — samples sensors while recording.

    Must be started as an asyncio task in main.py alongside the
    other sensor monitors.  When not recording, it idles cheaply.
    """
    # Lazy-import sensor modules (they're already running their own monitors)
    from sensors import accelerometer, dual_tof, hcsr04
    import motor
    import servo

    print("DataLogger monitor started (idle until recording)")

    while True:
        if not _recording:
            await asyncio.sleep_ms(200)  # idle — check periodically
            continue

        # ── Collect one sample ───────────────────────────────────
        ts = time.ticks_diff(time.ticks_ms(), _start_time)

        # Accelerometer / gyro / tilt
        acc = accelerometer.get_state()
        if acc["available"]:
            ax = acc["acceleration"]["x"]
            ay = acc["acceleration"]["y"]
            az = acc["acceleration"]["z"]
            gx = acc["gyroscope"]["x"]
            gy = acc["gyroscope"]["y"]
            gz = acc["gyroscope"]["z"]
            pitch = acc["tilt"]["pitch"]
            roll = acc["tilt"]["roll"]
        else:
            ax = ay = az = gx = gy = gz = pitch = roll = None

        # ToF distances
        tof = dual_tof.get_state()
        if tof["available"]:
            tof_l = tof["left_distance_cm"]
            tof_r = tof["right_distance_cm"]
        else:
            tof_l = tof_r = None

        # Ultrasonic rear
        us = hcsr04.get_state()
        if us["available"]:
            us_rear = us["distance_cm"]
        else:
            us_rear = None

        # Motor & servo (direct module state — no API call)
        motor_pct = motor.current_motor_speed
        servo_angle = servo.current_angle + 90  # internal → 0-180

        sample = [
            ts, ax, ay, az, gx, gy, gz,
            pitch, roll, tof_l, tof_r, us_rear,
            motor_pct, servo_angle,
        ]
        _buffer.append(sample)

        # Auto-stop if max reached
        if len(_buffer) >= _max_samples:
            print(f"DataLogger: max samples ({_max_samples}) reached — auto-stopping")
            stop()
            continue

        await asyncio.sleep_ms(_interval_ms)


# ═════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═════════════════════════════════════════════════════════════════

def _flush_to_file():
    """Write the buffer to flash as a compact JSON log profile."""
    duration_ms = time.ticks_diff(time.ticks_ms(), _start_time)

    profile = {
        "profile": "picar_sensor_log",
        "version": 1,
        "start_time": _start_epoch,
        "interval_ms": _interval_ms,
        "duration_s": round(duration_ms / 1000.0, 1),
        "sample_count": len(_buffer),
        "fields": FIELDS,
        "samples": _buffer,
    }

    with open(LOG_FILE, "w") as f:
        json.dump(profile, f)
