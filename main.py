import time
import machine
import json
import uasyncio as asyncio
from microdot import Microdot, Response

import display
import motor
import servo
import wifi
from sensors import payload_sensor

# ========== LED ==========
led = machine.Pin("LED", machine.Pin.OUT)

# ========== Initial State ==========
time.sleep(2)
led.off()
motor.update_motor()
servo.set_servo_angle(90)  # Center position
servo.display_servo()

# ========== WiFi Connection ==========
wlan = wifi.connect_wifi()

if wlan:
    ip_address = wlan.ifconfig()[0]
    print("Connected to Wi-Fi. IP Address:", ip_address)
    display.update_display(header="HTTP Server", text=f"{ip_address}:5000")
    led.on()
    time.sleep(1)
    led.off()
else:
    print("Wi-Fi connection failed.")
    display.update_display(header="Wi-Fi", text="Connection Failed")

# ========== Microdot API Server ==========
app = Microdot()

# ========== Display Helpers ==========
_last_command_time = 0
IDLE_TIMEOUT = 5  # seconds of silence before reverting to server IP

def _on_command(request, label, icon=None):
    global _last_command_time
    _last_command_time = time.time()
    try:
        client_ip = request.client_addr[0]
    except Exception:
        client_ip = "?"
    display.update_display(header=client_ip, text=label, icon=icon)

async def _idle_watcher():
    global _last_command_time
    while True:
        await asyncio.sleep(1)
        if _last_command_time and time.time() - _last_command_time >= IDLE_TIMEOUT:
            _last_command_time = 0
            if wlan and wlan.isconnected():
                display.update_display(header="Server Ready", text=f"{ip_address}:5000")
            else:
                display.update_display(header="Server Ready", text="WiFi Failed")

def create_cors_response(data, status_code=200):
    response = Response(json.dumps(data), status_code=status_code)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

app.options_handler = lambda req: {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
}

# ========== API Endpoints ==========

@app.route('/api/motor/<int:speed>')
def api_motor(request, speed):
    led.on()
    try:
        motor.current_motor_speed = max(-100, min(100, speed))
        motor.update_motor()
        _on_command(request, f"Motor: {motor.current_motor_speed}")
        response_data = {
            'success': True,
            'motor_speed': motor.current_motor_speed,
            'message': f'Motor speed: {motor.current_motor_speed}'
        }
        print(f"Motor speed set to {motor.current_motor_speed}")
    except Exception as e:
        response_data = {'success': False, 'message': f'Motor error: {e}'}
        print(f"Motor error: {e}")
    finally:
        led.off()
    return create_cors_response(response_data)

@app.route('/api/servo/<int:angle>')
def api_servo(request, angle):
    led.on()
    try:
        angle = max(0, min(180, angle))
        servo.current_angle = angle - 90  # Convert to internal -90:90 range
        servo.set_servo_angle(angle)
        _on_command(request, f"Servo: {angle}")
        response_data = {
            'success': True,
            'servo_angle': angle,
            'message': f'Servo angle: {angle}°'
        }
        print(f"Servo angle set to {angle}°")
    except Exception as e:
        response_data = {'success': False, 'message': f'Servo error: {e}'}
        print(f"Servo error: {e}")
    finally:
        led.off()
    return create_cors_response(response_data)

@app.route('/api/text', methods=['POST'])
def api_text(request):
    led.on()
    try:
        data = json.loads(request.body.decode('utf-8'))
        text = str(data.get('text', ''))
        icon = data.get('icon') or None
        _on_command(request, text if text else "(clear)", icon=icon)
        response_data = {'success': True, 'message': f'Displayed: {text}'}
        print(f"Displayed text: {text}, icon: {icon}")
    except Exception as e:
        response_data = {'success': False, 'message': f'Text error: {e}'}
        print(f"Text error: {e}")
    finally:
        led.off()
    return create_cors_response(response_data)

@app.route('/api/icons')
def api_icons(_request):
    try:
        with open('icons.json') as f:
            data = json.load(f)
        icon_names = sorted(data.keys())
    except Exception as e:
        print(f"icons.json read error: {e}")
        icon_names = []
    return create_cors_response({'success': True, 'icons': icon_names})

@app.route('/api/status')
def api_status(request):
    response_data = {
        'success': True,
        'motor_speed': motor.current_motor_speed,
        'servo_angle': servo.current_angle + 90,
        'message': f'Motor: {motor.current_motor_speed}, Servo: {servo.current_angle + 90}°'
    }
    return create_cors_response(response_data)

@app.route('/api/sensors')
def api_sensors(request):
    state = payload_sensor.get_state()
    response_data = {
        'success': True,
        'left_front':  state['left_front'],
        'right_front': state['right_front'],
        'left_back':   state['left_back'],
        'right_back':  state['right_back'],
        'timestamp':   state['timestamp'],
        'message': 'LF:{} RF:{} LB:{} RB:{}'.format(
            state['left_front'], state['right_front'],
            state['left_back'],  state['right_back']
        )
    }
    return create_cors_response(response_data)

@app.route('/api/test')
def api_test(request):
    response_data = {'success': True, 'message': 'CORS is working!', 'timestamp': time.time()}
    return create_cors_response(response_data)

# ========== Start Server ==========
async def start_server():
    print("Starting HTTP Robot Server...")
    if wlan and wlan.isconnected():
        print(f"Server running at: http://{ip_address}:5000")
        display.update_display(header="Server Ready", text=f"{ip_address}:5000")
    else:
        print("WiFi not connected - server will run on localhost only")
        display.update_display(header="Server Ready", text="WiFi Failed")
    asyncio.create_task(payload_sensor.monitor())
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

# ========== Start Everything ==========
if __name__ == '__main__':
    asyncio.run(start_server())
