# main_raw.py Optimization

Notes from the pass over `main_raw.py` that removed the per-command work from the
hot path. Covers what was flooding, what changed, the behaviour that changed with
it, and what is still outstanding.

Status: applied, **not yet tested on the car**. The changes touch the actuator
path, so a drive-test is wanted before this is trusted.

---

## What was actually flooding

The 5 Hz OLED debouncer in `main_raw.py` was being bypassed. `motor3.update_motor()`
called `display_motor_status()`, which does a full 128x32 I2C redraw *plus* a
serial `print()`, synchronously. So every `{"c":"m"}` blocked the command path on
~20 ms of I2C no matter what the debouncer did.

On top of that, the display was treated as a log: every command called `_show()`
with its own text, so driving meant a redraw every 200 ms forever, and status or
sensor polls counted as activity too.

The lights were the client's job — it watched the speed it had just sent and
followed up with a separate `{"c":"l"}` command, so every direction change cost a
second message and a second reply.

---

## Changes

| Issue | Fix |
| --- | --- |
| `motor3` redrew the OLED + printed on every speed change | new `motor3.show_status` flag; `main_raw` sets it `False` and owns the display. Default stays `True`, so `main.py` / `main_ws.py` are unaffected |
| `_show()` per command → constant 5 Hz redraws while driving | replaced with a 3-state display machine; a redraw happens only on a real state change |
| auto-lights were a second client→car command per direction change | moved into the motor path on the Pico (`_apply_lights`) |
| watchdog used `time.time()`, whole seconds on this port, against a `1.0` s threshold | `time.ticks_ms()` / `ticks_diff()`. The failsafe could previously fire right after a live frame, or up to 2 s late |
| `st` / `sns` / `imu` / `pg` polls counted as activity and held the display awake | only commands that move the car call `_touch_control()` |
| `{"c":"m"}` and `{"c":"s"}` rewrote the actuator even when the value was unchanged | deduped, as `ctl` already was |
| `{"c":"t"}` wrote the OLED straight from the command path | routed through the display task |
| 2 s `sleep` in the disconnect `finally` block | dropped |

Files: `main_raw.py`, `motor3.py`, `client/picar_ws_client.py`,
`client/controller.py`, `client/picar_ps4_client.py`.

---

## Display

Three states plus a text override, named by the command path and drawn by
`_display_loop` at 5 Hz — and only when the state actually changed, so streaming
control frames cost nothing here regardless of rate.

| State | Shows | When |
| --- | --- | --- |
| `DISP_IP` | `Picar` / `<ip>:5000` | no client attached |
| `DISP_IDLE` | `Picar` / `Connected - idle` | client attached, and after 5 s without a control command |
| `DISP_MANUAL` | `Picar` / `Manual control` | remote is driving |
| `DISP_TEXT` | `Picar` / whatever `{"c":"t"}` sent | explicit override; survives until the next control command |

The idle watcher only demotes from `DISP_MANUAL`, so a text the client asked for
is not wiped a second later.

---

## Lights

Forward lights the front, reverse the back, stop turns both off — applied on the
car, in `_apply_lights`, off the back of every motor write. No client involvement.

`{"c":"l","v":"front|back|both|off"}` is still there for driving them by hand, but
using it parks automatic mode so the next motor command cannot stomp the choice.
`{"c":"l","v":"auto"}` hands control back. Automatic mode is restored on every new
client connection, so a manual override cannot outlive the client that set it, and
`_safe_stop` kills the lights unconditionally so a disconnect cannot leave them
burning.

Protocol additions:

- `{"c":"l","v":"auto"}` — return to automatic
- `st` gained `"la":0|1` — whether the lights are in automatic mode

Client side: the duplicate command is gone from `set_motor()`, `lights_auto()` was
added, the terminal `T` key is now "lights auto" instead of a local toggle, and
both controllers' `B`/`Circle` cycle is `auto → off → front → back → both`.

---

## Outstanding

### 1. The controllers still do not use `ctl`

This is the biggest remaining source of traffic. `client/controller.py` polls
pygame at 50 Hz and calls `set_motor()` / `set_servo()`, each of which blocks on an
ack — so proportional-trigger driving can produce ~50 request/reply pairs per
second across two separate commands.

The firmware's `ctl` frame (throttle and steering in one message, `"q":1` to
suppress the reply, watchdog-protected) exists and has **no users**. Migrating the
controllers to a 20 Hz `ctl` push would cut this to ~20 messages/s and zero acks.
Not done here: it changes the client's timing model and the failsafe semantics, so
it wants its own pass and its own test.

### 2. The proximity guard is inert

`sensors/proximity_guard.py:31` does `import motor` — plain `motor.py`, the TB6612
driver. `main_raw` does `import motor3 as motor`, and that alias exists only in
`main_raw`'s namespace, so the guard holds a *different module object*:

- `motor.current_motor_speed` in the guard is always 0, so `_check_forward_emergency`
  returns at line 89 (`<= 0`) and `_check_reverse_emergency` at line 130 (`>= 0`).
  **The emergency stop can never fire.** Dead since the switch to the DRV8871.
- If it did fire, `_cut_motor()` would drive GP10-13 (TB6612), not the DRV8871 on
  GP16/17.
- Importing `motor.py` also claims GP10/11/12/13 as outputs at import time, for a
  driver that is not connected.

`main_ws.py` has the same combination. `sensors/data_logger.py:216` imports plain
`motor` too, so the `motor_pct` column in every recorded sample is always 0 (its
`servo` import is fine — there is only one servo module).

Suggested fix, one naming point instead of five:

```python
# drivetrain.py — the one place that names the driver in use
import motor3 as motor
```

then `from drivetrain import motor` in `proximity_guard`, `data_logger` and the
mains. That binds the same module object everywhere, so the shared
`current_motor_speed` really is shared.

Deliberately not applied: it switches on a safety system that has been doing
nothing. `_cut_motor()` would start cutting power at 15 cm front / 12 cm rear with
a 500 ms cooldown, which deserves a low-speed test of its own rather than arriving
as a side effect of an OLED change.

### 3. Concurrent connections

`_handle_client`'s docstring says "one at a time" but nothing enforces it. A second
connection overwrites `_ws_writer`, and whichever closes first runs `_safe_stop()`
and clears `_client_connected` under the other.

Naively rejecting the second connection is worse: if the Pico has not noticed a
dead socket, the reconnecting client would be locked out until the old read fails,
which may be never. The fix is a take-over — close the old writer and
generation-tag the handler so the outgoing one cannot clear shared state.

### 4. Smaller items

- `gc.threshold(4096)` is aggressive; short pauses, but a lot of them.
- `brake()` leaves both H-bridge pins at 100% duty indefinitely, holding current
  until the next motor command. Pre-existing behaviour, not touched.
- `motor3.py:62-69` labels `direction < 0` as "Forward", which contradicts the sign
  convention used everywhere else. Behaviour was left alone and `_apply_lights`
  follows the client's old mapping (`speed > 0` → front light). If the front light
  comes on while reversing, swap the two branches in `_apply_lights`.
- `gear.display_gear()` and `servo.display_servo()` are the same shape as the old
  `display_motor_status()` but are not wired into the actuator writes, so they were
  never a hot-path cost. `display_gear()` has no callers at all.
