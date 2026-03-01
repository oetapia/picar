
from machine import Pin, I2C
import ssd1306
import time

# Use the working pins
i2c = I2C(1, scl=Pin(19), sda=Pin(18), freq=400000)

# 0x3C is detected automatically, so no need to specify
oled = ssd1306.SSD1306_I2C(128, 32, i2c)

oled.fill(0)                     # Clear screen
oled.text("I2C Works!", 0, 0)
oled.text("Addr: 0x3C", 0, 10)
oled.show()
