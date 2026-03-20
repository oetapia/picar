import requests
import time
import sys
import threading
from pathlib import Path

# Import config from parent directory
try:
    # Try importing from parent directory (when run from anywhere)
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    import config
    PICAR_IP = config.car_ip
except (ImportError, AttributeError):
    # Fallback to hardcoded IP if config.py not found
    print("⚠️  Warning: Could not import config.py, using default IP")
    print("   Create config.py from config.example.py template")
    PICAR_IP = "192.168.178.30"

BASE_URL = f"http://{PICAR_IP}:5000"


class PicarClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.auto_lights = True  # Automatic light control based on movement
        self._last_light_target: str = ""  # debounce: skip if state unchanged

    def _get(self, path):
        response = self.session.get(f"{self.base_url}{path}", timeout=5)
        response.raise_for_status()
        return response.json()

    def _post(self, path, data):
        response = self.session.post(f"{self.base_url}{path}", json=data, timeout=5)
        response.raise_for_status()
        return response.json()

    # ========== Motor Control ==========
    def set_motor(self, speed: int) -> dict:
        """
        Set motor speed. Range: -100 (full reverse) to 100 (full forward), 0 = stop.
        Automatically controls lights based on direction if auto_lights is enabled.
        """
        speed = max(-100, min(100, int(speed)))
        result = self._get(f"/api/motor/{speed}")
        
        # Automatic light control based on movement direction (non-blocking).
        # Uses requests.get directly (not self.session) to avoid thread-safety issues
        # when the navigation loop is concurrently using the session.
        if self.auto_lights:
            if speed > 0:
                target = "front"
            elif speed < 0:
                target = "back"
            else:
                target = "off"
            if target != self._last_light_target:
                self._last_light_target = target
                url = f"{self.base_url}/api/lights/{target}"
                threading.Thread(
                    target=lambda: requests.get(url, timeout=5),
                    daemon=True
                ).start()
        
        return result

    # ========== Servo Control ==========
    def set_servo(self, angle: int) -> dict:
        """Set servo angle. Range: 0 to 180, 90 = centre."""
        angle = max(0, min(180, int(angle)))
        return self._get(f"/api/servo/{angle}")

    # ========== Display Control ==========
    def send_text(self, text: str) -> dict:
        """Display a message on the OLED screen."""
        return self._post("/api/text", {"text": text})

    def clear_display(self) -> dict:
        """Clear the OLED display."""
        return self._post("/api/text", {"text": ""})

    # ========== Status ==========
    def status(self) -> dict:
        """Get current motor speed and servo angle."""
        return self._get("/api/status")

    # ========== Lights Control ==========
    def get_lights(self) -> dict:
        """
        Get current light status.
        
        Returns:
            dict with 'front' (bool), 'back' (bool), 'status' (str: 'off'/'front'/'back'/'both')
        """
        return self._get("/api/lights")

    def set_lights(self, status: str) -> dict:
        """
        Control lights.
        
        Args:
            status: 'front', 'back', 'both', or 'off'
        
        Returns:
            dict with success status and current light state
        """
        return self._get(f"/api/lights/{status}")

    def lights_off(self) -> dict:
        """Turn off all lights."""
        return self.set_lights("off")

    def lights_front(self) -> dict:
        """Turn on front lights only."""
        return self.set_lights("front")

    def lights_back(self) -> dict:
        """Turn on back lights only."""
        return self.set_lights("back")

    def lights_both(self) -> dict:
        """Turn on both front and back lights."""
        return self.set_lights("both")

    # ========== Sensors ==========
    def get_sensors(self) -> dict:
        """
        Get IR sensor state (left_front, right_front, left_back, right_back, timestamp).
        DEPRECATED: This endpoint may not be available in current firmware.
        """
        return self._get("/api/sensors")

    def get_accelerometer(self) -> dict:
        """
        Get MPU-6050 accelerometer/gyroscope data.
        
        Returns:
            dict with acceleration (x,y,z in g), gyroscope (x,y,z in deg/s),
            tilt (pitch, roll in degrees), orientation (str), timestamp
        """
        return self._get("/api/accelerometer")

    def get_tof(self) -> dict:
        """
        Get dual VL53L0X Time-of-Flight distance sensors (front left and right).
        
        Returns:
            dict with left_distance_cm, right_distance_cm, and if both available:
            angle data (angle_degrees, orientation, wall_distance_cm)
        """
        return self._get("/api/tof")

    def get_ultrasonic(self) -> dict:
        """
        Get HC-SR04 ultrasonic distance sensor (rear).
        
        Returns:
            dict with distance_cm (rear obstacle distance), in_range (bool), timestamp
        """
        return self._get("/api/ultrasonic")

    def get_all_sensors(self) -> dict:
        """
        Get comprehensive sensor data from all available sensors.
        
        Returns:
            dict with 'accelerometer', 'tof', 'ultrasonic' keys containing sensor data
        """
        sensors = {}
        
        try:
            sensors['accelerometer'] = self.get_accelerometer()
        except Exception as e:
            sensors['accelerometer'] = {'available': False, 'error': str(e)}
        
        try:
            sensors['tof'] = self.get_tof()
        except Exception as e:
            sensors['tof'] = {'available': False, 'error': str(e)}
        
        try:
            sensors['ultrasonic'] = self.get_ultrasonic()
        except Exception as e:
            sensors['ultrasonic'] = {'available': False, 'error': str(e)}
        
        return sensors

    # ========== Convenience Methods ==========
    def stop(self) -> dict:
        """Stop the motor immediately and turn off lights if auto mode."""
        return self.set_motor(0)

    def centre(self) -> dict:
        """Centre the steering servo."""
        return self.set_servo(90)


# ========== Sensor Formatters ==========
def format_accelerometer(data):
    """Format accelerometer data for display."""
    if not data.get('success'):
        return "Accelerometer: Not available"
    
    tilt = data.get('tilt', {})
    orientation = data.get('orientation', 'unknown')
    pitch = tilt.get('pitch', 0)
    roll = tilt.get('roll', 0)
    
    return f"Accel: Pitch={pitch:+.1f}° Roll={roll:+.1f}° [{orientation}]"


def format_tof(data):
    """Format dual ToF sensor data for display."""
    if not data.get('success'):
        return "ToF: Not available"
    
    left = data.get('left_distance_cm')
    right = data.get('right_distance_cm')
    
    left_str = f"{left:.1f}cm" if left else "---"
    right_str = f"{right:.1f}cm" if right else "---"
    
    result = f"ToF Front: L={left_str} R={right_str}"
    
    # Add angle information if available
    if data.get('angle'):
        angle_data = data['angle']
        angle = angle_data['angle_degrees']
        orientation = angle_data['orientation']
        result += f" | {angle:+.1f}° [{orientation}]"
    
    return result


def format_ultrasonic(data):
    """Format ultrasonic sensor data for display."""
    if not data.get('success'):
        return "Ultrasonic: Not available"
    
    if data.get('in_range'):
        distance = data.get('distance_cm', 0)
        warning = " ⚠️ CLOSE!" if distance < 30 else ""
        return f"Ultrasonic Rear: {distance:.1f}cm{warning}"
    else:
        return "Ultrasonic Rear: All clear"


def format_lights(data):
    """Format lights status for display."""
    if not data.get('success'):
        return "Lights: Not available"
    
    status = data.get('status', 'unknown')
    return f"Lights: {status}"


def main():
    client = PicarClient()

    print(f"Connecting to Picar at {BASE_URL}...")
    try:
        s = client.status()
        print(f"✓ Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except requests.exceptions.ConnectionError:
        print(f"✗ Could not connect to {BASE_URL}. Is the Pico running?")
        return

    commands = {
        # Movement
        "w": ("Forward",           lambda: client.set_motor(75)),
        "s": ("Reverse",           lambda: client.set_motor(-75)),
        "a": ("Left",              lambda: client.set_servo(45)),
        "d": ("Right",             lambda: client.set_servo(135)),
        "c": ("Centre servo",      lambda: client.centre()),
        " ": ("Stop",              lambda: client.stop()),
        
        # Lights
        "f": ("Lights front",      lambda: client.lights_front()),
        "b": ("Lights back",       lambda: client.lights_back()),
        "l": ("Lights both",       lambda: client.lights_both()),
        "o": ("Lights off",        lambda: client.lights_off()),
        "t": ("Toggle auto lights", lambda: toggle_auto_lights()),
        
        # Status & Sensors
        "?": ("Status",            lambda: client.status()),
        "1": ("Accelerometer",     lambda: client.get_accelerometer()),
        "2": ("ToF sensors",       lambda: client.get_tof()),
        "3": ("Ultrasonic",        lambda: client.get_ultrasonic()),
        "4": ("All sensors",       lambda: client.get_all_sensors()),
        "5": ("Lights status",     lambda: client.get_lights()),
        
        # Exit
        "q": ("Quit",              None),
    }

    def toggle_auto_lights():
        client.auto_lights = not client.auto_lights
        return {"message": f"Auto lights: {'ON' if client.auto_lights else 'OFF'}"}

    print("\n" + "="*70)
    print("PICAR REMOTE CONTROL")
    print("="*70)
    print("\nMovement Controls:")
    print("  W/S       — Forward / Reverse")
    print("  A/D       — Steer Left / Right")
    print("  C         — Centre steering")
    print("  SPACE     — Stop")
    
    print("\nLights Controls:")
    print("  F         — Front lights ON")
    print("  B         — Back lights ON")
    print("  L         — Both lights ON")
    print("  O         — Lights OFF")
    print(f"  T         — Toggle auto lights [Currently: {'ON' if client.auto_lights else 'OFF'}]")
    
    print("\nSensor Information:")
    print("  1         — Accelerometer (MPU-6050: tilt, orientation)")
    print("  2         — ToF sensors (VL53L0X: front distances & angle)")
    print("  3         — Ultrasonic (HC-SR04: rear distance)")
    print("  4         — All sensors")
    print("  5         — Lights status")
    
    print("\nOther:")
    print("  ?         — Status (motor, servo)")
    print("  Q         — Quit")
    print("="*70)
    
    if client.auto_lights:
        print("\n💡 Auto lights mode: Lights will turn on automatically when moving")
    
    print("\nReady for commands...\n")

    import sys, tty, termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = sys.stdin.read(1).lower()
            if key not in commands:
                continue
            
            label, action = commands[key]
            if action is None:
                client.stop()
                print("\r\n✓ Stopped. Goodbye.\n")
                break
            
            try:
                result = action()
                
                # Format output based on command type
                if key == "1":
                    print(f"\r{format_accelerometer(result)}")
                elif key == "2":
                    print(f"\r{format_tof(result)}")
                elif key == "3":
                    print(f"\r{format_ultrasonic(result)}")
                elif key == "4":
                    # All sensors - multi-line output
                    print("\r\n" + "="*70)
                    print(format_accelerometer(result.get('accelerometer', {})))
                    print(format_tof(result.get('tof', {})))
                    print(format_ultrasonic(result.get('ultrasonic', {})))
                    print("="*70)
                elif key == "5":
                    print(f"\r{format_lights(result)}")
                elif key == "t":
                    status = "ON" if client.auto_lights else "OFF"
                    print(f"\r💡 Auto lights: {status}")
                else:
                    msg = result.get('message', '')
                    print(f"\r{label}: {msg}" + " " * 20)  # Padding to clear line
            
            except requests.exceptions.RequestException as e:
                print(f"\r✗ Request failed: {e}")
            except Exception as e:
                print(f"\r✗ Error: {e}")
    
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
