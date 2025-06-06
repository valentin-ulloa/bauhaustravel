#!/usr/bin/env python3
"""
Test script for POST /itinerary endpoint after database permissions fix.
"""

import requests
import json
from datetime import datetime

# Test configuration
API_BASE_URL = "http://localhost:8000"
TEST_TRIP_ID = "123e4567-e89b-12d3-a456-426614174000"  # Use existing trip ID

def test_itinerary_generation(trip_id=None):
    """Test POST /itinerary endpoint."""
    
    test_trip_id = trip_id or TEST_TRIP_ID
    print("🧪 Testing POST /itinerary endpoint...")
    print(f"📍 Using trip_id: {test_trip_id}")
    
    try:
        # Make the request
        response = requests.post(
            f"{API_BASE_URL}/itinerary",
            params={"trip_id": test_trip_id},
            timeout=30
        )
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 201:
            data = response.json()
            print("✅ SUCCESS: Itinerary generated successfully!")
            print(f"📄 Response: {json.dumps(data, indent=2)}")
            
            # Validate response structure
            if "itinerary_id" in data:
                print(f"✅ Itinerary ID: {data['itinerary_id']}")
            if "status" in data:
                print(f"✅ Status: {data['status']}")
            
        elif response.status_code == 404:
            print("❌ TRIP NOT FOUND - Need to create test trip first")
            print(f"Response: {response.text}")
            
        elif response.status_code == 403:
            print("❌ STILL 403 FORBIDDEN - Check database permissions")
            print(f"Response: {response.text}")
            
        else:
            print(f"❌ UNEXPECTED STATUS: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR: Is the FastAPI server running on localhost:8000?")
        print("Run: uvicorn app.main:app --reload")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")


def create_test_trip():
    """Create a test trip for itinerary generation."""
    
    print("🧪 Creating test trip first...")
    
    trip_data = {
        "client_name": "Test User",
        "whatsapp": "+1234567890",
        "flight_number": "AA123",
        "origin_iata": "NYC",
        "destination_iata": "LAX",
        "departure_date": "2024-12-15T14:30:00Z",
        "client_description": "I love museums, good food, and outdoor activities. Budget-conscious traveler."
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/trips",
            json=trip_data,
            timeout=10
        )
        
        if response.status_code == 201:
            data = response.json()
            trip_id = data.get("trip_id")
            print(f"✅ Test trip created: {trip_id}")
            return trip_id
        else:
            print(f"❌ Failed to create trip: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error creating trip: {e}")
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING POST /itinerary AFTER PERMISSIONS FIX")
    print("=" * 60)
    
    # First try with existing trip ID
    test_itinerary_generation()
    
    print("\n" + "=" * 60)
    print("📝 If 404, will create test trip and retry...")
    print("=" * 60)
    
    # If needed, create test trip and retry
    new_trip_id = create_test_trip()
    if new_trip_id:
        print(f"\n🔄 Retesting with new trip: {new_trip_id}")
        test_itinerary_generation(new_trip_id) 