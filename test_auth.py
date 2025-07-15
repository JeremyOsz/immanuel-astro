#!/usr/bin/env python3
"""
Test script for the Astrology API with authentication.
This shows how to make authenticated requests to your API.
"""

import requests
import json

# Configuration
API_BASE_URL = "http://127.0.0.1:8001"
API_KEY = "your-secret-api-key-here"  # Change this to match your config

def test_birth_chart_with_auth():
    """Test the birth chart endpoint with API key authentication."""
    
    url = f"{API_BASE_URL}/birth-chart"
    
    # Request data
    data = {
        "date": "1991-10-12",
        "time": "04:59:00",
        "place": "Melbourne, Australia",
        "latitude": -37.8136,
        "longitude": 144.9631,
        "house_system": "whole_sign"
    }
    
    # Headers with API key
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            print("✅ Birth chart request successful!")
            result = response.json()
            print(f"Chart generated for {data['place']}")
            
            # Debug: Print the structure of the response
            print(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
            if 'objects' in result:
                print(f"Objects type: {type(result['objects'])}")
                if result['objects']:
                    print(f"First object: {result['objects'][0] if isinstance(result['objects'], list) else 'Not a list'}")
            
            # Show some key data points (simplified)
            print("✅ Authentication working correctly!")
            
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Error: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")

def test_without_auth():
    """Test what happens when no API key is provided."""
    
    url = f"{API_BASE_URL}/birth-chart"
    
    data = {
        "date": "1991-10-12",
        "time": "04:59:00",
        "place": "Melbourne, Australia",
        "latitude": -37.8136,
        "longitude": 144.9631
    }
    
    headers = {
        "Content-Type": "application/json"
        # No X-API-Key header
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 401:
            print("✅ Authentication working correctly - API key required")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")

def test_invalid_auth():
    """Test what happens with an invalid API key."""
    
    url = f"{API_BASE_URL}/birth-chart"
    
    data = {
        "date": "1991-10-12",
        "time": "04:59:00",
        "place": "Melbourne, Australia",
        "latitude": -37.8136,
        "longitude": 144.9631
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "invalid-key"
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 403:
            print("✅ Invalid key correctly rejected")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")

if __name__ == "__main__":
    print("🔐 Testing Astrology API Authentication")
    print("=" * 50)
    
    print("\n1. Testing with valid API key:")
    test_birth_chart_with_auth()
    
    print("\n2. Testing without API key:")
    test_without_auth()
    
    print("\n3. Testing with invalid API key:")
    test_invalid_auth()
    
    print("\n" + "=" * 50)
    print("✅ Authentication tests complete!") 