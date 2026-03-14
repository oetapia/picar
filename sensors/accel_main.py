from machine import I2C, Pin
import time
from oled_screen import OLEDScreen

MPU6050_ADDR = 0x68
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B


def run():
    i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
    oled = OLEDScreen()._display

    # Wake MPU-6050 (clear sleep bit)
    i2c.writeto_mem(MPU6050_ADDR, PWR_MGMT_1, b'\x00')

    def read_accel():
        data = i2c.readfrom_mem(MPU6050_ADDR, ACCEL_XOUT_H, 6)
        def s16(hi, lo):
            v = (hi << 8) | lo
            return v - 65536 if v > 32767 else v
        ax = s16(data[0], data[1]) / 16384.0
        ay = s16(data[2], data[3]) / 16384.0
        az = s16(data[4], data[5]) / 16384.0
        return ax, ay, az

    def _g(v):
        return ("+" if v >= 0 else "") + f"{v:.2f}"

    while True:
        try:
            ax, ay, az = read_accel()
            oled.fill(0)
            oled.text("MPU-6050", 0, 0)
            oled.text(f"X:{_g(ax)} Y:{_g(ay)}", 0, 10)
            oled.text(f"Z:{_g(az)}", 0, 20)
            oled.show()
        except Exception as e:
            oled.fill(0)
            oled.text("I2C error", 0, 10)
            oled.show()
            print("Accel error:", e)
        time.sleep(0.1)
