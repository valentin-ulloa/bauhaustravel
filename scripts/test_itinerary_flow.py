#!/usr/bin/env python3
"""
Test script for automatic itinerary generation flow.
"""

import requests
import json
import time
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

# Test configuration
API_BASE_URL = "http://localhost:8000"

def test_itinerary_flow(trip_id: str):
    """Test automatic itinerary generation for a trip."""
    
    print(f"🧪 Testing itinerary generation for trip {trip_id}...")
    
    # Wait for automatic generation (max 2 minutes)
    max_wait = 120
    check_interval = 5
    waited = 0
    
    while waited < max_wait:
        try:
            # Check if itinerary exists
            response = requests.get(
                f"{API_BASE_URL}/itinerary/{trip_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ SUCCESS: Itinerary generated automatically!")
                print(f"📄 Response: {json.dumps(data, indent=2)}")
                
                # Validate response structure
                if "itinerary_id" in data:
                    print(f"✅ Itinerary ID: {data['itinerary_id']}")
                if "status" in data:
                    print(f"✅ Status: {data['status']}")
                if "parsed_itinerary" in data:
                    print("✅ Parsed itinerary present")
                    
                return True
                
            elif response.status_code == 404:
                print(f"⏳ Waiting for itinerary generation... ({waited}s)")
                time.sleep(check_interval)
                waited += check_interval
                continue
                
            else:
                print(f"❌ UNEXPECTED STATUS: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error checking itinerary: {e}")
            logger.error("itinerary_check_failed", 
                trip_id=trip_id,
                error=str(e)
            )
            return False
    
    print("❌ TIMEOUT: Itinerary not generated within expected time")
    return False

if __name__ == "__main__":
    # Get trip_id from command line or use test value
    import sys
    trip_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not trip_id:
        print("❌ Please provide a trip_id")
        sys.exit(1)
        
    test_itinerary_flow(trip_id) 