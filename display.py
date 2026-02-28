import machine
import ssd1306
import framebuf
import icons
import time

# Global variable to store the display object
display = None

def initialize_display():
    global display
    # Initialize I2C with default pins
    i2c = machine.I2C(1, sda=machine.Pin(18), scl=machine.Pin(19))  # Change if you are using different pins
    
    # Scan for I2C devices
    devices = i2c.scan()
    print('I2C devices found:', devices)
    
    # Try to initialize the OLED display
    try:
        # Initialize the OLED display with 128x64 resolution (adjust if needed)
        display = ssd1306.SSD1306_I2C(128, 64, i2c)
        display.fill(0)  # Clear the display
        display.text('Screen on', 0, 0, 1)
        display.show()
        return True
    except Exception as e:
        print("OLED display not detected or initialization failed.")
        return False
    
def list_display_methods():
    if display is None:
        print("Display not initialized.")
        return

    # List available methods and attributes of the display object
    methods = dir(display)
    print("Available methods and attributes:")
    for method in methods:
        print(method)

def draw_rectangle(x, y, width, height, color):
    # Use the framebuf object to draw a rectangle
    fb = display.framebuf  # Get the framebuf object
    fb.rect(x, y, width, height, color)  # Draw a rectangle
    
  


def draw_icon(display, icon_data, x, y, size):
    
       # Check if the size of icon_data matches the expected size
    if len(icon_data) != size:
        raise ValueError(f"Icon data length does not match the specified size. Expected {size} rows, got {len(icon_data)} rows.")
    
    
     # Convert icon_data into a bytearray
    byte_data = bytearray((0 for _ in range((size + 7) // 8 * size)))
    for row in range(size):
        for col in range(size):
            if icon_data[row] & (1 << (size - 1 - col)):
                byte_data[row * (size // 8) + col // 8] |= (1 << (7 - (col % 8)))

    fb = framebuf.FrameBuffer(byte_data, size, size, framebuf.MONO_HLSB)
    
    # Draw the icon on the display
    for row in range(size):
        for col in range(size):
            if fb.pixel(col, row):  # Check if the pixel is on
                display.pixel(x + col, y + row, 1)  # Draw the pixel


def update_display(header=None, text=None, y_start=16, line_height=10, icon=None):
    if display is None:
        print("Display not initialized.")
        return

    # Clear the whole display initially if header or text are provided
    if header or text or image:
        display.fill(0)
    
    # Display header if provided
    if header:
        display.text(header, 0, 0, 1)  # Display header at the top
    
    # Display text if provided
    if text:
        max_line_length = 16  # Adjust based on your font and display width
        lines = [text[i:i + max_line_length] for i in range(0, len(text), max_line_length)]
        y = y_start
        for line in lines:
            display.text(line, 0, y, 1)  # Display each line at the appropriate y position
            y += line_height  # Move to the next line position
            if y + line_height > 64:  # Stop if we exceed the display height
                break
            
    # Draw icon if provided
    if icon == 'square':
        draw_rectangle(24, 22, 32, 32, 1)  # Draw a square (32x32) starting at (16,10)
    elif icon == 'rectangle':
        draw_rectangle(16, 10, 60, 30, 1)  # Draw a rectangle (60x30) starting at (16,10)
    elif icon == 'heart':
        display.fill(0)
        display.text(header, 0, 0, 1)  # Display header at the top
        draw_icon(display, icons.emoticon_heart_8, 60, 32, 8)  # Draw the heart icon at (60, 28)
        display.show()
        time.sleep(1)
        display.fill(0)
        display.text(header, 0, 0, 1)  # Display header at the top
        draw_icon(display, icons.emoticon_heart_16, 56, 28, 16)  # Draw the heart icon at (60, 28)
        display.show()
        time.sleep(1)
        display.fill(0)
        display.text(header, 0, 0, 1)  # Display header at the top
        draw_icon(display, icons.emoticon_heart_24, 52, 24, 24)  # Draw the heart icon at (60, 28)
        display.show()
        
    display.show()


# Example usage
if initialize_display():
    #list_display_methods()
    update_display(
            header="Screen is ready",
            #text="Pass bootylicious texts",
            icon='heart'
            )
else:
    print("Failed to initialize the display. Cannot display text.")