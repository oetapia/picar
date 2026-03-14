"""
vl53l0x_mp.py - Pure MicroPython VL53L0X driver for Raspberry Pi Pico

Copy this file to your Pico (e.g. with mpremote or Thonny).

Wiring (Pico default I2C-0):
    SDA -> GP0
    SCL -> GP1
    VCC -> 3V3
    GND -> GND

Usage:
    from vl53l0x_mp import VL53L0X
    import machine

    i2c = machine.SoftI2C(sda=machine.Pin(0), scl=machine.Pin(1), freq=100_000)
    tof = VL53L0X(i2c)
    tof.init()
    print(tof.read_mm(), "mm")
"""

import time

_ADDR = 0x29

# --- Registers ---------------------------------------------------------------
_R_SYSRANGE_START                              = 0x00
_R_SYSTEM_SEQUENCE_CONFIG                      = 0x01
_R_SYSTEM_INTERMEASUREMENT_PERIOD              = 0x04
_R_SYSTEM_INTERRUPT_CONFIG                     = 0x0A
_R_SYSTEM_INTERRUPT_CLEAR                      = 0x0B
_R_RESULT_INTERRUPT_STATUS                     = 0x13
_R_RESULT_RANGE_STATUS                         = 0x14
_R_I2C_SLAVE_DEVICE_ADDRESS                    = 0x8A
_R_MSRC_CONFIG_CONTROL                         = 0x60
_R_FINAL_RANGE_CONFIG_MIN_SNR                  = 0x67
_R_FINAL_RANGE_CONFIG_VALID_PHASE_LOW          = 0x47
_R_FINAL_RANGE_CONFIG_VALID_PHASE_HIGH         = 0x48
_R_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT = 0x44
_R_PRE_RANGE_CONFIG_VCSEL_PERIOD               = 0x50
_R_PRE_RANGE_CONFIG_TIMEOUT_MACROP_HI          = 0x51
_R_PRE_RANGE_CONFIG_TIMEOUT_MACROP_LO          = 0x52
_R_FINAL_RANGE_CONFIG_VCSEL_PERIOD             = 0x70
_R_FINAL_RANGE_CONFIG_TIMEOUT_MACROP_HI        = 0x71
_R_FINAL_RANGE_CONFIG_TIMEOUT_MACROP_LO        = 0x72
_R_GLOBAL_CONFIG_SPAD_ENABLES_REF_0            = 0xB0
_R_GLOBAL_CONFIG_REF_EN_START_SELECT           = 0xB6
_R_DYNAMIC_SPAD_NUM_REQUESTED_REF              = 0x4E
_R_DYNAMIC_SPAD_REF_EN_START_OFFSET            = 0x4F
_R_VHV_CONFIG_PAD_SCL_SDA_EXTSUP_HV           = 0x89
_R_GPIO_HV_MUX_ACTIVE_HIGH                     = 0x84
_R_OSC_CALIBRATE_VAL                           = 0xF8
_R_IDENTIFICATION_MODEL_ID                     = 0xC0

# ST-supplied tuning settings (from VL53L0X_api.c)
_TUNING = (
    (0xFF, 0x01), (0x00, 0x00), (0xFF, 0x00), (0x09, 0x00),
    (0x10, 0x00), (0x11, 0x00), (0x24, 0x01), (0x25, 0xFF),
    (0x75, 0x00), (0xFF, 0x01), (0x4E, 0x2C), (0x48, 0x00),
    (0x30, 0x20), (0xFF, 0x00), (0x30, 0x09), (0x54, 0x00),
    (0x31, 0x04), (0x32, 0x03), (0x40, 0x83), (0x46, 0x25),
    (0x60, 0x00), (0x27, 0x00), (0x50, 0x06), (0x51, 0x00),
    (0x52, 0x96), (0x56, 0x08), (0x57, 0x30), (0x61, 0x00),
    (0x62, 0x00), (0x64, 0x00), (0x65, 0x00), (0x66, 0xA0),
    (0xFF, 0x01), (0x22, 0x32), (0x47, 0x14), (0x49, 0xFF),
    (0x4A, 0x00), (0xFF, 0x00), (0x7A, 0x0A), (0x7B, 0x00),
    (0x78, 0x21), (0xFF, 0x01), (0x23, 0x34), (0x42, 0x00),
    (0x44, 0xFF), (0x45, 0x26), (0x46, 0x05), (0x40, 0x40),
    (0x0E, 0x06), (0x20, 0x1A), (0x43, 0x40), (0xFF, 0x00),
    (0x34, 0x03), (0x35, 0x44), (0xFF, 0x01), (0x31, 0x04),
    (0x4B, 0x09), (0x4C, 0x05), (0x4D, 0x04), (0xFF, 0x00),
    (0x44, 0x00), (0x45, 0x20), (0x47, 0x08), (0x48, 0x28),
    (0x67, 0x00), (0x70, 0x04), (0x71, 0x01), (0x72, 0xFE),
    (0x76, 0x00), (0x77, 0x00), (0xFF, 0x01), (0x0D, 0x01),
    (0xFF, 0x00), (0x80, 0x01), (0x01, 0xF8), (0xFF, 0x01),
    (0x8E, 0x01), (0x00, 0x01), (0xFF, 0x00), (0x80, 0x00),
)


class VL53L0XError(Exception):
    pass


class VL53L0X:
    def __init__(self, i2c, addr=_ADDR):
        self._i2c = i2c
        self._addr = addr
        self._stop_variable = 0

    # --- low-level I2C helpers -----------------------------------------------
    # VL53L0X needs a STOP between the address write and the data read.
    # readfrom_mem() uses a repeated-start which the sensor doesn't support,
    # so we use explicit writeto() / readfrom() pairs throughout.

    def _wr(self, reg, val):
        self._i2c.writeto(self._addr, bytes([reg, val]))

    def _rd(self, reg):
        self._i2c.writeto(self._addr, bytes([reg]))
        return self._i2c.readfrom(self._addr, 1)[0]

    def _rd2(self, reg):
        self._i2c.writeto(self._addr, bytes([reg]))
        d = self._i2c.readfrom(self._addr, 2)
        return (d[0] << 8) | d[1]

    def _rd_block(self, reg, n):
        self._i2c.writeto(self._addr, bytes([reg]))
        return self._i2c.readfrom(self._addr, n)

    def _wr_block(self, reg, data):
        self._i2c.writeto(self._addr, bytes([reg]) + bytes(data))

    # --- public API ----------------------------------------------------------

    def check_id(self):
        """Return True if model-ID register reads 0xEE (VL53L0X)."""
        return self._rd(_R_IDENTIFICATION_MODEL_ID) == 0xEE

    def init(self):
        """Full init: data-init, static-init, SPAD cal, ref cal, continuous mode."""
        if not self.check_id():
            raise VL53L0XError("VL53L0X not found at 0x{:02X}".format(self._addr))

        # --- data init ---
        # set 2v8 mode
        self._wr(_R_VHV_CONFIG_PAD_SCL_SDA_EXTSUP_HV,
                 self._rd(_R_VHV_CONFIG_PAD_SCL_SDA_EXTSUP_HV) | 0x01)

        # standard i2c mode
        self._wr(0x88, 0x00)
        self._wr(0x80, 0x01)
        self._wr(0xFF, 0x01)
        self._wr(0x00, 0x00)
        self._stop_variable = self._rd(0x91)
        self._wr(0x00, 0x01)
        self._wr(0xFF, 0x00)
        self._wr(0x80, 0x00)

        # disable SIGNAL_RATE_MSRC and SIGNAL_RATE_PRE_RANGE limit checks
        self._wr(_R_MSRC_CONFIG_CONTROL, self._rd(_R_MSRC_CONFIG_CONTROL) | 0x12)

        # set signal rate limit to 0.25 MCPS (Q9.7 fixed point)
        self._wr_block(_R_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT, [0x00, 0x20])

        self._wr(_R_SYSTEM_SEQUENCE_CONFIG, 0xFF)

        # --- SPAD init ---
        self._spad_init()

        # --- load tuning settings ---
        for reg, val in _TUNING:
            self._wr(reg, val)

        # set interrupt to "new sample ready"
        self._wr(_R_SYSTEM_INTERRUPT_CONFIG, 0x04)
        self._wr(_R_GPIO_HV_MUX_ACTIVE_HIGH,
                 (self._rd(_R_GPIO_HV_MUX_ACTIVE_HIGH) & ~0x10))
        self._wr(_R_SYSTEM_INTERRUPT_CLEAR, 0x01)

        # --- reference calibrations ---
        self._vhv_calibration()
        self._phase_calibration()

        # restore sequence config (all steps enabled)
        self._wr(_R_SYSTEM_SEQUENCE_CONFIG, 0xE8)

        # --- start continuous ranging ---
        self._wr(0x80, 0x01)
        self._wr(0xFF, 0x01)
        self._wr(0x00, 0x00)
        self._wr(0x91, self._stop_variable)
        self._wr(0x00, 0x01)
        self._wr(0xFF, 0x00)
        self._wr(0x80, 0x00)
        self._wr(_R_SYSRANGE_START, 0x02)  # 0x02 = continuous back-to-back

    def read_mm(self, timeout_ms=1000):
        """
        Block until a measurement is ready and return distance in mm.
        Returns 65535 on timeout or sensor error.
        """
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while (self._rd(_R_RESULT_INTERRUPT_STATUS) & 0x07) == 0:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return 65535

        # result starts at offset 10 within the range status block (2 bytes BE)
        data = self._rd_block(_R_RESULT_RANGE_STATUS, 12)
        self._wr(_R_SYSTEM_INTERRUPT_CLEAR, 0x01)

        raw = (data[10] << 8) | data[11]
        # 8190 / 8191 = out of range
        if raw in (8190, 8191):
            return 65535
        return raw

    def read_cm(self, timeout_ms=1000):
        mm = self.read_mm(timeout_ms)
        if mm == 65535:
            return None
        return mm / 10.0

    # --- internal calibration helpers ----------------------------------------

    def _spad_init(self):
        self._wr(0x80, 0x01)
        self._wr(0xFF, 0x01)
        self._wr(0x00, 0x00)
        self._wr(0xFF, 0x06)
        self._wr(0x83, self._rd(0x83) | 0x04)
        self._wr(0xFF, 0x07)
        self._wr(0x81, 0x01)
        self._wr(0x80, 0x01)
        self._wr(0x94, 0x6B)
        self._wr(0x83, 0x00)

        # wait for 0x83 != 0
        for _ in range(500):
            if self._rd(0x83) != 0x00:
                break
            time.sleep_ms(1)

        self._wr(0x83, 0x01)
        tmp = self._rd(0x92)
        spad_count = tmp & 0x7F
        is_aperture = bool((tmp >> 7) & 0x01)

        self._wr(0x81, 0x00)
        self._wr(0xFF, 0x06)
        self._wr(0x83, self._rd(0x83) & ~0x04)
        self._wr(0xFF, 0x01)
        self._wr(0x00, 0x01)
        self._wr(0xFF, 0x00)
        self._wr(0x80, 0x00)

        ref_spad_map = bytearray(self._rd_block(_R_GLOBAL_CONFIG_SPAD_ENABLES_REF_0, 6))

        self._wr(0xFF, 0x01)
        self._wr(_R_DYNAMIC_SPAD_REF_EN_START_OFFSET, 0x00)
        self._wr(_R_DYNAMIC_SPAD_NUM_REQUESTED_REF, 0x2C)
        self._wr(0xFF, 0x00)
        self._wr(_R_GLOBAL_CONFIG_REF_EN_START_SELECT, 0xB4)

        first_spad = 12 if is_aperture else 0
        spads_enabled = 0
        for i in range(48):
            if i < first_spad or spads_enabled == spad_count:
                ref_spad_map[i // 8] &= ~(1 << (i % 8))
            elif ref_spad_map[i // 8] & (1 << (i % 8)):
                spads_enabled += 1

        self._wr_block(_R_GLOBAL_CONFIG_SPAD_ENABLES_REF_0, ref_spad_map)

    def _vhv_calibration(self):
        self._wr(_R_SYSTEM_SEQUENCE_CONFIG, 0x01)
        self._wr(_R_SYSRANGE_START, 0x01)
        for _ in range(500):
            if (self._rd(_R_RESULT_INTERRUPT_STATUS) & 0x07) != 0:
                break
            time.sleep_ms(1)
        self._wr(_R_SYSTEM_INTERRUPT_CLEAR, 0x01)
        self._wr(_R_SYSRANGE_START, 0x00)

    def _phase_calibration(self):
        self._wr(_R_SYSTEM_SEQUENCE_CONFIG, 0x02)
        self._wr(_R_SYSRANGE_START, 0x01)
        for _ in range(500):
            if (self._rd(_R_RESULT_INTERRUPT_STATUS) & 0x07) != 0:
                break
            time.sleep_ms(1)
        self._wr(_R_SYSTEM_INTERRUPT_CLEAR, 0x01)
        self._wr(_R_SYSRANGE_START, 0x00)
