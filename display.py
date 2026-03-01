import machine
import ssd1306
import framebuf
import icons

display = None

def initialize_display():
    global display
    i2c = machine.I2C(1, sda=machine.Pin(18), scl=machine.Pin(19))
    devices = i2c.scan()
    print('I2C devices found:', devices)
    try:
        display = ssd1306.SSD1306_I2C(128, 32, i2c)
        display.fill(0)
        display.text('Screen on', 0, 0, 1)
        display.show()
        return True
    except Exception as e:
        print("OLED display not detected or initialization failed.")
        return False

def draw_icon(icon_data, x, y):
    size = len(icon_data)
    bytes_per_row = (size + 7) // 8
    byte_data = bytearray(bytes_per_row * size)
    for row in range(size):
        for col in range(size):
            if icon_data[row] & (1 << (size - 1 - col)):
                byte_data[row * bytes_per_row + col // 8] |= (1 << (7 - (col % 8)))
    fb = framebuf.FrameBuffer(byte_data, size, size, framebuf.MONO_HLSB)
    display.blit(fb, x, y)

def update_display(header=None, text=None, y_start=10, line_height=10, icon=None):
    if display is None:
        print("Display not initialized.")
        return

    display.fill(0)

    icon_data = getattr(icons, icon, None) if icon else None
    icon_width = len(icon_data) if icon_data else 0

    if header:
        display.text(header, 0, 0, 1)

    if text:
        max_chars = (128 - icon_width) // 8
        lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
        y = y_start
        for line in lines:
            display.text(line, 0, y, 1)
            y += line_height
            if y + line_height > 32:
                break

    if icon_data:
        size = len(icon_data)
        draw_icon(icon_data, 128 - size, (32 - size) // 2)

    display.show()


if initialize_display():
    update_display(header="Screen", icon='robot')
else:
    print("Failed to initialize the display. Cannot display text.")
