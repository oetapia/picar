import time
import machine
import network
import json
from microdot import Microdot, Response
import secrets  # WiFi credentials

# Import your custom modules
import display

# ========== Pin Setup ==========
# (Keep your existing pin setup code here - LEDs, motors, servo, etc.)

# LEDs
led = machine.Pin("LED", machine.Pin.OUT)
light_back = machine.Pin(1, machine.Pin.OUT)   # Reverse indicator
light_front = machine.Pin(2, machine.Pin.OUT)  # Forward indicator
light_back.off()
light_front.off()

# Motor control pins
AIN1 = machine.Pin(11, machine.Pin.OUT)
AIN2 = machine.Pin(12, machine.Pin.OUT)
PWMA = machine.PWM(machine.Pin(10))   # Speed (PWM)
STBY = machine.Pin(13, machine.Pin.OUT)

PWMA.freq(1000)
current_motor_speed = 0  # signed: + = forward, - = reverse

# --- SERVO SETUP ---
servo = machine.PWM(machine.Pin(6))  # GPIO 6 for servo PWM
servo.freq(50)  # 50Hz standard
current_angle = 0  # Direction: -90 (left) to +90 (right), 0 = center

def set_servo_angle(angle):
    """Set servo to absolute angle 0–180°"""
    pulse_width = 500 + (angle / 180.0) * 2000  # 500 to 2500 µs
    duty = int((pulse_width / 20000.0) * 65535)
    servo.duty_u16(duty)
	

def set_direction(angle=None, percent=None):
    """Set steering direction using angle (-90 to 90) or percent (-100 to 100)"""
    global current_angle
    if percent is not None:
        angle = (max(-100, min(100, percent)) / 100) * 90
    elif angle is not None:
        angle = max(-90, min(90, angle))
    else:
        angle = 0
    current_angle = angle
    servo_angle = 90 + angle  # Map -90:90 → 0:180
    set_servo_angle(servo_angle)

def display_servo():
    display.update_display(header="Servo Position", text=f'{current_angle:.0f}°')
    print(f"Servo angle: {current_angle:.0f}°")

# ========== Motor Logic ==========
def update_motor():
    global current_motor_speed  # Range: -100 to +100

    # Dead zone: stop motor if input near zero
    if -5 < current_motor_speed < 5:
        STBY.low()
        PWMA.duty_u16(0)
        AIN1.low()
        AIN2.low()
        light_back.off()
        light_front.off()
    else:
        STBY.high()

        # Gentler speed curve for brushless motor
        min_duty = 25000  # Lower minimum for smoother start
        max_duty = 60000  # Lower maximum to prevent harshness

        # Determine direction and scale magnitude
        direction = 1 if current_motor_speed > 0 else -1
        speed_input = abs(current_motor_speed)

        # Smoother curve: square root for gentler acceleration
        import math
        normalized_linear = (speed_input - 5) / 95  # Normalize from 5-100 to 0-1
        normalized_smooth = math.sqrt(normalized_linear) if normalized_linear > 0 else 0
        speed_value = int(min_duty + normalized_smooth * (max_duty - min_duty))

        # Apply direction pins
        if direction > 0:
            AIN1.high()
            AIN2.low()
            light_front.on()
            light_back.off()
        else:
            AIN1.low()
            AIN2.high()
            light_front.off()
            light_back.on()

        PWMA.duty_u16(speed_value)

    display_motor_status()

def display_motor_status():
    direction = "Forward" if current_motor_speed > 0 else "Reverse" if current_motor_speed < 0 else "Stopped"
    speed_text = f"{abs(current_motor_speed)} ({direction})"
    display.update_display(header="Motor Status", text=speed_text)
    print(f"Motor: {speed_text}")

# ========== WiFi Connection ==========
def connect_wifi():
    """Connect to WiFi using secrets.py"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print(f'Connecting to WiFi: {secrets.ssid}')
        wlan.connect(secrets.ssid, secrets.password)
        
        # Wait for connection with timeout
        timeout = 10
        while timeout > 0:
            if wlan.isconnected():
                break
            print('Waiting for connection...')
            time.sleep(1)
            timeout -= 1
            
        if not wlan.isconnected():
            print('WiFi connection failed!')
            return None
    
    ip_info = wlan.ifconfig()
    print(f'Connected to WiFi. IP: {ip_info[0]}')
    return wlan

# ========== Initial State ==========
time.sleep(2)
led.off()
light_back.off()
light_front.off()
update_motor()
set_servo_angle(90)  # Center position
display_servo()

# ========== Wi-Fi Connection ==========
wlan = connect_wifi()

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

def create_cors_response(data, status_code=200):
    """Create a properly formatted CORS response for Microdot"""
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
    """Motor control API endpoint"""
    global current_motor_speed
    led.on()
    
    try:
        current_motor_speed = max(-100, min(100, speed))
        update_motor()
        
        response_data = {
            'success': True,
            'motor_speed': current_motor_speed,
            'message': f'Motor speed: {current_motor_speed}'
        }
        print(f"🔧 Motor speed set to {current_motor_speed}")
        
    except Exception as e:
        response_data = {
            'success': False,
            'message': f'Motor error: {e}'
        }
        print(f"❌ Motor error: {e}")
    
    finally:
        led.off()
    
    return create_cors_response(response_data)

@app.route('/api/servo/<int:angle>')
def api_servo(request, angle):
    """Servo control API endpoint"""
    global current_angle
    led.on()
    
    try:
        angle = max(0, min(180, angle))
        current_angle = angle - 90  # Convert to internal -90:90 range
        set_servo_angle(angle)
        display_servo()
        
        response_data = {
            'success': True,
            'servo_angle': angle,
            'message': f'Servo angle: {angle}°'
        }
        print(f"🔁 Servo angle set to {angle}°")
        
    except Exception as e:
        response_data = {
            'success': False,
            'message': f'Servo error: {e}'
        }
        print(f"❌ Servo error: {e}")
    
    finally:
        led.off()
    
    return create_cors_response(response_data)

@app.route('/api/text', methods=['POST'])
def api_text(request):
    """Text display API endpoint"""
    led.on()
    
    try:
        data = json.loads(request.body.decode('utf-8'))
        text = str(data.get('text', ''))
        display.update_display(header="HTTP API", text=text)
        
        response_data = {
            'success': True,
            'message': f'Displayed: {text}'
        }
        print(f"🖥️ Displayed text: {text}")
        
    except Exception as e:
        response_data = {
            'success': False,
            'message': f'Text error: {e}'
        }
        print(f"❌ Text error: {e}")
    
    finally:
        led.off()
    
    return create_cors_response(response_data)

@app.route('/api/status')
def api_status(request):
    """Status API endpoint"""
    response_data = {
        'success': True,
        'motor_speed': current_motor_speed,
        'servo_angle': current_angle + 90,  # Convert to 0-180 range
        'message': f'Motor: {current_motor_speed}, Servo: {current_angle + 90}°'
    }
    
    return create_cors_response(response_data)

@app.route('/api/test')
def api_test(request):
    """Simple test endpoint to verify CORS"""
    response_data = {
        'success': True,
        'message': 'CORS is working!',
        'timestamp': time.time()
    }
    return create_cors_response(response_data)

# ========== Start Server ==========
def start_server():
    print(f"🚀 Starting HTTP Robot Server...")
    if wlan and wlan.isconnected():
        print(f"🌐 Server running at: http://{ip_address}:5000")
        display.update_display(header="Server Ready", text=f"{ip_address}:5000")
    else:
        print("⚠️ WiFi not connected - server will run on localhost only")
        display.update_display(header="Server Ready", text="WiFi Failed")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        if wlan:
            wlan.disconnect()

# ========== Start Everything ==========
if __name__ == '__main__':
    start_server()