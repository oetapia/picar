"""
Test script for the dual ToF sensor API endpoint
Run this on your computer (not on the Pico) to test the API
"""

import requests
import time

# Configuration
PICAR_IP = "192.168.1.100"  # Replace with your PiCar's IP address
PICAR_PORT = 5000
BASE_URL = f"http://{PICAR_IP}:{PICAR_PORT}"

def test_tof():
    """Test the dual ToF sensor API endpoint."""
    print("=" * 60)
    print("Testing Dual ToF API")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/tof"
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
                print(f"Left Sensor:  {data.get('left_available', False)}")
                print(f"Right Sensor: {data.get('right_available', False)}")
                print()
                
                left_dist = data.get('left_distance_cm')
                right_dist = data.get('right_distance_cm')
                
                print(f"Left Distance:  {left_dist:.1f} cm" if left_dist else "Left Distance:  Not available")
                print(f"Right Distance: {right_dist:.1f} cm" if right_dist else "Right Distance: Not available")
                
                # Show angle data if available
                if data.get('angle'):
                    angle = data['angle']
                    print()
                    print("Wall Angle Analysis:")
                    print(f"  Angle:       {angle['angle_degrees']:+.2f}°")
                    print(f"  Orientation: {angle['orientation']}")
                    print(f"  Perpendicular: {'Yes' if angle['is_perpendicular'] else 'No'}")
                    print(f"  Wall Distance: {angle['wall_distance_cm']:.1f} cm")
                else:
                    print("\n⚠️  Angle data not available (requires both sensors)")
                
                print(f"\nMessage: {data.get('message')}")
                print(f"Timestamp: {data.get('timestamp')}")
            else:
                print(f"❌ Sensors not available: {data.get('message')}")
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
    """Continuously read ToF sensor data for a duration."""
    print("\n" + "=" * 60)
    print(f"Continuous Reading Test ({duration} seconds)")
    print("=" * 60)
    
    endpoint = f"{BASE_URL}/api/tof"
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
                    print(f"[{count:03d}] Sensors not available")
            time.sleep(0.5)
        
        print(f"\n✅ Completed {count} readings in {duration} seconds")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Stopped by user after {count} readings")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    print("\n🤖 PiCar Dual ToF API Test")
    print(f"Target: {BASE_URL}")
    print("\nMake sure to update PICAR_IP with your PiCar's IP address!\n")
    
    # Run single test
    test_tof()
    
    # Optionally run continuous test
    response = input("\nRun continuous test? (y/n): ").strip().lower()
    if response == 'y':
        test_continuous(duration=10)
    
    print("\n✅ Test complete!")
