from machine import Pin
import time
import uasyncio as asyncio

# -------------------------
# IR sensor setup
# -------------------------
ir_left  = Pin(3, Pin.IN, Pin.PULL_UP)   # left front
ir_right = Pin(7, Pin.IN, Pin.PULL_UP)   # right front

print("IR sensors initialized (left: pin 3, right: pin 7)")

# -------------------------
# Cached state (updated by monitor)
# -------------------------
_state = {
    "left_front":  False,
    "right_front": False,
    "timestamp":   0
}

# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    print("IR sensor monitor started")
    while True:
        left  = ir_left.value() == 0
        right = ir_right.value() == 0

        # Log only on rising edge (beam just broken)
        if left and not _state["left_front"]:
            print("IR: left front beam broken")
        if right and not _state["right_front"]:
            print("IR: right front beam broken")

        _state["left_front"]  = left
        _state["right_front"] = right
        _state["timestamp"]   = time.time()

        await asyncio.sleep_ms(50)

# -------------------------
# State accessor for API
# -------------------------
def get_state():
    return dict(_state)
