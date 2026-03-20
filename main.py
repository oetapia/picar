import time
import machine
import json
import uasyncio as asyncio
from microdot import Microdot, Response

import display
import motor
import servo
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

@app.route('/api/accelerometer')
def api_accelerometer(request):
    state = accelerometer.get_state()
    if state['available']:
        response_data = {
            'success': True,
            'acceleration': state['acceleration'],
            'gyroscope': state['gyroscope'],
            'tilt': state['tilt'],
            'orientation': state['orientation'],
            'timestamp': state['timestamp'],
            'message': 'P:{:+.0f}° R:{:+.0f}° {}'.format(
                state['tilt']['pitch'],
                state['tilt']['roll'],
                state['orientation']
            )
        }
    else:
        response_data = {
            'success': False,
            'message': 'MPU-6050 sensor not available',
            'available': False
        }
    return create_cors_response(response_data)

@app.route('/api/tof')
def api_tof(request):
    state = dual_tof.get_state()
    if state['available']:
        # Build response with distance data
        response_data = {
            'success': True,
            'left_distance_cm': state['left_distance_cm'],
            'right_distance_cm': state['right_distance_cm'],
            'left_available': state['left_available'],
            'right_available': state['right_available'],
            'timestamp': state['timestamp']
        }
        
        # Add angle data if available (requires both sensors)
        if state['angle']:
            response_data['angle'] = state['angle']
            angle_data = state['angle']
            response_data['message'] = 'L:{:.1f}cm R:{:.1f}cm | {:+.2f}° {}'.format(
                state['left_distance_cm'] if state['left_distance_cm'] else 0,
                state['right_distance_cm'] if state['right_distance_cm'] else 0,
                angle_data['angle_degrees'],
                angle_data['orientation']
            )
        else:
            left_str = f"{state['left_distance_cm']:.1f}cm" if state['left_distance_cm'] else "---"
            right_str = f"{state['right_distance_cm']:.1f}cm" if state['right_distance_cm'] else "---"
            response_data['message'] = f'L:{left_str} R:{right_str}'
    else:
        response_data = {
            'success': False,
            'message': 'VL53L0X ToF sensors not available',
            'available': False
        }
    return create_cors_response(response_data)

@app.route('/api/ultrasonic')
def api_ultrasonic(request):
    state = hcsr04.get_state()
    if state['available']:
        distance = state['distance_cm']
        in_range = state['in_range']
        
        response_data = {
            'success': True,
            'distance_cm': distance,
            'in_range': in_range,
            'timestamp': state['timestamp']
        }
        
        if distance:
            response_data['message'] = f'Rear: {distance:.1f}cm'
        else:
            response_data['message'] = 'Rear: No obstacle detected'
    else:
        response_data = {
            'success': False,
            'message': 'HC-SR04 ultrasonic sensor not available',
            'available': False
        }
    return create_cors_response(response_data)

@app.route('/api/lights')
def api_lights_status(request):
    """Get current light status."""
    state = lights.get_state()
    if state['available']:
        response_data = {
            'success': True,
            'front': state['front'],
            'back': state['back'],
            'status': state['status'],
            'timestamp': state['timestamp'],
            'message': f'Lights: {state["status"]}'
        }
    else:
        response_data = {
            'success': False,
            'message': 'Lights not available',
            'available': False
        }
    return create_cors_response(response_data)

@app.route('/api/lights/<status>')
def api_lights_control(request, status):
    """Control lights with status: front, back, both, off."""
    led.on()
    try:
        status = status.lower()
        
        if status == 'front':
            lights.lights_front()
            message = 'Front lights on'
        elif status == 'back':
            lights.lights_back()
            message = 'Back lights on'
        elif status == 'both':
            lights.lights_both()
            message = 'Both lights on'
        elif status == 'off':
            lights.lights_off()
            message = 'Lights off'
        else:
            led.off()
            return create_cors_response({
                'success': False,
                'message': f'Invalid status: {status}. Use: front, back, both, or off'
            }, status_code=400)
        
        state = lights.get_state()
        _on_command(request, f"Lights: {state['status']}")
        
        response_data = {
            'success': True,
            'front': state['front'],
            'back': state['back'],
            'status': state['status'],
            'message': message
        }
        print(message)
        
    except Exception as e:
        response_data = {'success': False, 'message': f'Lights error: {e}'}
        print(f"Lights error: {e}")
    finally:
        led.off()
    
    return create_cors_response(response_data)

@app.route('/api/proximity_guard')
def api_proximity_guard(request):
    """Get proximity guard status (Pico-side emergency stop)."""
    state = proximity_guard.get_state()
    response_data = {
        'success': True,
        'enabled': state['enabled'],
        'interventions': state['interventions'],
        'last_front_cm': state['last_front_cm'],
        'last_rear_cm': state['last_rear_cm'],
        'message': f'Guard: {"ON" if state["enabled"] else "OFF"} | Stops: {state["interventions"]}'
    }
    return create_cors_response(response_data)

# ========== Data Logger Endpoints ==========

@app.route('/api/log/start', methods=['POST'])
def api_log_start(request):
    """Start recording sensor data for offline modeling."""
    try:
        body = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        body = {}
    interval_ms = body.get('interval_ms')
    max_samples = body.get('max_samples')
    result = data_logger.start(interval_ms=interval_ms, max_samples=max_samples)
    if result['success']:
        _on_command(request, "Log: REC")
    return create_cors_response(result)

@app.route('/api/log/stop', methods=['POST'])
def api_log_stop(request):
    """Stop recording and flush to flash."""
    result = data_logger.stop()
    if result['success']:
        _on_command(request, f"Log: {result.get('sample_count', 0)} saved")
    return create_cors_response(result)

@app.route('/api/log/status')
def api_log_status(request):
    """Get logger status (recording, sample count, file ready)."""
    status = data_logger.get_status()
    status['success'] = True
    return create_cors_response(status)

@app.route('/api/log/download')
def api_log_download(request):
    """Download the log profile JSON and auto-erase from Pico."""
    result = data_logger.download_and_erase()
    if result.get('success'):
        _on_command(request, "Log: downloaded")
    return create_cors_response(result)

@app.route('/api/log/clear', methods=['DELETE'])
def api_log_clear(request):
    """Erase stored log without downloading."""
    result = data_logger.clear()
    return create_cors_response(result)

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

# ========== Start Everything ==========
if __name__ == '__main__':
    asyncio.run(start_server())
