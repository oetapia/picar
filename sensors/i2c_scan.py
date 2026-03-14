"""
Simple I2C bus scanner for Raspberry Pi Pico (MicroPython)
Prints all detected device addresses on the bus.
"""

from machine import I2C, Pin

SDA_PIN = 20
SCL_PIN = 21
I2C_ID  = 0

i2c = I2C(I2C_ID, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400_000)

devices = i2c.scan()

if devices:
    print("I2C devices found: {}".format(len(devices)))
    for addr in devices:
        print("  0x{:02X} ({})".format(addr, addr))
else:
    print("No I2C devices found — check wiring and power.")
