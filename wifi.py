import time
import network
import secrets


def connect_wifi():
    """Connect to WiFi using secrets.py"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print(f'Connecting to WiFi: {secrets.ssid}')
        wlan.connect(secrets.ssid, secrets.password)

        timeout = 10
        while timeout > 0:
            if wlan.isconnected():
                break
            print('Waiting for connection...')
            time.sleep(1)
            timeout -= 1

        if not wlan.isconnected():
            print('WiFi connection failed!')
            return None

    ip_info = wlan.ifconfig()
    print(f'Connected to WiFi. IP: {ip_info[0]}')
    return wlan
