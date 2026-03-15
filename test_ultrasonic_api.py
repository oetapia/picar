"""
Test script for the HC-SR04 ultrasonic sensor API endpoint
Run this on your computer (not on the Pico) to test the API
"""

import requests
import time
import secrets

# Configuration
PICAR_IP = secrets.car_ip  # Replace with your PiCar's IP address
PICAR_PORT = 5000
BASE_URL = f"http://{PICAR_IP}:{PICAR_PORT}"

def test_ultrasonic():
    """Test the ultrasonic sensor API endpoint."""
    print("=" * 60)
    print("Testing HC-SR04 Ultrasonic API")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/ultrasonic"
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
                distance = data.get('distance_cm')
                in_range = data.get('in_range')
                
                if distance:
                    print(f"Rear Distance: {distance:.1f} cm")
                    print(f"Obstacle in Range: {in_range}")
                    
                    # Warning if too close
                    if distance < 20:
                        print("\n⚠️  WARNING: Obstacle very close to rear!")
                    elif distance < 50:
                        print("\n⚠️  CAUTION: Obstacle detected behind car")
                else:
                    print("Rear Distance: No obstacle detected or out of range")
                    print(f"Obstacle in Range: {in_range}")
                
                print(f"\nMessage: {data.get('message')}")
                print(f"Timestamp: {data.get('timestamp')}")
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
    """Continuously read ultrasonic sensor data for a duration."""
    print("\n" + "=" * 60)
    print(f"Continuous Reading Test ({duration} seconds)")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/ultrasonic"
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
    print("\n🤖 PiCar HC-SR04 Ultrasonic API Test")
    print(f"Target: {BASE_URL}")
    print("\nMake sure to update PICAR_IP with your PiCar's IP address!\n")
    
    # Run single test
    test_ultrasonic()
    
    # Optionally run continuous test
    response = input("\nRun continuous test? (y/n): ").strip().lower()
    if response == 'y':
        test_continuous(duration=10)
    
    print("\n✅ Test complete!")
