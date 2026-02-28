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

# ========== Microdot HTTP Server with Proper CORS ==========
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

@app.before_request
def before_request(request):
    """Handle preflight OPTIONS requests"""
    if request.method == 'OPTIONS':
        response = Response('', status=204)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response

@app.route('/')
def index(request):
    """Robot control web interface using HTTP/AJAX"""
    html_content = '''<!DOCTYPE html>
<html>
<head>
    <title>Pico W Robot Control</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            background-color: #f5f5f5;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 { color: #333; text-align: center; }
        .status { 
            background: #e9ecef; 
            padding: 15px; 
            margin: 15px 0; 
            border-radius: 5px;
            border-left: 4px solid #007bff;
            font-weight: bold;
            text-align: center;
        }
        .status.connected { 
            background: #d4edda; 
            border-left-color: #28a745; 
            color: #155724;
        }
        .control-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }
        .control { 
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border: 1px solid #dee2e6;
        }
        .control h3 {
            margin-top: 0;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
            padding-bottom: 10px;
        }
        button { 
            padding: 12px 24px; 
            margin: 5px; 
            font-size: 16px; 
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-weight: 600;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
        .motor-btn { background: #28a745; color: white; }
        .motor-btn:hover { background: #218838; }
        .stop-btn { background: #dc3545; color: white; }
        .stop-btn:hover { background: #c82333; }
        .servo-btn { background: #007bff; color: white; }
        .servo-btn:hover { background: #0056b3; }
        .util-btn { background: #6c757d; color: white; }
        .util-btn:hover { background: #545b62; }
        
        .slider-container {
            margin: 15px 0;
        }
        .slider-container label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #495057;
        }
        .slider-wrapper {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .slider {
            flex: 1;
            height: 8px;
            border-radius: 5px;
            background: #ddd;
            outline: none;
            -webkit-appearance: none;
        }
        .slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #007bff;
            cursor: pointer;
        }
        .slider::-moz-range-thumb {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #007bff;
            cursor: pointer;
            border: none;
        }
        .value-display {
            min-width: 60px;
            text-align: center;
            font-weight: bold;
            font-size: 16px;
            color: #495057;
            background: white;
            padding: 5px 10px;
            border-radius: 5px;
            border: 2px solid #dee2e6;
        }
        
        .dpad {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
            margin: 15px 0;
            justify-items: center;
        }
        .dpad button {
            width: 60px;
            height: 60px;
            font-size: 20px;
            margin: 0;
        }
        .dpad .empty { visibility: hidden; }
        
        .message-input {
            display: flex;
            gap: 10px;
            margin: 15px 0;
        }
        .message-input input {
            flex: 1;
            padding: 12px;
            border: 2px solid #dee2e6;
            border-radius: 5px;
            font-size: 16px;
        }
        .message-input input:focus {
            outline: none;
            border-color: #007bff;
        }
        
        @media (max-width: 768px) {
            .control-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Pico W Robot Control</h1>
        <div class="status connected" id="status">✅ Connected - Ready to Control!</div>
        
        <div class="control-grid">
            <div class="control">
                <h3>🎮 D-Pad Control</h3>
                <div class="dpad">
                    <div class="empty"></div>
                    <button class="motor-btn" onmousedown="startMotor(getCurrentSpeed())" onmouseup="stopMotor()" ontouchstart="startMotor(getCurrentSpeed())" ontouchend="stopMotor()">⬆️</button>
                    <div class="empty"></div>
                    <button class="servo-btn" onclick="turnLeft()">⬅️</button>
                    <button class="stop-btn" onclick="emergencyStop()">⏹️</button>
                    <button class="servo-btn" onclick="turnRight()">➡️</button>
                    <div class="empty"></div>
                    <button class="motor-btn" onmousedown="startMotor(-getCurrentSpeed())" onmouseup="stopMotor()" ontouchstart="startMotor(-getCurrentSpeed())" ontouchend="stopMotor()">⬇️</button>
                    <div class="empty"></div>
                </div>
            </div>
            
            <div class="control">
                <h3>⚙️ Motor Speed Control</h3>
                <div class="slider-container">
                    <label>Speed Setting:</label>
                    <div class="slider-wrapper">
                        <span>0</span>
                        <input type="range" id="speedSlider" class="slider" min="0" max="100" value="75" 
                               oninput="updateSpeedDisplay(this.value)">
                        <span>100</span>
                    </div>
                    <div class="value-display" id="speedDisplay">75</div>
                </div>
                <div class="slider-container">
                    <label>Current Motor:</label>
                    <div class="slider-wrapper">
                        <span>-100</span>
                        <input type="range" id="motorSlider" class="slider" min="-100" max="100" value="0" 
                               oninput="updateMotorDisplay(this.value)" 
                               onmouseup="releaseMotorSlider()" 
                               ontouchend="releaseMotorSlider()">
                        <span>100</span>
                    </div>
                    <div class="value-display" id="motorDisplay">0</div>
                </div>
                <button class="stop-btn" onclick="emergencyStop()">🛑 Emergency Stop</button>
            </div>
            
            <div class="control">
                <h3>🧭 Servo Control</h3>
                <div class="slider-container">
                    <label>Servo Angle:</label>
                    <div class="slider-wrapper">
                        <span>0°</span>
                        <input type="range" id="servoSlider" class="slider" min="0" max="180" value="90" 
                               oninput="updateServoDisplay(this.value)" 
                               onchange="sendServo(this.value)">
                        <span>180°</span>
                    </div>
                    <div class="value-display" id="servoDisplay">90°</div>
                </div>
                <button class="servo-btn" onclick="turnLeft()">⬅️ Left</button>
                <button class="servo-btn" onclick="sendServo(90)">🎯 Center</button>
                <button class="servo-btn" onclick="turnRight()">➡️ Right</button>
            </div>
            
            <div class="control">
                <h3>💬 Send Message</h3>
                <div class="message-input">
                    <input type="text" id="messageInput" placeholder="Type your message here..." maxlength="50">
                    <button class="util-btn" onclick="sendMessage()">📤 Send</button>
                </div>
                <button class="util-btn" onclick="getStatus()">📊 Get Status</button>
                <button class="util-btn" onclick="clearMessage()">🗑️ Clear Display</button>
            </div>
        </div>
    </div>

    <script>
        function updateStatus(message, isSuccess = true) {
            const status = document.getElementById('status');
            status.textContent = isSuccess ? `✅ ${message}` : `⚠️ ${message}`;
            status.className = isSuccess ? 'status connected' : 'status';
        }
        
        function updateSpeedDisplay(value) {
            document.getElementById('speedDisplay').textContent = value;
        }
        
        function updateMotorDisplay(value) {
            document.getElementById('motorDisplay').textContent = value;
        }
        
        function updateServoDisplay(value) {
            document.getElementById('servoDisplay').textContent = value + '°';
        }
        
        function getCurrentSpeed() {
            return parseInt(document.getElementById('speedSlider').value);
        }
        
        function startMotor(speed) {
            sendMotor(speed);
        }
        
        function stopMotor() {
            sendMotor(0);
        }
        
        function releaseMotorSlider() {
            // Auto-return motor slider to center (0) when released
            setTimeout(() => {
                document.getElementById('motorSlider').value = 0;
                updateMotorDisplay(0);
                sendMotor(0);
            }, 100);
        }
        
        function turnLeft() {
            const currentAngle = parseInt(document.getElementById('servoSlider').value);
            const newAngle = Math.max(0, currentAngle - 15); // Turn left by 15° each press
            sendServo(newAngle);
        }
        
        function turnRight() {
            const currentAngle = parseInt(document.getElementById('servoSlider').value);
            const newAngle = Math.min(180, currentAngle + 15); // Turn right by 15° each press
            sendServo(newAngle);
        }
        
        function sendMotor(speed) {
            fetch(`/api/motor/${speed}`)
                .then(response => response.json())
                .then(data => {
                    updateStatus(data.message, data.success);
                    document.getElementById('motorSlider').value = speed;
                    updateMotorDisplay(speed);
                })
                .catch(error => {
                    updateStatus('Motor command failed', false);
                    console.error('Motor error:', error);
                });
        }
        
        function sendServo(angle) {
            fetch(`/api/servo/${angle}`)
                .then(response => response.json())
                .then(data => {
                    updateStatus(data.message, data.success);
                    document.getElementById('servoSlider').value = angle;
                    updateServoDisplay(angle);
                })
                .catch(error => {
                    updateStatus('Servo command failed', false);
                    console.error('Servo error:', error);
                });
        }
        
        function sendMessage() {
            const message = document.getElementById('messageInput').value.trim();
            if (!message) {
                updateStatus('Please enter a message', false);
                return;
            }
            
            fetch('/api/text', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: message})
            })
                .then(response => response.json())
                .then(data => {
                    updateStatus(data.message, data.success);
                    if (data.success) {
                        document.getElementById('messageInput').value = '';
                    }
                })
                .catch(error => {
                    updateStatus('Message send failed', false);
                    console.error('Message error:', error);
                });
        }
        
        function clearMessage() {
            fetch('/api/text', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: ''})
            })
                .then(response => response.json())
                .then(data => updateStatus('Display cleared', data.success))
                .catch(error => {
                    updateStatus('Clear failed', false);
                    console.error('Clear error:', error);
                });
        }
        
        function getStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateStatus(data.message, data.success);
                    if (data.success) {
                        document.getElementById('motorSlider').value = data.motor_speed || 0;
                        document.getElementById('servoSlider').value = data.servo_angle || 90;
                        updateMotorDisplay(data.motor_speed || 0);
                        updateServoDisplay(data.servo_angle || 90);
                    }
                })
                .catch(error => {
                    updateStatus('Status request failed', false);
                    console.error('Status error:', error);
                });
        }
        
        function emergencyStop() {
            sendMotor(0);
            // Don't auto-center servo on emergency stop - keep current position
            // Reset motor slider to center
            document.getElementById('motorSlider').value = 0;
            updateMotorDisplay(0);
            updateStatus('Emergency stop activated!', true);
        }
        
        // Allow Enter key to send message
        document.getElementById('messageInput').addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                sendMessage();
            }
        });
        
        // Prevent keyboard controls when typing in input field
        document.addEventListener('keydown', (event) => {
            // Only prevent keyboard shortcuts if not typing in an input field
            if (event.target.tagName.toLowerCase() === 'input') {
                return; // Allow normal typing in input fields
            }
            
            // Disable all keyboard shortcuts to prevent conflicts
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'W', 's', 'S', 'a', 'A', 'd', 'D', ' '].includes(event.key)) {
                event.preventDefault();
            }
        });
        
        // Initial status check
        setTimeout(getStatus, 500);
    </script>
</body>
</html>'''
    
    response = Response(html_content)
    response.headers['Content-Type'] = 'text/html'
    return response

# ========== API Endpoints with Fixed Response Format ==========

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