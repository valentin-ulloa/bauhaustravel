#!/usr/bin/env python3
"""
Test script to validate trip creation and notification flow.
"""

import requests
import json
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()
BASE_URL = "http://localhost:8000"

def test_trip_creation():
    print("🚀 Testing POST /trips endpoint...")
    
    # Set departure date to 25 hours from now
    departure_date = (datetime.utcnow() + timedelta(hours=25)).replace(microsecond=0).isoformat() + 'Z'
    trip_data = {
        "client_name": "Valen Ulloa Test 24h",
        "whatsapp": "+5491140383422",
        "flight_number": "AR1303",
        "origin_iata": "EZE",
        "destination_iata": "MIA",
        "departure_date": departure_date,
        "client_description": "Test notificación 24h."
    }
    
    try:
        # Make POST request to /trips
        response = requests.post(
            f"{BASE_URL}/trips",
            json=trip_data
        )
        
        # Log response
        logger.info("trip_creation_response",
            status_code=response.status_code,
            response=response.json() if response.ok else response.text
        )
        
        if response.status_code == 201:
            print("✅ Trip created successfully!")
            print(f"Trip ID: {response.json()['trip_id']}")
            print("You should receive a WhatsApp confirmation shortly.")
            return response.json()['trip_id']
        elif response.status_code == 409:
            print("⚠️ Trip already exists (duplicate)")
            return None
        elif response.status_code == 422:
            print("❌ Validation error:", response.json())
            return None
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        logger.error("trip_creation_error", error=str(e))
        print(f"❌ Error creating trip: {str(e)}")
        return None

if __name__ == "__main__":
    test_trip_creation() 