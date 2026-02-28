import requests

PICO_IP = "192.168.178.30"
BASE_URL = f"http://{PICO_IP}:5000"


class PicarClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()

    def _get(self, path):
        response = self.session.get(f"{self.base_url}{path}", timeout=5)
        response.raise_for_status()
        return response.json()

    def _post(self, path, data):
        response = self.session.post(f"{self.base_url}{path}", json=data, timeout=5)
        response.raise_for_status()
        return response.json()

    def set_motor(self, speed: int) -> dict:
        """Set motor speed. Range: -100 (full reverse) to 100 (full forward), 0 = stop."""
        speed = max(-100, min(100, int(speed)))
        return self._get(f"/api/motor/{speed}")

    def set_servo(self, angle: int) -> dict:
        """Set servo angle. Range: 0 to 180, 90 = centre."""
        angle = max(0, min(180, int(angle)))
        return self._get(f"/api/servo/{angle}")

    def send_text(self, text: str) -> dict:
        """Display a message on the OLED screen."""
        return self._post("/api/text", {"text": text})

    def clear_display(self) -> dict:
        """Clear the OLED display."""
        return self._post("/api/text", {"text": ""})

    def status(self) -> dict:
        """Get current motor speed and servo angle."""
        return self._get("/api/status")

    def get_sensors(self) -> dict:
        """Get IR sensor state (left_front, right_front, timestamp)."""
        return self._get("/api/sensors")

    def stop(self) -> dict:
        """Stop the motor immediately."""
        return self.set_motor(0)

    def centre(self) -> dict:
        """Centre the steering servo."""
        return self.set_servo(90)


def main():
    client = PicarClient()

    print(f"Connecting to Picar at {BASE_URL}...")
    try:
        s = client.status()
        print(f"Connected. Motor: {s['motor_speed']}, Servo: {s['servo_angle']}°")
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to {BASE_URL}. Is the Pico running?")
        return

    def fmt_sensors(r):
        l = "BLOCKED" if r.get("left_front") else "clear"
        ri = "BLOCKED" if r.get("right_front") else "clear"
        return f"IR sensors — left: {l}, right: {ri}"

    commands = {
        "w": ("Forward",       lambda: client.set_motor(75)),
        "s": ("Reverse",       lambda: client.set_motor(-75)),
        "a": ("Left",          lambda: client.set_servo(45)),
        "d": ("Right",         lambda: client.set_servo(135)),
        "c": ("Centre servo",  lambda: client.centre()),
        " ": ("Stop",          lambda: client.stop()),
        "?": ("Status",        lambda: client.status()),
        "i": ("IR sensors",    lambda: client.get_sensors()),
        "q": ("Quit",          None),
    }

    print("\nControls:")
    for key, (label, _) in commands.items():
        display_key = "SPACE" if key == " " else key
        print(f"  {display_key} — {label}")
    print()

    import sys, tty, termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = sys.stdin.read(1)
            if key not in commands:
                continue
            label, action = commands[key]
            if action is None:
                client.stop()
                print("\r\nStopped. Goodbye.")
                break
            result = action()
            if key == "i":
                print(f"\r{fmt_sensors(result)}")
            else:
                print(f"\r{label}: {result.get('message', '')}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
