"""
Lights Component
Provides async monitoring and cached state for API access
"""

import machine
import time
import uasyncio as asyncio

# ========== Light Configuration ==========
LIGHT_FRONT_PIN = 5      # GP5
LIGHT_BACK_PIN = 2       # GP2

# Light control pins
light_front = machine.Pin(LIGHT_FRONT_PIN, machine.Pin.OUT)
light_back = machine.Pin(LIGHT_BACK_PIN, machine.Pin.OUT)

# Initialize lights off
light_front.off()
light_back.off()

# -------------------------
# Cached state
# -------------------------
_state = {
    "front": False,
    "back": False,
    "both": False,
    "status": "off",
    "available": True,
    "timestamp": 0
}


# -------------------------
# Light control functions
# -------------------------
def set_lights(front=None, back=None):
    """
    Set light states.
    
    Args:
        front: True/False to set front light, None to leave unchanged
        back: True/False to set back light, None to leave unchanged
    """
    global _state
    
    if front is not None:
        if front:
            light_front.on()
            _state["front"] = True
        else:
            light_front.off()
            _state["front"] = False
    
    if back is not None:
        if back:
            light_back.on()
            _state["back"] = True
        else:
            light_back.off()
            _state["back"] = False
    
    # Update combined status
    if _state["front"] and _state["back"]:
        _state["status"] = "both"
        _state["both"] = True
    elif _state["front"]:
        _state["status"] = "front"
        _state["both"] = False
    elif _state["back"]:
        _state["status"] = "back"
        _state["both"] = False
    else:
        _state["status"] = "off"
        _state["both"] = False
    
    _state["timestamp"] = time.time()
    
    return _state["status"]


def lights_off():
    """Turn off all lights."""
    return set_lights(front=False, back=False)


def lights_front():
    """Turn on front light, turn off back light."""
    return set_lights(front=True, back=False)


def lights_back():
    """Turn on back light, turn off front light."""
    return set_lights(front=False, back=True)


def lights_both():
    """Turn on both lights."""
    return set_lights(front=True, back=True)


# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    """Monitor loop for lights (minimal - lights are hardware controlled)."""
    print("Lights monitor started")
    
    # Lights don't need active monitoring like sensors
    # This task exists for consistency with sensor pattern
    # and could be used for features like blinking, patterns, etc.
    
    while True:
        # Update timestamp periodically to show system is alive
        _state["timestamp"] = time.time()
        await asyncio.sleep(1)


# -------------------------
# State accessor for API
# -------------------------
def get_state():
    """Get current cached light state."""
    return dict(_state)


# -------------------------
# Self-test (run directly)
# -------------------------
if __name__ == '__main__':
    async def _self_test():
        print("=== Lights Self-Test ===")
        asyncio.create_task(monitor())
        
        await asyncio.sleep(1)
        
        print("Testing front lights...")
        lights_front()
        print(f"State: {get_state()}")
        await asyncio.sleep(2)
        
        print("Testing back lights...")
        lights_back()
        print(f"State: {get_state()}")
        await asyncio.sleep(2)
        
        print("Testing both lights...")
        lights_both()
        print(f"State: {get_state()}")
        await asyncio.sleep(2)
        
        print("Turning off lights...")
        lights_off()
        print(f"State: {get_state()}")
        await asyncio.sleep(1)
        
        print("=== Self-Test Complete ===")
    
    asyncio.run(_self_test())
