# Configuration File Migration: secrets.py → config.py

## Summary

The project has been migrated from `secrets.py` to `config.py` to avoid naming conflicts with Python's built-in `secrets` module and follow better naming conventions.

## Changes Made

### Files Renamed
- `secrets.py` → `config.py` (gitignored, not in repository)
- Created `config.example.py` as a template

### Files Updated to Use `config` Instead of `secrets`

#### Client Files (on your computer)
- ✅ `client/picar_client.py` - Now properly imports from parent directory
- ✅ `test_ultrasonic_api.py`
- ✅ `test_tof_api.py`
- ✅ `test_accelerometer_api.py`

#### Pico Files (on Raspberry Pi Pico W)
- ✅ `wifi.py`
- ✅ `main_long.py`

### Configuration Files
- ✅ `.gitignore` - Updated to ignore `config.py` instead of `secrets.py`
- ✅ `config.example.py` - Created as template

## What You Need to Do

### 1. Create Your config.py File

Copy the example template and add your actual credentials:

```bash
cp config.example.py config.py
```

Then edit `config.py` with your actual values:

```python
# WiFi credentials (for Raspberry Pi Pico W)
ssid = "YourActualWiFiName"
password = "YourActualWiFiPassword"

# PiCar IP address (update after connecting to WiFi)
car_ip = "192.168.178.30"  # Your actual PiCar IP
```

### 2. Upload config.py to Your Pico

The Pico needs `config.py` for WiFi connectivity:

1. Connect your Pico via USB
2. Open Thonny or your preferred editor
3. Create a file named `config.py` on the Pico
4. Add your WiFi credentials:

```python
ssid = "YourWiFiSSID"
password = "YourWiFiPassword"
```

**Note:** The Pico only needs `ssid` and `password`. The `car_ip` field is only used by client scripts running on your computer.

### 3. Test the Changes

#### On Your Computer:
```bash
# The client should now work without import errors
python client/picar_client.py

# Test scripts should also work
python test_ultrasonic_api.py
python test_tof_api.py
python test_accelerometer_api.py
```

#### On Your Pico:
The Pico should connect to WiFi using the credentials from `config.py` when you run `main.py`.

## Why This Change?

### Problem with `secrets.py`
Python has a built-in module called `secrets` (for cryptographic random numbers). When you tried to `import secrets`, Python was importing the built-in module instead of your file, causing the error:
```
AttributeError: module 'secrets' has no attribute 'car_ip'
```

### Solution: `config.py`
- ✅ No naming conflict with Python built-ins
- ✅ More descriptive name (configuration vs. secrets)
- ✅ Common convention in Python projects
- ✅ Still gitignored to protect credentials

## Security Notes

- ⚠️ **Never commit config.py to git** - It's already in `.gitignore`
- ✅ Use `config.example.py` as a template for others
- ✅ Share `config.example.py` in the repository
- ⚠️ config.py contains WiFi passwords and IP addresses - keep it private

## File Structure

```
picar/
├── config.py              # ← Your actual config (gitignored, create this)
├── config.example.py      # ← Template (in git)
├── .gitignore            # ← Updated to ignore config.py
├── client/
│   └── picar_client.py   # ← Updated to import config
├── test_*.py             # ← All test files updated
├── wifi.py               # ← Updated for Pico
└── main_long.py          # ← Updated for Pico
```

## Troubleshooting

### "No module named 'config'"

**On your computer:**
1. Make sure `config.py` exists in the project root
2. Check that it contains `car_ip = "..."`

**On the Pico:**
1. Make sure you've uploaded `config.py` to the Pico
2. Check that it contains `ssid` and `password`

### Client can't find config.py

The client now uses a smart import that looks in the parent directory:
```python
from pathlib import Path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
import config
```

This should work whether you run the client from:
- `python client/picar_client.py` (from root)
- `python picar_client.py` (from client directory)

### Fallback Behavior

If `config.py` is not found, the client will:
1. Print a warning message
2. Use hardcoded IP: `192.168.178.30`
3. Continue to work (if that IP is correct)

## Migration Complete! ✅

All files have been updated. Just create your `config.py` file from the template and you're ready to go!
