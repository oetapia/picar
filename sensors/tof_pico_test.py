"""
tof_pico_test.py - VL53L0X diagnostic for Raspberry Pi Pico

Copy both this file and vl53l0x_mp.py to the Pico, then run:
    mpremote run tof_pico_test.py
or open in Thonny and press Run.

Wiring (Pico default I2C-0):
    SDA -> GP4   SCL -> GP5   VCC -> 3V3   GND -> GND
"""

import machine
import time
from vl53l0x_mp import VL53L0X, VL53L0XError

SDA_PIN = 0
SCL_PIN = 1
# SoftI2C is more forgiving than hardware I2C for the VL53L0X:
# it issues a clean STOP between every write/read and is less strict
# about clock timing than the RP2040 hardware I2C peripheral.
# 100kHz avoids edge cases with weak pull-ups or long wires.
I2C_FREQ = 100_000
VL53_ADDR = 0x29


def scan_i2c(i2c):
    devices = i2c.scan()
    return devices


def print_bar(dist_cm, width=40):
    filled = max(0, min(width, int(dist_cm / 3)))
    bar = "#" * filled + "-" * (width - filled)
    print("\r  {:6.1f} cm  |{}|".format(dist_cm, bar), end="")


def main():
    print("=" * 52)
    print("  VL53L0X Pico Diagnostic")
    print("=" * 52)

    # Step 1 - I2C scan
    print("\n[1] I2C scan (SDA=GP{}, SCL=GP{})...".format(SDA_PIN, SCL_PIN))
    i2c = machine.SoftI2C(sda=machine.Pin(SDA_PIN),
                          scl=machine.Pin(SCL_PIN),
                          freq=I2C_FREQ)
    time.sleep_ms(10)  # let bus settle after scan probing

    devices = scan_i2c(i2c)
    if not devices:
        print("  No I2C devices found.")
        print("  Check: SDA->GP{}, SCL->GP{}, 3V3, GND, pull-ups.".format(SDA_PIN, SCL_PIN))
        return

    print("  Found {} device(s): {}".format(
        len(devices), ", ".join("0x{:02X}".format(a) for a in devices)))

    if VL53_ADDR not in devices:
        print("  VL53L0X not at 0x{:02X} - check wiring.".format(VL53_ADDR))
        return

    # Step 2 - model check
    print("\n[2] Checking model ID at 0x{:02X}...".format(VL53_ADDR))
    tof = VL53L0X(i2c, addr=VL53_ADDR)
    if tof.check_id():
        print("  Model ID: 0xEE  =>  VL53L0X confirmed")
    else:
        raw = i2c.readfrom_mem(VL53_ADDR, 0xC0, 1)[0]
        print("  Unexpected model ID: 0x{:02X}".format(raw))
        print("  Expected 0xEE for VL53L0X - check sensor type.")
        return

    # Step 3 - init and stream
    print("\n[3] Initializing (SPAD cal + ref cal)...")
    try:
        tof.init()
    except VL53L0XError as e:
        print("  Init error:", e)
        return
    except Exception as e:
        print("  Unexpected error:", e)
        return

    print("  OK - streaming readings, Ctrl+C to stop.\n")

    try:
        while True:
            dist = tof.read_cm()
            if dist is None:
                print("\r  Out of range          ", end="")
            else:
                print_bar(dist)
            time.sleep_ms(100)
    except KeyboardInterrupt:
        print("\n\nDone.")


main()
