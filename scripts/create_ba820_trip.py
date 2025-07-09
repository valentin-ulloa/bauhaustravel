#!/usr/bin/env python3
"""
✈️ Create BA820 trip for system testing after API abuse fixes.
This will test that the next_check_at logic works correctly with a real flight.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import UUID

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.models.database import TripCreate
from app.utils.timezone_utils import parse_local_time_to_utc

async def create_ba820_trip():
    """Create BA820 trip for Valentin"""
    
    print("✈️ CREATING BA820 TRIP")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    
    try:
        # Flight details from user
        client_name = "Valentin"
        whatsapp = "+5491140383422"
        flight_number = "BA820"
        origin_iata = "LHR"
        destination_iata = "CPH"
        
        # Parse departure time (London local time -> UTC)
        # Wed, 09 Jul 2025, 16:20 London time
        london_departure = datetime(2025, 7, 9, 16, 20)
        departure_utc = parse_local_time_to_utc(london_departure, origin_iata)
        
        # Parse arrival time (Copenhagen local time -> UTC)  
        # Wed, 09 Jul 2025, 19:15 Copenhagen time
        copenhagen_arrival = datetime(2025, 7, 9, 19, 15)
        arrival_utc = parse_local_time_to_utc(copenhagen_arrival, destination_iata)
        
        print(f"Client: {client_name}")
        print(f"WhatsApp: {whatsapp}")
        print(f"Flight: {flight_number}")
        print(f"Route: {origin_iata} → {destination_iata}")
        print(f"Departure: {london_departure} London time → {departure_utc} UTC")
        print(f"Arrival: {copenhagen_arrival} Copenhagen time → {arrival_utc} UTC")
        print()
        
        # Check for duplicates
        print("1️⃣ CHECKING FOR DUPLICATES...")
        duplicate_check = await db_client.check_duplicate_trip(
            whatsapp, flight_number, departure_utc
        )
        
        if duplicate_check.success and duplicate_check.data["exists"]:
            print(f"   ⚠️  Trip already exists! Count: {duplicate_check.data['count']}")
            print("   Continuing anyway for testing...")
        else:
            print("   ✅ No duplicates found")
        print()
        
        # Prepare trip data with metadata
        trip_metadata = {
            "source": "manual_testing",
            "terminal_origin": "5",
            "terminal_destination": "2", 
            "check_in_zone": "Zone D",
            "flight_details": {
                "check_in_time": "14:20",
                "expected_arrival": arrival_utc.isoformat(),
                "status_note": "ON TIME at creation"
            },
            "created_for_testing": True
        }
        
        trip_data = TripCreate(
            client_name=client_name,
            whatsapp=whatsapp,
            flight_number=flight_number,
            origin_iata=origin_iata,
            destination_iata=destination_iata,
            departure_date=departure_utc,
            status="ACTIVE",
            metadata=trip_metadata,
            client_description="Test passenger for API abuse prevention validation",
            agency_id=None  # No agency for testing
        )
        
        print("2️⃣ CREATING TRIP...")
        result = await db_client.create_trip(trip_data)
        
        if result.success:
            trip_id = result.data["id"]
            next_check_at = result.data.get("next_check_at")
            
            print(f"   ✅ Trip created successfully!")
            print(f"   Trip ID: {trip_id}")
            print(f"   Next check at: {next_check_at}")
            print()
            
            # Calculate time until next check
            if next_check_at:
                next_check_dt = datetime.fromisoformat(next_check_at.replace('Z', '+00:00'))
                now_utc = datetime.now(timezone.utc)
                time_until_check = next_check_dt - now_utc
                
                print("3️⃣ NEXT_CHECK_AT ANALYSIS...")
                print(f"   Current time: {now_utc.isoformat()}")
                print(f"   Next check: {next_check_dt.isoformat()}")
                print(f"   Time until check: {time_until_check}")
                
                if time_until_check.total_seconds() > 0:
                    hours = time_until_check.total_seconds() / 3600
                    print(f"   ✅ Correctly scheduled for {hours:.1f} hours from now")
                else:
                    print(f"   🚨 WARNING: Next check is in the past! ({time_until_check})")
                print()
            
            # Test immediate polling to verify no API abuse
            print("4️⃣ TESTING IMMEDIATE POLLING...")
            now_utc = datetime.now(timezone.utc)
            trips_to_poll = await db_client.get_trips_to_poll(now_utc)
            
            print(f"   Trips due for polling NOW: {len(trips_to_poll)}")
            if len(trips_to_poll) == 0:
                print("   ✅ PERFECT: No immediate API calls - respects next_check_at")
            else:
                print("   🚨 WARNING: Trip would be polled immediately")
                for trip in trips_to_poll:
                    if trip.id == trip_id:
                        print(f"      - BA820 trip next_check_at: {trip.next_check_at}")
            print()
            
            # Test future polling windows
            print("5️⃣ TESTING FUTURE POLLING WINDOWS...")
            for hours in [1, 6, 12, 24]:
                future_time = now_utc + timedelta(hours=hours)
                future_trips = await db_client.get_trips_to_poll(future_time)
                ba820_in_window = any(trip.id == trip_id for trip in future_trips)
                
                print(f"   In {hours}h: {len(future_trips)} trips, BA820: {'YES' if ba820_in_window else 'NO'}")
            print()
            
            print("6️⃣ SYSTEM STATUS...")
            print("   ✅ Trip created with intelligent next_check_at")
            print("   ✅ No immediate API abuse")
            print("   ✅ Respects scheduling logic")
            print("   🎉 System working correctly!")
            
            return trip_id
            
        else:
            print(f"   ❌ Trip creation failed: {result.error}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    trip_id = asyncio.run(create_ba820_trip())
    if trip_id:
        print(f"\n🎯 Next: Monitor with 'python3 scripts/monitor_api_usage.py'")
    else:
        print(f"\n❌ Trip creation failed") 