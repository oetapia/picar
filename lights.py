import machine
import display
import time

# Light control pins
light_back = machine.Pin(2, machine.Pin.OUT)
light_front = machine.Pin(5, machine.Pin.OUT)

light_back.off()
light_front.off()



def update_lights(status):
    if status == "front":
        light_back.off()
        light_front.on()
        display_light_status("front")

    elif status == "back":
        light_back.on()
        light_front.off()
        display_light_status("back")
    elif status == "off":
            light_back.off()
            light_front.off()
            display_light_status("off")
    

    


def display_light_status(message):
    display.update_display(header="Light Status", text=message)
    print(f"Lights: {message}")

# ========== Start Everything ==========
if __name__ == '__main__':
    update_lights("front")
    time.sleep(3)
    update_lights("back")
    time.sleep(3)
    update_lights("off")