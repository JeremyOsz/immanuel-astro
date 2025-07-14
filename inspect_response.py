#!/usr/bin/env python3
"""
Script to inspect the API response structure for Melbourne, Australia, 10/12/1991 4:59am
"""

import requests
import json

# Test data
TEST_DATA = {
    "date": "1991-12-10",
    "time": "04:59:00",
    "place": "Melbourne, Australia",
    "latitude": -37.8136,
    "longitude": 144.9631
}

def inspect_response():
    """Inspect the API response structure"""
    print("Inspecting API response structure...")
    print(f"Test data: {TEST_DATA}")
    print("-" * 50)
    
    try:
        # Make request to the API
        response = requests.post(
            "http://localhost:8001/birth-chart",
            json=TEST_DATA,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        # Parse the response
        chart_data = response.json()
        print("✅ API request successful")
        
        # Extract objects
        objects = chart_data.get('objects', {})
        
        print(f"\nFound {len(objects)} objects in the response:")
        print("-" * 50)
        
        # List all objects with their names and signs
        for obj_id, obj_data in objects.items():
            name = obj_data.get('name', 'Unknown')
            sign = obj_data.get('sign', {}).get('name', 'Unknown')
            longitude = obj_data.get('longitude', {})
            raw_long = longitude.get('raw', 0)
            retrograde = longitude.get('retrograde', False)
            
            print(f"{name}: {sign} {raw_long}°" + (" (R)" if retrograde else ""))
        
        print("\n" + "=" * 50)
        print("Looking for specific objects:")
        print("-" * 50)
        
        # Look for specific objects we're interested in
        target_objects = ["Node", "North Node", "True Node", "Fortune", "Part of Fortune", 
                         "ASC", "Ascendant", "Lilith", "Chiron"]
        
        for target in target_objects:
            found = False
            for obj_id, obj_data in objects.items():
                name = obj_data.get('name', '')
                if target.lower() in name.lower():
                    sign = obj_data.get('sign', {}).get('name', 'Unknown')
                    longitude = obj_data.get('longitude', {})
                    raw_long = longitude.get('raw', 0)
                    retrograde = longitude.get('retrograde', False)
                    print(f"✅ Found '{target}' as '{name}': {sign} {raw_long}°" + 
                          (" (R)" if retrograde else ""))
                    found = True
                    break
            
            if not found:
                print(f"❌ '{target}' not found")
        
        # Save full response to file for detailed inspection
        with open('api_response.json', 'w') as f:
            json.dump(chart_data, f, indent=2)
        print(f"\nFull response saved to 'api_response.json'")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API. Make sure the server is running on localhost:8001")
    except Exception as e:
        print(f"❌ Inspection failed with error: {e}")

if __name__ == "__main__":
    inspect_response() 