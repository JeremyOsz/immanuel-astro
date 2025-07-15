#!/usr/bin/env python3
"""
Birth Chart Generator for Melbourne, Victoria, Australia
10 December 1991, 04:59 AM
Coordinates: -37.814, 144.96332
Timezone: UTC+11 DST (Australia/Melbourne)
"""

import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Your specific birth data
BIRTH_DATA = {
    "date": "1991-12-10",  # December 10, 1991
    "time": "04:59:00",    # 4:59 AM
    "place": "Melbourne, Victoria, Australia",
    "latitude": -37.814,   # Your exact coordinates
    "longitude": 144.96332,
    "house_system": "whole_sign"  # or "placidus" if you prefer
}

# API Configuration - get API key from environment
API_BASE_URL = "http://127.0.0.1:8001"
API_KEY = os.getenv("API_KEY", "your-secret-api-key-here")

def format_sign_degree(longitude, sign):
    """Convert absolute longitude to sign-relative degree (e.g., 17°09')"""
    sign_order = [
        "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
        "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
    ]
    sign_index = sign_order.index(sign) if sign in sign_order else 0
    sign_start = sign_index * 30
    deg_in_sign = longitude - sign_start
    if deg_in_sign < 0:
        deg_in_sign += 30
    degrees = int(deg_in_sign)
    minutes = int(round((deg_in_sign - degrees) * 60))
    if minutes == 60:
        degrees += 1
        minutes = 0
    return f"{degrees}°{minutes:02d}'"

def generate_birth_chart():
    """Generate and display the birth chart"""
    print("🌟 Birth Chart Generator")
    print("=" * 60)
    print(f"📍 Location: {BIRTH_DATA['place']}")
    print(f"📅 Date: {BIRTH_DATA['date']}")
    print(f"🕐 Time: {BIRTH_DATA['time']}")
    print(f"🌍 Coordinates: {BIRTH_DATA['latitude']}, {BIRTH_DATA['longitude']}")
    print(f"�� House System: {BIRTH_DATA['house_system']}")
    print(f"🔑 API Key: {API_KEY[:10]}..." if len(API_KEY) > 10 else f"🔑 API Key: {API_KEY}")
    print("=" * 60)
    
    # Headers with API key from environment
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        # Make request to the API
        response = requests.post(
            f"{API_BASE_URL}/birth-chart",
            json=BIRTH_DATA,
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"Error: {response.text}")
            return
        
        # Parse the response
        chart_data = response.json()
        print("✅ Birth chart generated successfully!")
        print()
        
        # Extract objects (planets, angles, etc.)
        objects = chart_data.get('objects', {})
        
        # Define the order we want to display planets
        planet_order = [
            "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
            "Uranus", "Neptune", "Pluto", "North Node", "Lilith", "Chiron",
            "Part of Fortune", "Vertex", "Asc", "MC"
        ]
        
        # Display planets in order
        print("🌞 PLANETS & ANGLES:")
        print("-" * 40)
        
        for planet_name in planet_order:
            planet_found = None
            for obj_id, obj_data in objects.items():
                if obj_data.get('name') == planet_name:
                    planet_found = obj_data
                    break
            
            if planet_found:
                sign = planet_found.get('sign', {}).get('name', 'Unknown')
                longitude = planet_found.get('longitude', {})
                raw_long = longitude.get('raw', 0)
                retrograde = longitude.get('retrograde', False)
                degree = format_sign_degree(raw_long, sign)
                
                # Add emoji for planets
                planet_emoji = {
                    "Sun": "☀️", "Moon": "🌙", "Mercury": "☿", "Venus": "♀️", 
                    "Mars": "♂️", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", 
                    "Neptune": "♆", "Pluto": "♇", "North Node": "☊", 
                    "Lilith": "⚸", "Chiron": "⚷", "Part of Fortune": "⚸",
                    "Vertex": "⚸", "Asc": "🔼", "MC": "🔽"
                }
                
                emoji = planet_emoji.get(planet_name, "•")
                retrograde_symbol = " ℞" if retrograde else ""
                print(f"{emoji} {planet_name:15} {sign:12} {degree}{retrograde_symbol}")
        
        # Display house cusps
        print("\n🏠 HOUSE CUSPS:")
        print("-" * 40)
        
        house_cusps_found = 0
        for i in range(1, 13):
            house_name = f"{i}th House"
            house_found = None
            
            for obj_id, obj_data in objects.items():
                if obj_data.get('name') == house_name:
                    house_found = obj_data
                    break
            
            if house_found:
                sign = house_found.get('sign', {}).get('name', 'Unknown')
                longitude = house_found.get('longitude', {})
                raw_long = longitude.get('raw', 0)
                degree = format_sign_degree(raw_long, sign)
                print(f"🏠 {house_name:10} {sign:12} {degree}")
                house_cusps_found += 1
        
        print(f"\n📊 Summary: {house_cusps_found}/12 house cusps found")
        
        # Save full response to file
        with open('melbourne_birth_chart.json', 'w') as f:
            json.dump(chart_data, f, indent=2)
        print(f"\n💾 Full chart data saved to 'melbourne_birth_chart.json'")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API. Make sure the server is running on localhost:8001")
    except Exception as e:
        print(f"❌ Error generating birth chart: {e}")

if __name__ == "__main__":
    generate_birth_chart()