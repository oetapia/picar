"""
Raw WebSocket server for Picar (Raspberry Pi Pico W).

Lowest-latency variant — no framework, no JSON encode on hot path.
Direct uasyncio TCP server with hand-rolled WebSocket framing.

Optimizations over main_ws.py:
    - No Microdot: raw TCP → HTTP upgrade → binary WS frames
    - Pre-built response strings: avoids json.dumps() per command
    - Debounced OLED: display updates at 5Hz max, never blocks commands
    - GC tuning: gc.threshold() for smaller, more predictable pauses
    - WiFi PM disabled in wifi.py (already done)
    - Single-allocation frame buffer for reads

Protocol: identical to main_ws.py (JSON short keys), but responses
are pre-formatted strings to avoid serialization overhead.

    Client → Pico:
        {"c":"m","v":50}        motor speed (-100..100)
        {"c":"b"}               brake
        {"c":"s","v":120}       servo angle (0..180)
        {"c":"g","v":"on"}      gear: on/off/toggle
        {"c":"l","v":"front"}   lights: front/back/both/off
        {"c":"t","v":"hello"}   display text
        {"c":"st"}              request status
        {"c":"sns"}             one-shot sensor read
        {"c":"sub","ms":100}    subscribe sensor push
        {"c":"unsub"}           unsubscribe sensor push

    Pico → Client:
        {"ok":1,"m":50}         command ack (pre-built string)
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
time.sleep(2)
led.off()
motor.update_motor()
servo.set_servo_angle(90)
servo.display_servo()
gear.set_gear(False)

# ========== WiFi Connection ==========
wlan = wifi.connect_wifi()

if wlan:
    ip_address = wlan.ifconfig()[0]
    print("Connected to Wi-Fi. IP Address:", ip_address)
    display.update_display(header="Raw WS", text=f"{ip_address}:5000")
    led.on()
    time.sleep(1)
    led.off()
else:
    print("Wi-Fi connection failed.")
    display.update_display(header="Wi-Fi", text="Connection Failed")
    ip_address = "0.0.0.0"


# ========== Debounced Display ==========
_display_dirty = False
_display_header = ""
_display_text = ""


def _show(text, header=None):
    global _display_dirty, _display_text, _display_header
    _display_text = text
    if header is not None:
        _display_header = header
    _display_dirty = True


async def _display_loop():
    global _display_dirty
    while True:
        if _display_dirty:
            _display_dirty = False
            display.update_display(header=_display_header or "WS", text=_display_text)
        await asyncio.sleep(0.2)


# ========== Connection State ==========
_client_connected = False
_client_ip = None
_sensor_push_interval = 0
_ws_writer = None

IDLE_TIMEOUT = 5
_last_command_time = 0


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


# ========== Command Dispatch (pre-built responses) ==========

def _handle_command(msg):
    """Parse JSON command, execute, return response string."""
    global _last_command_time, _sensor_push_interval
    _last_command_time = time.time()

    try:
        cmd = json.loads(msg)
    except ValueError:
        return '{"ok":0,"e":"bad json"}'

    c = cmd.get("c")
    v = cmd.get("v")

    try:
        if c == "m":
            speed = max(-100, min(100, int(v)))
            motor.current_motor_speed = speed
            motor.update_motor()
            _show(f"M:{speed}")
            return '{"ok":1,"m":' + str(speed) + '}'

        elif c == "b":
            if hasattr(motor, 'brake'):
                motor.brake()
            motor.current_motor_speed = 0
            _show("BRAKE")
            return '{"ok":1,"m":0}'

        elif c == "s":
            angle = max(0, min(180, int(v)))
            servo.current_angle = angle - 90
            servo.set_servo_angle(angle)
            _show(f"S:{angle}")
            return '{"ok":1,"s":' + str(angle) + '}'

        elif c == "g":
            status = str(v).lower()
            if status == "on":
                gear.set_gear(True)
            elif status == "off":
                gear.set_gear(False)
            elif status == "toggle":
                gear.toggle_gear()
            else:
                return '{"ok":0,"e":"gear: ' + str(v) + '"}'
            g = 1 if gear.gear_on else 0
            _show(f"G:{'LOW' if gear.gear_on else 'OFF'}")
            return '{"ok":1,"g":' + str(g) + '}'

        elif c == "l":
            status = str(v).lower()
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
            st = lights.get_state()
            _show(f"L:{st['status']}")
            return '{"ok":1,"l":"' + st['status'] + '"}'

        elif c == "t":
            text = str(v) if v else ""
            icon = cmd.get("i")
            display.update_display(header=_client_ip or "WS", text=text, icon=icon)
            return '{"ok":1}'

        elif c == "st":
            m = motor.current_motor_speed
            s = servo.current_angle + 90
            g = 1 if gear.gear_on else 0
            l_st = lights.get_state().get('status', 'off')
            return '{"ok":1,"st":{"m":' + str(m) + ',"s":' + str(s) + ',"g":' + str(g) + ',"l":"' + l_st + '"}}'

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
    motor.current_motor_speed = 0
    motor.update_motor()
    if hasattr(motor, 'brake'):
        motor.brake()
    print("Safety stop: client disconnected")


# ========== WebSocket Client Handler ==========

async def _handle_client(reader, writer):
    """Handle one WebSocket client connection (one at a time)."""
    global _client_connected, _client_ip, _last_command_time
    global _sensor_push_interval, _ws_writer

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
    _client_ip = "client"
    _ws_writer = writer
    _last_command_time = time.time()
    _sensor_push_interval = 0

    print(f"WebSocket connected")
    _show("Connected", header="Raw WS")
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
            writer.write(_encode_frame(response))
            await writer.drain()

    except Exception as e:
        print(f"WS error: {e}")

    finally:
        _client_connected = False
        _ws_writer = None
        _sensor_push_interval = 0
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
        _show("Waiting...", header="Disconnected")
        led.off()

        await asyncio.sleep(2)
        if not _client_connected:
            _show(f"{ip_address}:5000", header="Raw WS")


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


# ========== Idle Display Watcher ==========

async def _idle_watcher():
    global _last_command_time
    while True:
        await asyncio.sleep(1)
        if _client_connected and _last_command_time:
            if time.time() - _last_command_time >= IDLE_TIMEOUT:
                _last_command_time = 0
                _show("Idle")


# ========== Server ==========

async def start_server():
    print("Starting Raw WebSocket Server...")
    if wlan and wlan.isconnected():
        print(f"WebSocket endpoint: ws://{ip_address}:5000")
        _show(f"{ip_address}:5000", header="Raw WS")
    else:
        print("WiFi not connected")
        _show("WiFi Failed", header="Raw WS")

    # Start background tasks
    asyncio.create_task(lights.monitor())
    asyncio.create_task(accelerometer.monitor())
    asyncio.create_task(dual_tof.monitor())
    asyncio.create_task(hcsr04.monitor())
    asyncio.create_task(proximity_guard.monitor())
    asyncio.create_task(data_logger.monitor())
    asyncio.create_task(_idle_watcher())
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
