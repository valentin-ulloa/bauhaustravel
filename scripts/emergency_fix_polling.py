#!/usr/bin/env python3
"""
🚨 EMERGENCY FIX: Stop API abuse immediately by correcting next_check_at values.
This script will fix all trips that are causing excessive AeroAPI polling.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import UUID

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.utils.flight_schedule_utils import calculate_unified_next_check

async def emergency_fix_polling():
    """Emergency fix to stop API abuse immediately"""
    
    print("🚨 EMERGENCY FIX: Stopping AeroAPI abuse")
    print("=" * 60)
    
    db_client = SupabaseDBClient()
    
    try:
        now_utc = datetime.now(timezone.utc)
        print(f"Current time UTC: {now_utc.isoformat()}")
        
        # 1. Get ALL trips to analyze the situation
        print(f"\n1️⃣ ANALYZING ALL TRIPS...")
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={
                "select": "id,flight_number,client_name,departure_date,next_check_at,status",
                "order": "departure_date.asc"
            }
        )
        response.raise_for_status()
        all_trips = response.json()
        
        print(f"   Total trips in database: {len(all_trips)}")
        
        # 2. Categorize trips
        past_trips = []
        future_trips = []
        current_polling_trips = []
        
        for trip_data in all_trips:
            # Parse departure date
            departure_str = trip_data["departure_date"]
            if departure_str.endswith('Z'):
                departure_dt = datetime.fromisoformat(departure_str.replace('Z', '+00:00'))
            else:
                departure_dt = datetime.fromisoformat(departure_str)
                if departure_dt.tzinfo is None:
                    departure_dt = departure_dt.replace(tzinfo=timezone.utc)
            
            # Parse next_check_at
            next_check_str = trip_data.get("next_check_at")
            if next_check_str:
                if next_check_str.endswith('Z'):
                    next_check_dt = datetime.fromisoformat(next_check_str.replace('Z', '+00:00'))
                else:
                    next_check_dt = datetime.fromisoformat(next_check_str)
                    if next_check_dt.tzinfo is None:
                        next_check_dt = next_check_dt.replace(tzinfo=timezone.utc)
                
                # Check if trip is currently being polled
                if next_check_dt <= now_utc:
                    current_polling_trips.append({**trip_data, "departure_dt": departure_dt, "next_check_dt": next_check_dt})
            
            if departure_dt < now_utc:
                past_trips.append({**trip_data, "departure_dt": departure_dt})
            else:
                future_trips.append({**trip_data, "departure_dt": departure_dt})
        
        print(f"   Past trips (already departed): {len(past_trips)}")
        print(f"   Future trips (not yet departed): {len(future_trips)}")
        print(f"   🚨 TRIPS BEING POLLED RIGHT NOW: {len(current_polling_trips)}")
        
        # 3. Show current polling abuse
        if current_polling_trips:
            print(f"\n🚨 CURRENT API ABUSE - These trips are being polled every 5 minutes:")
            for trip in current_polling_trips:
                hours_overdue = (now_utc - trip["next_check_dt"]).total_seconds() / 3600
                print(f"   ❌ {trip['flight_number']} ({trip['client_name'][:20]}...) - overdue by {hours_overdue:.1f}h")
        
        # 4. Fix past trips (set to LANDED or very infrequent polling)
        print(f"\n2️⃣ FIXING PAST TRIPS...")
        past_fixes = 0
        
        for trip in past_trips:
            try:
                # For past trips, set next_check_at to far future to stop polling
                # Unless they're already LANDED
                if trip.get("status") == "LANDED":
                    # Set next_check_at to None for landed trips
                    new_next_check = None
                    print(f"   ✅ {trip['flight_number']}: Already LANDED - removing from polling")
                else:
                    # Set to check once every 24 hours for landing detection
                    new_next_check = now_utc + timedelta(hours=24)
                    print(f"   🔧 {trip['flight_number']}: Setting landing check in 24h")
                
                # Update database
                update_data = {}
                if new_next_check:
                    update_data["next_check_at"] = new_next_check.isoformat()
                else:
                    update_data["next_check_at"] = None
                
                response = await db_client._client.patch(
                    f"{db_client.rest_url}/trips",
                    json=update_data,
                    params={"id": f"eq.{trip['id']}"}
                )
                response.raise_for_status()
                past_fixes += 1
                
            except Exception as e:
                print(f"   ❌ Error fixing {trip['flight_number']}: {e}")
        
        print(f"   ✅ Fixed {past_fixes} past trips")
        
        # 5. Fix future trips with intelligent scheduling
        print(f"\n3️⃣ FIXING FUTURE TRIPS WITH INTELLIGENT SCHEDULING...")
        future_fixes = 0
        
        for trip in future_trips:
            try:
                departure_dt = trip["departure_dt"]
                
                # Calculate correct next_check using unified logic
                correct_next_check = calculate_unified_next_check(
                    departure_time=departure_dt,
                    now_utc=now_utc,
                    current_status="SCHEDULED"
                )
                
                if correct_next_check:
                    hours_to_departure = (departure_dt - now_utc).total_seconds() / 3600
                    hours_to_next_check = (correct_next_check - now_utc).total_seconds() / 3600
                    
                    print(f"   🔧 {trip['flight_number']}: T-{hours_to_departure:.1f}h → next check in {hours_to_next_check:.1f}h")
                    
                    # Update database
                    response = await db_client._client.patch(
                        f"{db_client.rest_url}/trips",
                        json={"next_check_at": correct_next_check.isoformat()},
                        params={"id": f"eq.{trip['id']}"}
                    )
                    response.raise_for_status()
                    future_fixes += 1
                else:
                    print(f"   ⚠️  {trip['flight_number']}: No next check calculated (very far future)")
                
            except Exception as e:
                print(f"   ❌ Error fixing {trip['flight_number']}: {e}")
        
        print(f"   ✅ Fixed {future_fixes} future trips")
        
        # 6. Verify fix
        print(f"\n4️⃣ VERIFYING FIX...")
        trips_to_poll_now = await db_client.get_trips_to_poll(now_utc)
        
        print(f"   🎯 Trips that will be polled NOW: {len(trips_to_poll_now)}")
        
        if trips_to_poll_now:
            print("   ⚠️  These trips are still in polling queue:")
            for trip in trips_to_poll_now:
                print(f"      - {trip.flight_number} ({trip.client_name})")
        else:
            print("   ✅ SUCCESS: No trips in immediate polling queue!")
        
        print(f"\n🎉 EMERGENCY FIX COMPLETED!")
        print(f"   Past trips fixed: {past_fixes}")
        print(f"   Future trips fixed: {future_fixes}")
        print(f"   API abuse should be STOPPED immediately!")
        print(f"   Next scheduler run will respect the new timings (every 30 min)")
        
    except Exception as e:
        print(f"❌ Emergency fix failed: {e}")
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(emergency_fix_polling()) 