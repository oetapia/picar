"""
Raw WebSocket server for Picar (Raspberry Pi Pico W).

Lowest-latency variant — no framework, no JSON encode on hot path.
Direct uasyncio TCP server with hand-rolled WebSocket framing.

Optimizations over main_ws.py:
    - No Microdot: raw TCP → HTTP upgrade → binary WS frames
    - Pre-built response strings: avoids json.dumps() per command
    - State-driven OLED: the panel shows one of three states (IP when no client,
      "Connected - idle", "Manual control" while driving), so a redraw only
      happens on a state change instead of once per command
    - Lights follow the motor on the Pico, so a driving client does not spend a
      second round trip per direction change
    - GC tuning: gc.threshold() for smaller, more predictable pauses
    - WiFi PM disabled in wifi.py (already done)
    - Single-allocation frame buffer for reads

Protocol: identical to main_ws.py (JSON short keys), but responses
are pre-formatted strings to avoid serialization overhead.

    Client → Pico:
        {"c":"ctl","m":50,"s":120,"q":1}
                                combined control frame — throttle and steering
                                together. "q":1 means do not ack. This is the
                                path a driving client should use: one message
                                per tick and no reply traffic.
        {"c":"m","v":50}        motor speed (-100..100)
        {"c":"b"}               brake
        {"c":"s","v":120}       servo angle (0..180)
        {"c":"g","v":"on"}      gear: on/off/toggle
        {"c":"l","v":"front"}   lights: front/back/both/off — takes the lights
                                off automatic mode until {"c":"l","v":"auto"}
        {"c":"t","v":"hello"}   display text
        {"c":"st"}              request status
        {"c":"sns"}             one-shot sensor read
        {"c":"sub","ms":100}    subscribe sensor push
        {"c":"unsub"}           unsubscribe sensor push

    Any command may carry "r":<n>, which is echoed on the reply so the client
    can correlate the two. ("i" is not used for this — it is already the icon
    field of the "t" command.) A client that streams "ctl" frames also gets a
    failsafe: the motor stops if the frames stop (see CONTROL_TIMEOUT_MS).

    The lights follow the motor: forward lights the front, reverse the back, stop
    turns both off. A client does not need to ask for this. Sending "l" by hand
    takes over — automatic mode stays off until {"c":"l","v":"auto"}.

    Pico → Client:
        {"ok":1,"m":50}         command ack (pre-built string)
        {"r":7,"ok":1,"m":50}   ack correlated to request 7
        {"ok":0,"e":"..."}      error
        {"t":"sns",...}          sensor push
"""

import gc
gc.threshold(4096)

import time
import machine
import json
import hashlib
import binascii
import struct
import uasyncio as asyncio

import display
import motor3 as motor
import servo
import gear
import wifi
import lights
from sensors import accelerometer
from sensors import dual_tof
from sensors import hcsr04
from sensors import proximity_guard
from sensors import data_logger

# ========== LED ==========
led = machine.Pin("LED", machine.Pin.OUT)

# ========== Initial State ==========
# The motor driver redraws the OLED on every speed change, which is blocking I2C
# work in the middle of the command path. This server owns the display instead
# (see _display_loop), so the driver's own updates are switched off.
motor.show_status = False

time.sleep(2)
led.off()
motor.update_motor()
servo.set_servo_angle(90)
gear.set_gear(False)

# ========== WiFi Connection ==========
wlan = wifi.connect_wifi()

if wlan:
    ip_address = wlan.ifconfig()[0]
    print("Connected to Wi-Fi. IP Address:", ip_address)
    display.update_display(header="Picar", text=f"{ip_address}:5000")
    led.on()
    time.sleep(1)
    led.off()
else:
    print("Wi-Fi connection failed.")
    display.update_display(header="Wi-Fi", text="Connection Failed")
    ip_address = "0.0.0.0"


# ========== Display ==========
# A full 128x32 redraw is blocking I2C work, so the command path never touches
# the panel — it only names the state it wants, which is a cheap idempotent
# assignment. The display task polls at 5 Hz and redraws only on a real change,
# so streaming control frames cost nothing here no matter how fast they arrive.
DISP_IP = 0         # no client attached — show how to reach the car
DISP_IDLE = 1       # client attached, not driving
DISP_MANUAL = 2     # remote is driving
DISP_TEXT = 3       # explicit {"c":"t"} override

_disp_want = DISP_IP    # what the panel should show
_disp_shown = None      # what it currently shows (None = redraw needed)
_disp_text = ""
_disp_icon = None
_disp_ip_line = f"{ip_address}:5000" if wlan else "WiFi failed"


def _set_display(state, text=None, icon=None):
    """Request a display state. Safe to call on every command."""
    global _disp_want, _disp_shown, _disp_text, _disp_icon
    if state == DISP_TEXT:
        # Text is a payload, not a state: two different strings both mean
        # DISP_TEXT, so force the redraw rather than relying on the state check.
        _disp_text = text or ""
        _disp_icon = icon
        _disp_shown = None
    _disp_want = state


async def _display_loop():
    global _disp_shown
    while True:
        want = _disp_want
        if want != _disp_shown:
            _disp_shown = want
            if want == DISP_MANUAL:
                display.update_display(header="Picar", text="Manual control")
            elif want == DISP_IDLE:
                display.update_display(header="Picar", text="Connected - idle")
            elif want == DISP_TEXT:
                display.update_display(header="Picar", text=_disp_text,
                                       icon=_disp_icon)
            else:
                display.update_display(header="Picar", text=_disp_ip_line)
        await asyncio.sleep(0.2)


# ========== Connection State ==========
_client_connected = False
_sensor_push_interval = 0
_ws_writer = None

# Timestamps are ticks_ms, not time.time(): time.time() has one-second
# resolution on this port, which is too coarse for a one-second failsafe.
IDLE_TIMEOUT_MS = 5000
_last_control_cmd_ms = 0

# Control is pushed best-effort at ~20 Hz with a 250 ms keepalive, so a whole
# second of silence means the client or the link is gone and the car must not
# keep its last commanded speed. Only armed once a "ctl" frame has been seen, so
# the keyboard client — which sets a speed and then legitimately says nothing —
# is never cut off.
CONTROL_TIMEOUT_MS = 1000
_control_armed = False
_last_control_frame_ms = 0


# ========== WebSocket Frame Helpers ==========

def _ws_accept_key(key):
    """Compute Sec-WebSocket-Accept from client key."""
    d = hashlib.sha1(key.encode())
    d.update(b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
    return binascii.b2a_base64(d.digest())[:-1]


def _encode_frame(data, opcode=None):
    """Encode a WebSocket frame (server → client, no mask)."""
    if isinstance(data, str):
        payload = data.encode()
        if opcode is None:
            opcode = 0x01  # TEXT
    else:
        payload = data
        if opcode is None:
            opcode = 0x02  # BINARY
    fin_opcode = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes([fin_opcode, length])
    elif length < 65536:
        header = bytes([fin_opcode, 126]) + struct.pack('>H', length)
    else:
        header = bytes([fin_opcode, 127]) + struct.pack('>Q', length)
    return header + payload


async def _read_frame(reader):
    """Read one WebSocket frame. Returns (opcode, payload) or raises."""
    header = await reader.readexactly(2)
    opcode = header[0] & 0x0f
    has_mask = header[1] & 0x80
    length = header[1] & 0x7f

    if length == 126:
        raw = await reader.readexactly(2)
        length = struct.unpack('>H', raw)[0]
    elif length == 127:
        raw = await reader.readexactly(8)
        length = struct.unpack('>Q', raw)[0]

    if length > 16384:
        raise ValueError("frame too large")

    if has_mask:
        mask = await reader.readexactly(4)

    payload = await reader.readexactly(length)

    if has_mask:
        payload = bytes(payload[i] ^ mask[i & 3] for i in range(length))

    return opcode, payload


async def _ws_send(writer, data):
    """Send a WebSocket text frame."""
    writer.write(_encode_frame(data))
    await writer.drain()


# ========== Actuators ==========
# The lights used to be the client's job: it watched the speed it had just sent
# and followed up with a separate "l" command, so every direction change cost a
# second message and a second reply. The car knows its own direction, so it does
# it here instead — one command in, no extra traffic.

_lights_auto = True    # cleared by an explicit "l" command, restored by "auto"
_light_target = "off"  # last target applied here; lets redundant writes be skipped


def _apply_lights(speed):
    """Point the lights the way the car is moving."""
    global _light_target
    if not _lights_auto:
        return
    target = "front" if speed > 0 else "back" if speed < 0 else "off"
    if target == _light_target:
        return
    _light_target = target
    if target == "front":
        lights.lights_front()
    elif target == "back":
        lights.lights_back()
    else:
        lights.lights_off()


def _set_motor(speed):
    """Set the motor speed and follow it with the lights, skipping no-op writes."""
    if speed != motor.current_motor_speed:
        motor.current_motor_speed = speed
        motor.update_motor()
    _apply_lights(speed)


def _touch_control():
    """Mark remote control activity — drives the display and the idle timer.

    Only the commands that actually move the car count. Status and sensor polls
    are not "manual control" and must not hold the display awake."""
    global _last_control_cmd_ms
    _last_control_cmd_ms = time.ticks_ms()
    _set_display(DISP_MANUAL)


# ========== Command Dispatch (pre-built responses) ==========

def _handle_command(msg):
    """Parse a JSON command, dispatch it, return the response string or None.

    None means send nothing — see the "ctl" branch of _dispatch."""
    try:
        cmd = json.loads(msg)
    except ValueError:
        return '{"ok":0,"e":"bad json"}'

    response = _dispatch(cmd)
    rid = cmd.get("r")
    if response is not None and rid is not None:
        # Splice the echoed request id into the pre-built response string. The
        # client correlates replies by it, so a timed-out command's late reply
        # can no longer be read by whichever command asked next. Every response
        # here starts with '{', so replacing that brace keeps the JSON valid.
        return '{"r":' + str(rid) + ',' + response[1:]
    return response


def _dispatch(cmd):
    """Execute a parsed command and return its pre-built response string."""
    global _sensor_push_interval, _control_armed, _last_control_frame_ms
    global _lights_auto, _light_target

    c = cmd.get("c")
    v = cmd.get("v")

    try:
        if c == "ctl":
            # Combined control frame: throttle and steering in one message, so a
            # driving client costs one round of work per tick instead of two.
            # Posted fire-and-forget at ~20 Hz, so this path stays cheap —
            # redundant actuator writes are skipped (the keepalive resends
            # unchanged state) and no reply is built at all when "q" is set.
            _control_armed = True
            _last_control_frame_ms = time.ticks_ms()
            _touch_control()
            if "m" in cmd:
                _set_motor(max(-100, min(100, int(cmd["m"]))))
            if "s" in cmd:
                angle = max(0, min(180, int(cmd["s"])))
                if angle != servo.current_angle + 90:
                    servo.current_angle = angle - 90
                    servo.set_servo_angle(angle)
            if cmd.get("q"):
                return None
            return ('{"ok":1,"m":' + str(motor.current_motor_speed) +
                    ',"s":' + str(servo.current_angle + 90) + '}')

        elif c == "m":
            speed = max(-100, min(100, int(v)))
            _touch_control()
            _set_motor(speed)
            return '{"ok":1,"m":' + str(speed) + '}'

        elif c == "b":
            _touch_control()
            if hasattr(motor, 'brake'):
                motor.brake()
            motor.current_motor_speed = 0
            _apply_lights(0)
            return '{"ok":1,"m":0}'

        elif c == "s":
            angle = max(0, min(180, int(v)))
            _touch_control()
            if angle != servo.current_angle + 90:
                servo.current_angle = angle - 90
                servo.set_servo_angle(angle)
            return '{"ok":1,"s":' + str(angle) + '}'

        elif c == "g":
            status = str(v).lower()
            _touch_control()
            if status == "on":
                gear.set_gear(True)
            elif status == "off":
                gear.set_gear(False)
            elif status == "toggle":
                gear.toggle_gear()
            else:
                return '{"ok":0,"e":"gear: ' + str(v) + '"}'
            g = 1 if gear.gear_on else 0
            return '{"ok":1,"g":' + str(g) + '}'

        elif c == "l":
            # Kept for driving the lights by hand. Doing so parks automatic mode
            # so the next motor command cannot immediately override the choice.
            status = str(v).lower()
            _touch_control()
            if status == "auto":
                _lights_auto = True
                _light_target = None
                _apply_lights(motor.current_motor_speed)
                return '{"ok":1,"l":"auto"}'
            if status == "front":
                lights.lights_front()
            elif status == "back":
                lights.lights_back()
            elif status == "both":
                lights.lights_both()
            elif status == "off":
                lights.lights_off()
            else:
                return '{"ok":0,"e":"lights: ' + str(v) + '"}'
            _lights_auto = False
            return '{"ok":1,"l":"' + status + '"}'

        elif c == "t":
            _set_display(DISP_TEXT, str(v) if v else "", cmd.get("i"))
            return '{"ok":1}'

        elif c == "st":
            m = motor.current_motor_speed
            s = servo.current_angle + 90
            g = 1 if gear.gear_on else 0
            l_st = lights.get_state().get('status', 'off')
            la = 1 if _lights_auto else 0
            return ('{"ok":1,"st":{"m":' + str(m) + ',"s":' + str(s) +
                    ',"g":' + str(g) + ',"l":"' + l_st + '","la":' + str(la) + '}}')

        elif c == "sns":
            data = _read_sensors()
            return '{"ok":1,"sns":' + json.dumps(data) + '}'

        elif c == "sub":
            ms = int(cmd.get("ms", 100))
            _sensor_push_interval = max(50, ms)
            return '{"ok":1,"sub":' + str(_sensor_push_interval) + '}'

        elif c == "unsub":
            _sensor_push_interval = 0
            return '{"ok":1,"unsub":1}'

        elif c == "imu":
            accel = accelerometer.get_state()
            if accel.get('available'):
                return json.dumps({
                    "ok": 1,
                    "imu": {
                        "ax": round(accel['acceleration']['x'], 3),
                        "ay": round(accel['acceleration']['y'], 3),
                        "az": round(accel['acceleration']['z'], 3),
                        "gx": round(accel['gyroscope']['x'], 1),
                        "gy": round(accel['gyroscope']['y'], 1),
                        "gz": round(accel['gyroscope']['z'], 1),
                        "p": round(accel['tilt']['pitch'], 1),
                        "r": round(accel['tilt']['roll'], 1),
                    }
                })
            else:
                return '{"ok":0,"e":"imu unavailable"}'

        elif c == "pg":
            state = proximity_guard.get_state()
            return json.dumps({
                "ok": 1,
                "pg": {
                    "enabled": state['enabled'],
                    "interventions": state['interventions'],
                    "front_cm": state['last_front_cm'],
                    "rear_cm": state['last_rear_cm'],
                }
            })

        else:
            return '{"ok":0,"e":"unknown: ' + str(c) + '"}'

    except Exception as e:
        return '{"ok":0,"e":"' + str(e).replace('"', "'") + '"}'


def _read_sensors():
    """Read all sensors — returns dict (serialized only when needed)."""
    result = {}

    accel = accelerometer.get_state()
    if accel.get('available'):
        result['accel'] = {
            'p': round(accel['tilt']['pitch'], 1),
            'r': round(accel['tilt']['roll'], 1),
            'o': accel['orientation'],
        }

    tof = dual_tof.get_state()
    if tof.get('available'):
        result['tof'] = {
            'l': round(tof['left_distance_cm'], 1) if tof['left_distance_cm'] else None,
            'r': round(tof['right_distance_cm'], 1) if tof['right_distance_cm'] else None,
        }
        if tof.get('angle'):
            result['tof']['a'] = round(tof['angle']['angle_degrees'], 2)

    ultra = hcsr04.get_state()
    if ultra.get('available'):
        result['ultra'] = {
            'd': round(ultra['distance_cm'], 1) if ultra['distance_cm'] else None,
            'ir': ultra['in_range'],
        }

    result['ts'] = time.time()
    return result


# ========== Safety ==========

def _safe_stop():
    global _light_target
    motor.current_motor_speed = 0
    motor.update_motor()
    if hasattr(motor, 'brake'):
        motor.brake()
    # Unconditional, not via _apply_lights: a manual override must not leave the
    # lights burning after the client is gone.
    lights.lights_off()
    _light_target = "off"
    print("Safety stop: client disconnected")


# ========== WebSocket Client Handler ==========

async def _handle_client(reader, writer):
    """Handle one WebSocket client connection (one at a time)."""
    global _client_connected, _last_control_cmd_ms
    global _sensor_push_interval, _ws_writer, _control_armed, _lights_auto

    # ---------- HTTP Upgrade Handshake ----------
    ws_key = None
    try:
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if line == b'\r\n' or line == b'\n' or line == b'':
                break
            line_str = line.decode()
            if line_str.lower().startswith('sec-websocket-key:'):
                ws_key = line_str.split(':', 1)[1].strip()
    except asyncio.TimeoutError:
        writer.close()
        await writer.wait_closed()
        return

    if not ws_key:
        writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        return

    accept = _ws_accept_key(ws_key)
    writer.write(b'HTTP/1.1 101 Switching Protocols\r\n'
                 b'Upgrade: websocket\r\n'
                 b'Connection: Upgrade\r\n'
                 b'Sec-WebSocket-Accept: ')
    writer.write(accept)
    writer.write(b'\r\n\r\n')
    await writer.drain()

    # ---------- Connection established ----------
    _client_connected = True
    _ws_writer = writer
    _last_control_cmd_ms = time.ticks_ms()
    _sensor_push_interval = 0
    _lights_auto = True   # a manual override does not outlive the client that set it

    print(f"WebSocket connected")
    _set_display(DISP_IDLE)
    led.on()

    push_task = asyncio.create_task(_sensor_push_loop(writer))

    try:
        while True:
            opcode, payload = await _read_frame(reader)

            if opcode == 0x08:  # CLOSE
                break
            elif opcode == 0x09:  # PING → respond with PONG
                writer.write(_encode_frame(payload, opcode=0x0A))
                await writer.drain()
                continue
            elif opcode == 0x0A:  # PONG — ignore
                continue
            elif opcode == 0x01:  # TEXT
                try:
                    msg = payload.decode()
                except UnicodeError:
                    continue
            elif opcode == 0x02:  # BINARY
                try:
                    msg = payload.decode()
                except UnicodeError:
                    continue
            else:
                continue

            response = _handle_command(msg)
            # None means the command asked not to be acked, so nothing goes on
            # the wire — a streaming client saves a frame per tick each way.
            if response is not None:
                writer.write(_encode_frame(response))
                await writer.drain()

    except Exception as e:
        print(f"WS error: {e}")

    finally:
        _client_connected = False
        _ws_writer = None
        _sensor_push_interval = 0
        _control_armed = False    # disarm the watchdog for the next client
        push_task.cancel()
        _safe_stop()

        try:
            writer.write(_encode_frame(b'', opcode=0x08))
            await writer.drain()
        except Exception:
            pass
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        print("WebSocket disconnected")
        led.off()
        if not _client_connected:
            _set_display(DISP_IP)


# ========== Sensor Push ==========

async def _sensor_push_loop(writer):
    """Push sensor data at subscribed interval."""
    while True:
        if _sensor_push_interval > 0:
            try:
                data = _read_sensors()
                msg = '{"t":"sns",' + json.dumps(data)[1:]
                writer.write(_encode_frame(msg))
                await writer.drain()
            except Exception:
                break
            await asyncio.sleep(_sensor_push_interval / 1000.0)
        else:
            await asyncio.sleep(0.1)


# ========== Control Watchdog ==========

async def _control_watchdog():
    """Stop the motor when a streaming client goes quiet.

    Control frames are best-effort pushes, so losing the link no longer produces
    a clean disconnect that _safe_stop can catch — the car would just keep its
    last commanded speed. Arms itself only after a "ctl" frame has been seen
    (see CONTROL_TIMEOUT_MS)."""
    global _control_armed
    while True:
        await asyncio.sleep(0.2)
        if not _control_armed:
            continue
        if time.ticks_diff(time.ticks_ms(),
                           _last_control_frame_ms) >= CONTROL_TIMEOUT_MS:
            _control_armed = False   # re-arms on the next control frame
            if motor.current_motor_speed != 0:
                _set_motor(0)
                print("Control watchdog: no frames, motor stopped")


# ========== Idle Display Watcher ==========

async def _idle_watcher():
    """Drop the display back to "idle" once the remote goes quiet.

    Only demotes from "manual control": a text the client asked for stays up
    until it starts driving again. _set_display is idempotent and the display
    task only redraws on a change, so this can fire every second for free."""
    while True:
        await asyncio.sleep(1)
        if not _client_connected or _disp_want != DISP_MANUAL:
            continue
        if time.ticks_diff(time.ticks_ms(),
                           _last_control_cmd_ms) >= IDLE_TIMEOUT_MS:
            _set_display(DISP_IDLE)


# ========== Server ==========

async def start_server():
    print("Starting Raw WebSocket Server...")
    if wlan and wlan.isconnected():
        print(f"WebSocket endpoint: ws://{ip_address}:5000")
    else:
        print("WiFi not connected")
    _set_display(DISP_IP)

    # Start background tasks
    asyncio.create_task(lights.monitor())
    asyncio.create_task(accelerometer.monitor())
    asyncio.create_task(dual_tof.monitor())
    asyncio.create_task(hcsr04.monitor())
    asyncio.create_task(proximity_guard.monitor())
    asyncio.create_task(data_logger.monitor())
    asyncio.create_task(_idle_watcher())
    asyncio.create_task(_control_watchdog())
    asyncio.create_task(_display_loop())

    server = await asyncio.start_server(_handle_client, '0.0.0.0', 5000)
    print("Server listening on port 5000")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("Server stopped by user")
    finally:
        server.close()
        await server.wait_closed()
        if wlan:
            wlan.disconnect()


# ========== Entry Point ==========
if __name__ == '__main__':
    asyncio.run(start_server())
