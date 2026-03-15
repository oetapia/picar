"""
Test script for the accelerometer API endpoint
Run this on your computer (not on the Pico) to test the API
"""

import requests
import time
import secrets

# Configuration
PICAR_IP = secrets.car_ip  # Replace with your PiCar's IP address
PICAR_PORT = 5000
BASE_URL = f"http://{PICAR_IP}:{PICAR_PORT}"

def test_accelerometer():
    """Test the accelerometer API endpoint."""
    print("=" * 60)
    print("Testing Accelerometer API")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/accelerometer"
    print(f"\nEndpoint: {endpoint}")
    
    try:
        # Make request
        print("\nSending GET request...")
        response = requests.get(endpoint, timeout=5)
        
        # Check status
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS!")
            print("\nResponse Data:")
            print("-" * 60)
            
            if data.get('success'):
                print(f"Acceleration (g):")
                print(f"  X: {data['acceleration']['x']:+.3f}g")
                print(f"  Y: {data['acceleration']['y']:+.3f}g")
                print(f"  Z: {data['acceleration']['z']:+.3f}g")
                
                print(f"\nGyroscope (deg/s):")
                print(f"  X: {data['gyroscope']['x']:+.1f}°/s")
                print(f"  Y: {data['gyroscope']['y']:+.1f}°/s")
                print(f"  Z: {data['gyroscope']['z']:+.1f}°/s")
                
                print(f"\nTilt Angles:")
                print(f"  Pitch: {data['tilt']['pitch']:+.1f}°")
                print(f"  Roll:  {data['tilt']['roll']:+.1f}°")
                
                print(f"\nOrientation: {data['orientation']}")
                print(f"\nMessage: {data['message']}")
                print(f"Timestamp: {data['timestamp']}")
            else:
                print(f"❌ Sensor not available: {data.get('message')}")
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ CONNECTION ERROR")
        print(f"Could not connect to {BASE_URL}")
        print("Make sure:")
        print("  1. PiCar is running main.py")
        print("  2. PiCar IP address is correct")
        print("  3. You're on the same network")
    except requests.exceptions.Timeout:
        print(f"\n❌ TIMEOUT ERROR")
        print("Request took too long - PiCar may be busy")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

def test_continuous(duration=10):
    """Continuously read accelerometer data for a duration."""
    print("\n" + "=" * 60)
    print(f"Continuous Reading Test ({duration} seconds)")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/accelerometer"
    start_time = time.time()
    count = 0
    
    try:
        while time.time() - start_time < duration:
            response = requests.get(endpoint, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    count += 1
                    print(f"[{count:03d}] {data['message']}")
                else:
                    print(f"[{count:03d}] Sensor not available")
            time.sleep(0.5)
        
        print(f"\n✅ Completed {count} readings in {duration} seconds")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Stopped by user after {count} readings")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    print("\n🤖 PiCar Accelerometer API Test")
    print(f"Target: {BASE_URL}")
    print("\nMake sure to update PICAR_IP with your PiCar's IP address!\n")
    
    # Run single test
    test_accelerometer()
    
    # Optionally run continuous test
    response = input("\nRun continuous test? (y/n): ").strip().lower()
    if response == 'y':
        test_continuous(duration=10)
    
    print("\n✅ Test complete!")
