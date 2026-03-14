# minimal_vl53l1x_test.py
# Raspberry Pi Pico + VL53L1X minimal test (MicroPython)
# Only checks if the sensor responds correctly

from machine import I2C, Pin
import time
import vl53l1x

# Pico I2C pins
SDA_PIN = 6
SCL_PIN = 7

# Initialize I2C bus
i2c = I2C(1, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100_000)

# Scan the bus
devices = i2c.scan()
print("I2C devices found:", devices)

# Check for VL53L1X at default address 0x29
if 0x29 not in devices:
    print("VL53L1X not found. Check VIN/XSHUT and wiring!")
else:
    print("VL53L1X detected at 0x29.")

# Initialize sensor
sensor = vl53l1x.VL53L1X(i2c)

# Try a single measurement
sensor.start_ranging()  # Default mode
time.sleep(0.05)        # Give it 50 ms to measure

distance = sensor.get_distance()
print("Distance reading:", distance, "mm")

sensor.stop_ranging()
print("Test complete.")
