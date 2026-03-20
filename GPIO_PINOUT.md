# PiCar GPIO Pinout — Raspberry Pi Pico W

Complete wiring reference for all components connected to the Pico W.

## Pin Assignment Summary

| GPIO | Function | Direction | Module | Notes |
|------|----------|-----------|--------|-------|
| 2 | Back light | OUT | `lights.py` | LED or MOSFET gate |
| 5 | Front light | OUT | `lights.py` | LED or MOSFET gate |
| 6 | Left ToF SDA | I/O | `sensors/dual_tof.py` | SoftI2C, VL53L0X (0x29) |
| 7 | Left ToF SCL | OUT | `sensors/dual_tof.py` | SoftI2C, 100 kHz |
| 8 | MPU-6050 SDA | I/O | `sensors/accelerometer.py` | I2C0, addr 0x68 |
| 9 | MPU-6050 SCL | OUT | `sensors/accelerometer.py` | I2C0, 400 kHz |
| 10 | Motor A PWM (PWMA) | PWM | `motor.py` / `motor2.py` | TB6612FNG, 1 kHz |
| 11 | Motor A IN1 (AIN1) | OUT | `motor.py` / `motor2.py` | Direction control |
| 12 | Motor A IN2 (AIN2) | OUT | `motor.py` / `motor2.py` | Direction control |
| 13 | Motor Driver STBY | OUT | `motor.py` / `motor2.py` | Shared standby (both channels) |
| 14 | HC-SR04 TRIG | OUT | `sensors/hcsr04.py` | Ultrasonic trigger pulse |
| 15 | HC-SR04 ECHO | IN | `sensors/hcsr04.py` | Ultrasonic echo return |
| 18 | OLED SDA | I/O | `display.py` | I2C1, SSD1306 128×32 |
| 19 | OLED SCL | OUT | `display.py` | I2C1 |
| 20 | Right ToF SDA | I/O | `sensors/dual_tof.py` | SoftI2C, VL53L0X (0x29) |
| 21 | Right ToF SCL | OUT | `sensors/dual_tof.py` | SoftI2C, 100 kHz |
| 22 | Servo PWM | PWM | `servo.py` | 50 Hz, steering |
| 26 | Motor B IN2 (BIN2) | OUT | `motor2.py` only | Direction control |
| 27 | Motor B IN1 (BIN1) | OUT | `motor2.py` only | Direction control |
| 28 | Motor B PWM (PWMB) | PWM | `motor2.py` only | TB6612FNG, 1 kHz |
| LED | Onboard LED | OUT | `main.py` | Activity indicator |

## I2C Buses

| Bus | SDA | SCL | Freq | Device | Address |
|-----|-----|-----|------|--------|---------|
| I2C0 (hw) | GP8 | GP9 | 400 kHz | MPU-6050 Accelerometer/Gyro | 0x68 |
| I2C1 (hw) | GP18 | GP19 | default | SSD1306 OLED 128×32 | 0x3C |
| SoftI2C | GP6 | GP7 | 100 kHz | VL53L0X ToF (left/front) | 0x29 |
| SoftI2C | GP20 | GP21 | 100 kHz | VL53L0X ToF (right/front) | 0x29 |

## Motor Driver — TB6612FNG

```
         TB6612FNG
  ┌─────────────────────┐
  │  PWMA ← GP10        │──→ AO1 ──┐
  │  AIN1 ← GP11        │──→ AO2 ──┴── Motor A
  │  AIN2 ← GP12        │
  │                      │
  │  STBY ← GP13        │  (shared enable)
  │                      │
  │  PWMB ← GP28        │──→ BO1 ──┐
  │  BIN1 ← GP27        │──→ BO2 ──┴── Motor B
  │  BIN2 ← GP26        │
  │                      │
  │  VM   ← Battery +   │
  │  VCC  ← 3.3V        │
  │  GND  ← GND         │
  └─────────────────────┘
```

**Motor A** is wired in both `motor.py` (single motor) and `motor2.py` (dual motor).
**Motor B** is only wired in `motor2.py` (dual motor mode).

### Direction Truth Table

| IN1 | IN2 | Function |
|-----|-----|----------|
| H | L | Forward (CW) |
| L | H | Reverse (CCW) |
| L | L | Coast / Stop |
| H | H | Brake |

## Power Rails

| Rail | Source | Consumers |
|------|--------|-----------|
| 3.3V | Pico W regulator | VL53L0X ×2, MPU-6050, SSD1306, TB6612 VCC, IR sensors |
| 5V | USB or battery | HC-SR04 VCC |
| VM | Battery pack | TB6612FNG motor power |
| GND | Common | All components |

## Unused / Available GPIOs

The following Pico W GPIOs are **not used** by the current configuration and are available for expansion:

- GP0, GP1, GP3, GP4
- GP16, GP17
- GP23, GP24, GP25 (GP25 may be LED on non-W Pico)

> **Note:** GP23, GP24, GP25, and GP29 have special functions on the Pico W (wireless SPI, VBUS sense). Avoid these for general I/O.

## Switching Between Single and Dual Motor

In `main.py`, change the import:

```python
# Single motor (original)
import motor

# Dual motor (uses both BO1/BO2 and AO1/AO2)
import motor2 as motor
```

No other code changes are needed — the API is identical.
