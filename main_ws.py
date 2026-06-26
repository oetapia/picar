"""
WebSocket-only server for Picar (Raspberry Pi Pico W).

Low-latency alternative to main.py REST server.
Single persistent WebSocket connection — no HTTP overhead per command.

Usage: Copy this file as main.py on the Pico to use WebSocket mode,
       or keep both and rename at deploy time.

Protocol (JSON, short keys to minimize bytes):
    Client → Pico:
        {"c":"m","v":50}        motor speed (-100..100)
        {"c":"b"}               brake
        {"c":"s","v":120}       servo angle (0..180)
        {"c":"g","v":"on"}      gear: on/off/toggle
        {"c":"l","v":"front"}   lights: front/back/both/off
        {"c":"t","v":"hello"}   display text (optional "i" for icon)
        {"c":"st"}              request status
        {"c":"sub","ms":100}    subscribe sensor push (interval ms)
        {"c":"unsub"}           unsubscribe sensor push

    Pico → Client:
        {"ok":1,"m":50}                       command ack
        {"ok":1,"st":{...}}                   status response
        {"t":"sns","accel":{...},"tof":{...},"ultra":{...},"ts":123}  sensor push
        {"ok":0,"e":"error message"}          error
"""

import time
import machine
import json
import uasyncio as asyncio
from microdot import Microdot, Response
from microdot.websocket import with_websocket

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
servo.set_servo_angle(90)  # Center position
servo.display_servo()
gear.set_gear(False)  # Start with gear off

# ========== WiFi Connection ==========
wlan = wifi.connect_wifi()

if wlan:
    ip_address = wlan.ifconfig()[0]
    print("Connected to Wi-Fi. IP Address:", ip_address)
    display.update_display(header="WS Server", text=f"{ip_address}:5000")
    led.on()
    time.sleep(1)
    led.off()
else:
    print("Wi-Fi connection failed.")
    display.update_display(header="Wi-Fi", text="Connection Failed")
    ip_address = "0.0.0.0"

# ========== Microdot App (WebSocket only) ==========
app = Microdot()

# ========== Connection State ==========
_client_connected = False
_client_ip = None
_last_command_time = 0
_sensor_push_interval = 0  # 0 = disabled, >0 = push interval in ms
_sensor_push_task = None
_ws_ref = None  # reference to active WebSocket for push

IDLE_TIMEOUT = 5  # seconds before reverting display to server IP


# ========== Command Dispatcher ==========

def handle_command(cmd):
    """Dispatch a command dict and return response dict."""
    global _last_command_time, _sensor_push_interval
    _last_command_time = time.time()
    
    c = cmd.get("c")
    v = cmd.get("v")
    
    try:
        if c == "m":
            # Motor speed
            speed = max(-100, min(100, int(v)))
            motor.current_motor_speed = speed
            motor.update_motor()
            _show(f"Motor: {speed}")
            return {"ok": 1, "m": speed}
        
        elif c == "b":
            # Brake
            if hasattr(motor, 'brake'):
                motor.brake()
            motor.current_motor_speed = 0
            _show("BRAKE")
            return {"ok": 1, "m": 0}
        
        elif c == "s":
            # Servo angle
            angle = max(0, min(180, int(v)))
            servo.current_angle = angle - 90
            servo.set_servo_angle(angle)
            _show(f"Servo: {angle}")
            return {"ok": 1, "s": angle}
        
        elif c == "g":
            # Gear
            status = str(v).lower()
            if status == "on":
                gear.set_gear(True)
            elif status == "off":
                gear.set_gear(False)
            elif status == "toggle":
                gear.toggle_gear()
            else:
                return {"ok": 0, "e": f"gear: {v}"}
            state = "LOW" if gear.gear_on else "OFF"
            _show(f"Gear: {state}")
            return {"ok": 1, "g": 1 if gear.gear_on else 0}
        
        elif c == "l":
            # Lights
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
                return {"ok": 0, "e": f"lights: {v}"}
            st = lights.get_state()
            _show(f"Lights: {st['status']}")
            return {"ok": 1, "l": st['status']}
        
        elif c == "t":
            # Display text
            text = str(v) if v else ""
            icon = cmd.get("i")
            display.update_display(header=_client_ip or "WS", text=text, icon=icon)
            return {"ok": 1}
        
        elif c == "st":
            # Status
            return {
                "ok": 1,
                "st": {
                    "m": motor.current_motor_speed,
                    "s": servo.current_angle + 90,
                    "g": 1 if gear.gear_on else 0,
                    "l": lights.get_state().get('status', 'off'),
                }
            }
        
        elif c == "sns":
            # One-shot sensor read
            return {"ok": 1, "sns": _read_sensors()}
        
        elif c == "sub":
            # Subscribe to sensor push
            ms = int(cmd.get("ms", 100))
            _sensor_push_interval = max(50, ms)  # minimum 50ms
            return {"ok": 1, "sub": _sensor_push_interval}
        
        elif c == "unsub":
            # Unsubscribe from sensor push
            _sensor_push_interval = 0
            return {"ok": 1, "unsub": 1}
        
        elif c == "pg":
            # Proximity guard status
            state = proximity_guard.get_state()
            return {
                "ok": 1,
                "pg": {
                    "enabled": state['enabled'],
                    "interventions": state['interventions'],
                    "front_cm": state['last_front_cm'],
                    "rear_cm": state['last_rear_cm'],
                }
            }
        
        else:
            return {"ok": 0, "e": f"unknown: {c}"}
    
    except Exception as e:
        return {"ok": 0, "e": str(e)}


def _read_sensors():
    """Read all sensors and return compact dict."""
    result = {}
    
    # Accelerometer
    accel = accelerometer.get_state()
    if accel.get('available'):
        result['accel'] = {
            'p': round(accel['tilt']['pitch'], 1),
            'r': round(accel['tilt']['roll'], 1),
            'o': accel['orientation'],
        }
    
    # ToF
    tof = dual_tof.get_state()
    if tof.get('available'):
        result['tof'] = {
            'l': round(tof['left_distance_cm'], 1) if tof['left_distance_cm'] else None,
            'r': round(tof['right_distance_cm'], 1) if tof['right_distance_cm'] else None,
        }
        if tof.get('angle'):
            result['tof']['a'] = round(tof['angle']['angle_degrees'], 2)
    
    # Ultrasonic
    ultra = hcsr04.get_state()
    if ultra.get('available'):
        result['ultra'] = {
            'd': round(ultra['distance_cm'], 1) if ultra['distance_cm'] else None,
            'ir': ultra['in_range'],
        }
    
    result['ts'] = time.time()
    return result


def _show(text):
    """Update OLED with command info."""
    display.update_display(header=_client_ip or "WS", text=text)


def _safe_stop():
    """Emergency stop — called when client disconnects."""
    motor.current_motor_speed = 0
    motor.update_motor()
    if hasattr(motor, 'brake'):
        motor.brake()
    print("Safety stop: client disconnected")


# ========== WebSocket Endpoint ==========

@app.route('/ws')
@with_websocket
async def ws_handler(request, ws):
    """Main WebSocket handler — one client at a time."""
    global _client_connected, _client_ip, _last_command_time
    global _sensor_push_interval, _sensor_push_task, _ws_ref
    
    # Get client IP
    try:
        _client_ip = request.client_addr[0]
    except Exception:
        _client_ip = "?"
    
    _client_connected = True
    _ws_ref = ws
    _last_command_time = time.time()
    _sensor_push_interval = 0
    
    print(f"WebSocket connected: {_client_ip}")
    display.update_display(header="Connected", text=_client_ip)
    led.on()
    
    # Start sensor push task
    push_task = asyncio.create_task(_sensor_push_loop(ws))
    
    try:
        while True:
            msg = await ws.receive()
            if msg is None:
                break
            
            led.on()
            try:
                cmd = json.loads(msg)
                response = handle_command(cmd)
                await ws.send(json.dumps(response))
            except ValueError:
                await ws.send(json.dumps({"ok": 0, "e": "bad json"}))
            except Exception as e:
                await ws.send(json.dumps({"ok": 0, "e": str(e)}))
            finally:
                led.off()
    
    except Exception as e:
        print(f"WebSocket error: {e}")
    
    finally:
        # Client disconnected
        _client_connected = False
        _ws_ref = None
        _sensor_push_interval = 0
        push_task.cancel()
        
        # Safety stop
        _safe_stop()
        
        print(f"WebSocket disconnected: {_client_ip}")
        display.update_display(header="Disconnected", text="Waiting...")
        led.off()
        
        # After a moment, show server address again
        await asyncio.sleep(2)
        if not _client_connected:
            display.update_display(header="WS Server", text=f"{ip_address}:5000")


async def _sensor_push_loop(ws):
    """Push sensor data to client at subscribed interval."""
    while True:
        if _sensor_push_interval > 0:
            try:
                data = _read_sensors()
                msg = json.dumps({"t": "sns", **data})
                await ws.send(msg)
            except Exception:
                break  # Connection lost
            await asyncio.sleep(_sensor_push_interval / 1000.0)
        else:
            # Not subscribed — check again in 100ms
            await asyncio.sleep(0.1)


# ========== Idle Display Watcher ==========

async def _idle_watcher():
    """Revert display to server IP after idle timeout."""
    global _last_command_time
    while True:
        await asyncio.sleep(1)
        if _client_connected and _last_command_time:
            if time.time() - _last_command_time >= IDLE_TIMEOUT:
                _last_command_time = 0
                display.update_display(header=_client_ip or "Connected", text="Idle")


# ========== Start Server ==========

async def start_server():
    print("Starting WebSocket Robot Server...")
    if wlan and wlan.isconnected():
        print(f"WebSocket endpoint: ws://{ip_address}:5000/ws")
        display.update_display(header="WS Server", text=f"{ip_address}:5000")
    else:
        print("WiFi not connected - server will run on localhost only")
        display.update_display(header="WS Server", text="WiFi Failed")
    
    # Start sensor monitors (same as main.py)
    asyncio.create_task(lights.monitor())
    asyncio.create_task(accelerometer.monitor())
    asyncio.create_task(dual_tof.monitor())
    asyncio.create_task(hcsr04.monitor())
    asyncio.create_task(proximity_guard.monitor())
    asyncio.create_task(data_logger.monitor())
    asyncio.create_task(_idle_watcher())
    
    try:
        await app.start_server(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("Server stopped by user")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        if wlan:
            wlan.disconnect()


# ========== Entry Point ==========
if __name__ == '__main__':
    asyncio.run(start_server())
