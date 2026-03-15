"""
HC-SR04 Ultrasonic Sensor Component
Provides async monitoring and cached state for API access
Mounted on the back of the car for rear obstacle detection

Hardware Setup:
- Trigger: GP14
- Echo: GP15
- VCC: 5V
- GND: GND
"""

import machine
import time
import uasyncio as asyncio

# ========== HC-SR04 Configuration ==========
TRIGGER_PIN = 14  # GP14
ECHO_PIN = 15     # GP15
MAX_DISTANCE_CM = 400  # Maximum measurable distance
TIMEOUT_US = int(MAX_DISTANCE_CM * 58.8)  # Timeout for pulse measurement

# Speed of sound: 343 m/s = 0.0343 cm/μs
SPEED_OF_SOUND = 0.0343

# Measurement validation range
MIN_DISTANCE_CM = 2
MAX_DISTANCE_CM = 400


class HCSR04Sensor:
    """HC-SR04 ultrasonic distance sensor driver for MicroPython."""
    
    def __init__(self, trigger_pin=TRIGGER_PIN, echo_pin=ECHO_PIN):
        """
        Initialize HC-SR04 sensor.
        
        Args:
            trigger_pin: GPIO pin for trigger signal
            echo_pin: GPIO pin for echo signal
        """
        self.trigger = machine.Pin(trigger_pin, machine.Pin.OUT)
        self.echo = machine.Pin(echo_pin, machine.Pin.IN)
        self.timeout_us = TIMEOUT_US
        self.initialized = False
    
    def init(self, verbose=True):
        """
        Initialize the sensor.
        
        Args:
            verbose: Print initialization status
            
        Returns:
            bool: True if initialized successfully
        """
        try:
            # Ensure trigger starts low
            self.trigger.low()
            time.sleep_ms(100)
            
            self.initialized = True
            
            if verbose:
                print("HC-SR04: initialized successfully")
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"HC-SR04: initialization error: {e}")
            return False
    
    def measure_distance_cm(self):
        """
        Measure distance using ultrasonic pulse.
        
        Returns:
            float: Distance in centimeters, or None if measurement failed
        """
        if not self.initialized:
            return None
        
        try:
            # Ensure trigger is low
            self.trigger.low()
            time.sleep_us(2)
            
            # Send 10μs pulse to trigger
            self.trigger.high()
            time.sleep_us(10)
            self.trigger.low()
            
            # Measure the duration of the echo pulse (in microseconds)
            pulse_time = machine.time_pulse_us(self.echo, 1, self.timeout_us)
            
            if pulse_time < 0:
                # Timeout occurred (no echo received)
                return None
            
            # Calculate distance: distance = (pulse_time * speed_of_sound) / 2
            # Divide by 2 because sound travels to object and back
            distance_cm = (pulse_time * SPEED_OF_SOUND) / 2
            
            # Validate measurement range
            if MIN_DISTANCE_CM <= distance_cm <= MAX_DISTANCE_CM:
                return distance_cm
            else:
                return None
                
        except Exception as e:
            print(f"HC-SR04: measurement error: {e}")
            return None
    
    def get_status(self):
        """
        Get sensor status.
        
        Returns:
            dict: Status information
        """
        return {
            'initialized': self.initialized,
            'trigger_pin': TRIGGER_PIN,
            'echo_pin': ECHO_PIN,
            'max_range_cm': MAX_DISTANCE_CM
        }


# -------------------------
# Global sensor instance
# -------------------------
_sensor = None
_sensor_available = False

# -------------------------
# Cached state (updated by monitor)
# -------------------------
_state = {
    "distance_cm": None,
    "available": False,
    "in_range": False,  # True if object detected within range
    "timestamp": 0
}


# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    """Continuously read HC-SR04 sensor and update cached state."""
    global _sensor, _sensor_available
    
    print("HC-SR04 monitor: initializing sensor...")
    
    # Initialize sensor
    try:
        _sensor = HCSR04Sensor(trigger_pin=TRIGGER_PIN, echo_pin=ECHO_PIN)
        
        if _sensor.init(verbose=True):
            _sensor_available = True
            _state["available"] = True
            print("HC-SR04 monitor: sensor initialized successfully")
        else:
            print("HC-SR04 monitor: sensor init failed")
            _state["available"] = False
    except Exception as e:
        print(f"HC-SR04 monitor: initialization error: {e}")
        _state["available"] = False
    
    # Monitor loop
    print("HC-SR04 monitor started")
    while True:
        if _sensor_available and _sensor:
            try:
                # Measure distance
                distance = _sensor.measure_distance_cm()
                
                if distance is not None:
                    _state["distance_cm"] = round(distance, 1)
                    _state["in_range"] = True
                else:
                    _state["distance_cm"] = None
                    _state["in_range"] = False
                
                _state["timestamp"] = time.time()
                
            except Exception as e:
                print(f"HC-SR04 monitor: read error: {e}")
                _state["distance_cm"] = None
                _state["in_range"] = False
        
        # Update every 200ms (5 Hz) - don't go faster, sensor needs recovery time
        await asyncio.sleep_ms(200)


# -------------------------
# State accessor for API
# -------------------------
def get_state():
    """Get current cached HC-SR04 sensor state."""
    return dict(_state)


# -------------------------
# Self-test (run directly)
# -------------------------
if __name__ == "__main__":
    async def _self_test():
        print("=== HC-SR04 Self-Test ===")
        asyncio.create_task(monitor())
        
        # Wait for initialization
        await asyncio.sleep(2)
        
        # Read for 10 seconds
        for i in range(20):
            await asyncio.sleep_ms(500)
            s = get_state()
            
            if s["available"]:
                distance = s['distance_cm']
                
                if distance:
                    print(f"[{i+1:02d}] Distance: {distance:.1f} cm (rear obstacle detected)")
                else:
                    print(f"[{i+1:02d}] No obstacle detected or out of range")
            else:
                print(f"[{i+1:02d}] Sensor not available")
        
        print("=== Self-Test Complete ===")

    asyncio.run(_self_test())
