from machine import Pin
import time

ir_sensor = Pin(7, Pin.IN, Pin.PULL_UP)

print("IR break-beam test started...")

while True:
    if ir_sensor.value() == 0:
        print("Beam broken!")
        time.sleep(0.2)  # prevent spam
