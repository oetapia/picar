from machine import Pin
import time
import uasyncio as asyncio

# -------------------------
# IR sensor setup
# -------------------------
ir_left_front  = Pin(3, Pin.IN, Pin.PULL_UP)   # left front
ir_right_front = Pin(7, Pin.IN, Pin.PULL_UP)   # right front
ir_left_back   = Pin(8, Pin.IN, Pin.PULL_UP)   # left back
ir_right_back  = Pin(4, Pin.IN, Pin.PULL_UP)   # right back

print("IR sensors initialized (left_front: pin 3, right_front: pin 7, left_back: pin 4, right_back: pin 8)")

# -------------------------
# Cached state (updated by monitor)
# -------------------------
_state = {
    "left_front":  False,
    "right_front": False,
    "left_back":   False,
    "right_back":  False,
    "timestamp":   0
}

# -------------------------
# Background monitor loop
# -------------------------
async def monitor():
    print("IR sensor monitor started")
    while True:
        left_front  = ir_left_front.value() == 0
        right_front = ir_right_front.value() == 0
        left_back   = ir_left_back.value() == 0
        right_back  = ir_right_back.value() == 0

        # Log only on rising edge (beam just broken)
        if left_front  and not _state["left_front"]:
            print("IR: left front beam broken")
        if right_front and not _state["right_front"]:
            print("IR: right front beam broken")
        if left_back   and not _state["left_back"]:
            print("IR: left back beam broken")
        if right_back  and not _state["right_back"]:
            print("IR: right back beam broken")

        _state["left_front"]  = left_front
        _state["right_front"] = right_front
        _state["left_back"]   = left_back
        _state["right_back"]  = right_back
        _state["timestamp"]   = time.time()

        await asyncio.sleep_ms(50)

# -------------------------
# State accessor for API
# -------------------------
def get_state():
    return dict(_state)

# -------------------------
# Self-test (run directly)
# -------------------------
if __name__ == "__main__":
    async def _self_test():
        print("=== IR Sensor Self-Test ===")
        asyncio.create_task(monitor())
        for _ in range(20):
            await asyncio.sleep_ms(500)
            s = get_state()
            print("left_front={}  right_front={}  left_back={}  right_back={}".format(
                s["left_front"], s["right_front"], s["left_back"], s["right_back"]
            ))
        print("=== Self-Test Complete ===")

    asyncio.run(_self_test())
