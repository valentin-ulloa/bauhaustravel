#!/usr/bin/env python3
"""
Test AeroAPI Integration for Bauhaus Travel
"""

import os
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from app.services.aeroapi_client import AeroAPIClient, FlightStatus

# Load environment variables
load_dotenv()

async def test_aeroapi():
    """Test AeroAPI integration with real flight data"""
    
    print("🛫 Testing AeroAPI Integration...")
    
    # Initialize client
    client = AeroAPIClient()
    
    if not client.api_key:
        print("❌ AERO_API_KEY not found in environment variables")
        print("📝 Add AERO_API_KEY to your .env file to test")
        return False
    
    print(f"✅ AeroAPI client initialized")
    print(f"🔑 API Key: {client.api_key[:8]}...")
    
    # Test cases
    test_flights = [
        {"flight": "LP2464", "date": "2025-06-10"},  # Example from user's JSON
        {"flight": "AA1234", "date": "2025-06-15"},  # Common flight for testing
        {"flight": "LAN800", "date": "2025-01-07"},  # LATAM flight  
    ]
    
    print("\n📊 Testing flights:")
    
    for i, test_case in enumerate(test_flights, 1):
        flight_number = test_case["flight"]
        departure_date = test_case["date"]
        
        print(f"\n{i}. Testing {flight_number} on {departure_date}")
        print("-" * 50)
        
        try:
            # Get flight status
            status = await client.get_flight_status(flight_number, departure_date)
            
            if status:
                print(f"✅ Flight found!")
                print(f"   📝 Flight: {status.ident}")
                print(f"   📊 Status: {status.status}")
                print(f"   🚪 Gate: {status.gate_origin or 'Not assigned'}")
                print(f"   ⏰ Est. Departure: {status.estimated_out or 'N/A'}")
                print(f"   ✈️ Aircraft: {status.aircraft_type or 'N/A'}")
                print(f"   📍 Route: {status.origin_iata} → {status.destination_iata}")
                print(f"   📈 Progress: {status.progress_percent}%")
                
                if status.cancelled:
                    print(f"   ❌ CANCELLED")
                if status.diverted:
                    print(f"   🔄 DIVERTED")
                if status.departure_delay > 0:
                    print(f"   ⏱️ Delayed: {status.departure_delay} minutes")
                    
            else:
                print(f"❌ Flight not found or no data available")
                
        except Exception as e:
            print(f"💥 Error testing {flight_number}: {e}")
    
    # Test change detection
    print(f"\n🔍 Testing change detection...")
    
    # Create mock statuses for change detection test
    old_status = FlightStatus(
        ident="TEST123",
        status="Scheduled",
        gate_origin="A12",
        estimated_out="2025-06-15T10:00:00Z"
    )
    
    new_status = FlightStatus(
        ident="TEST123", 
        status="Delayed",
        gate_origin="B5",
        estimated_out="2025-06-15T11:30:00Z"
    )
    
    changes = client.detect_flight_changes(new_status, old_status)
    
    print(f"   📝 Detected {len(changes)} changes:")
    for change in changes:
        print(f"      - {change['type']}: {change['old_value']} → {change['new_value']}")
        print(f"        📢 Notification: {change['notification_type']}")
    
    print(f"\n✅ AeroAPI testing completed!")
    return True

if __name__ == "__main__":
    print("🚀 Starting AeroAPI Integration Test...")
    success = asyncio.run(test_aeroapi())
    if success:
        print("\n🎉 AeroAPI integration is ready!")
        print("💡 Next: Add AEROAPI_KEY to production environment")
    else:
        print("\n❌ AeroAPI integration needs setup") 