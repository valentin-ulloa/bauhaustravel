#!/usr/bin/env python3
"""
🧪 Test actual polling system with BA820 trip.
This will simulate what the scheduler does and verify if API calls occur.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.scheduler_service import SchedulerService
from app.agents.notifications_agent import NotificationsAgent
from app.db.supabase_client import SupabaseDBClient

async def test_ba820_polling():
    """Test actual polling behavior with BA820"""
    
    print("🧪 TESTING BA820 POLLING BEHAVIOR")
    print("=" * 60)
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        now_utc = datetime.now(timezone.utc)
        print(f"Current time UTC: {now_utc.isoformat()}")
        print()
        
        # Test 1: Direct database query like scheduler does
        print("1️⃣ TESTING DIRECT DB QUERY (scheduler behavior)...")
        trips_to_poll = await db_client.get_trips_to_poll(now_utc)
        
        print(f"   Trips returned by get_trips_to_poll(): {len(trips_to_poll)}")
        
        if trips_to_poll:
            for trip in trips_to_poll:
                print(f"   - Flight: {trip.flight_number}")
                print(f"     ID: {trip.id}")
                print(f"     Next check: {trip.next_check_at}")
                print(f"     Status: {trip.status}")
        else:
            print("   No trips due for polling")
        print()
        
        # Test 2: Check specific BA820 trip by getting all trips
        print("2️⃣ FINDING BA820 TRIP SPECIFICALLY...")
        
        # Get trips in a wider window to find BA820
        future_window = now_utc + timedelta(days=1)
        all_trips = await db_client.get_trips_to_poll(future_window)
        
        ba820_trips = [trip for trip in all_trips if trip.flight_number == "BA820"]
        
        if ba820_trips:
            trip = ba820_trips[0]
            print(f"   ✅ Found BA820 trip: {trip.id}")
            print(f"   Next check at: {trip.next_check_at}")
            print(f"   Status: {trip.status}")
            
            # Parse next_check_at to understand format
            next_check_str = str(trip.next_check_at)
            print(f"   Next check (raw): {repr(next_check_str)}")
            
            # Try to parse and compare
            try:
                if 'T' in next_check_str and next_check_str.endswith('+00:00'):
                    next_check_dt = datetime.fromisoformat(next_check_str)
                elif 'T' in next_check_str:
                    next_check_dt = datetime.fromisoformat(next_check_str + '+00:00')
                else:
                    # Assume space format and add timezone
                    next_check_dt = datetime.fromisoformat(next_check_str.replace(' ', 'T') + '+00:00')
                
                time_diff = next_check_dt - now_utc
                print(f"   Parsed next check: {next_check_dt}")
                print(f"   Time difference: {time_diff}")
                
                if time_diff.total_seconds() <= 0:
                    print(f"   🚨 Should be polled (next_check_at <= now)")
                else:
                    print(f"   ✅ Not yet due ({time_diff} remaining)")
                    
            except Exception as e:
                print(f"   ❌ Could not parse next_check_at: {e}")
            print()
        
        # Test 3: Simulate scheduler behavior
        print("3️⃣ SIMULATING SCHEDULER BEHAVIOR...")
        
        if trips_to_poll:
            print(f"   Would process {len(trips_to_poll)} trips")
            
            for trip in trips_to_poll:
                if trip.flight_number == "BA820":
                    print(f"   🎯 BA820 would trigger API call to AeroAPI!")
                    print(f"      Flight: {trip.flight_number}")
                    print(f"      Route: {trip.origin_iata} → {trip.destination_iata}")
                    print(f"      Departure: {trip.departure_date}")
                    
                    # Test what notifications agent would do
                    print("   📡 Testing NotificationsAgent.check_single_trip_status()...")
                    try:
                        result = await notifications_agent.check_single_trip_status(trip)
                        print(f"      Result: {result.success}")
                        if result.success:
                            print(f"      Data: {result.data}")
                        else:
                            print(f"      Error: {result.error}")
                    except Exception as e:
                        print(f"      Exception: {e}")
        else:
            print("   ✅ No trips to process - no API calls would be made")
        print()
        
        # Test 4: Landing detection
        print("4️⃣ TESTING LANDING DETECTION...")
        past_8h = now_utc - timedelta(hours=8)
        landing_trips = await db_client.get_trips_after_departure(past_8h)
        
        print(f"   Trips in landing detection: {len(landing_trips)}")
        
        ba820_in_landing = any(trip.flight_number == "BA820" for trip in landing_trips)
        print(f"   BA820 in landing detection: {'YES' if ba820_in_landing else 'NO'}")
        
        if ba820_in_landing:
            print("   🚨 BA820 would also trigger API call from landing detection!")
        print()
        
        # Summary
        total_api_calls = len(trips_to_poll) + len(landing_trips)
        print("5️⃣ SUMMARY...")
        print(f"   API calls from polling: {len(trips_to_poll)}")
        print(f"   API calls from landing detection: {len(landing_trips)}")
        print(f"   TOTAL API calls if scheduler runs: {total_api_calls}")
        
        if total_api_calls == 0:
            print("   🎉 PERFECT: No API abuse - system respects next_check_at")
        elif total_api_calls == 1:
            print("   ✅ GOOD: Only 1 API call - acceptable for active flight")
        else:
            print("   ⚠️  MULTIPLE API calls detected")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()
        await notifications_agent.close()

if __name__ == "__main__":
    asyncio.run(test_ba820_polling()) 