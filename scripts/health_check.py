#!/usr/bin/env python3
"""
Main health check script for Bauhaus Travel MVP.
Runs all tests in sequence and reports results.
"""

import sys
import time
from test_trip_creation import test_trip_creation
from test_itinerary_flow import test_itinerary_flow
from test_concierge_flow import test_concierge_flow
import structlog

logger = structlog.get_logger()

def run_health_check():
    """Run complete health check of MVP components."""
    
    print("🔍 Starting Bauhaus Travel MVP Health Check...")
    print("=" * 50)
    
    # 1. Test trip creation
    print("\n1️⃣ Testing POST /trips endpoint...")
    trip_id = test_trip_creation()
    
    if not trip_id:
        print("❌ Trip creation failed - stopping health check")
        return False
    
    print("\n✅ Trip created successfully!")
    print(f"📝 Trip ID: {trip_id}")
    print("=" * 50)
    
    # 2. Test automatic itinerary generation
    print("\n2️⃣ Testing automatic itinerary generation...")
    time.sleep(5)  # Give scheduler time to process
    
    if not test_itinerary_flow(trip_id):
        print("❌ Itinerary generation failed")
        return False
    
    print("\n✅ Itinerary generated successfully!")
    print("=" * 50)
    
    # 3. Test WhatsApp webhook and ConciergeAgent
    print("\n3️⃣ Testing WhatsApp webhook and ConciergeAgent...")
    
    if not test_concierge_flow(trip_id):
        print("❌ ConciergeAgent test failed")
        return False
    
    print("\n✅ ConciergeAgent responded successfully!")
    print("=" * 50)
    
    # All tests passed
    print("\n🎉 HEALTH CHECK COMPLETED SUCCESSFULLY!")
    print("All core MVP components are working as expected.")
    return True

if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1) 