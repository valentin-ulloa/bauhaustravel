#!/usr/bin/env python3
"""
📊 API Usage Monitor - Track AeroAPI calls and verify optimization effectiveness.
This script helps monitor API usage patterns to prevent cost overruns.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient

async def monitor_api_usage():
    """Monitor current API usage patterns and trip statuses"""
    
    print("📊 API USAGE MONITOR")
    print("=" * 60)
    
    db_client = SupabaseDBClient()
    now_utc = datetime.now(timezone.utc)
    
    try:
        print(f"Current time UTC: {now_utc.isoformat()}")
        print()
        
        # 1. Check all trips that need polling
        print("1️⃣ ANALYZING ALL TRIPS...")
        
        # Get trips that might need polling in the future (24h window)
        future_window = now_utc + timedelta(hours=24)
        all_trips = await db_client.get_trips_to_poll(future_window)
        
        if not all_trips:
            print("   ✅ No trips in polling queue - API usage should be ZERO")
            return
        
        print(f"   Total trips in system: {len(all_trips)}")
        
        # 2. Check which trips will be polled NOW
        trips_to_poll = await db_client.get_trips_to_poll(now_utc)
        print(f"   🎯 Trips due for polling NOW: {len(trips_to_poll)}")
        
        if trips_to_poll:
            print("   📋 Trips that will generate API calls:")
            for trip in trips_to_poll:
                print(f"      • {trip.flight_number} - {trip.departure_date}")
                print(f"        next_check_at: {trip.next_check_at}")
        
        # 3. Check next polling windows
        print("\n2️⃣ NEXT POLLING WINDOWS...")
        
        for minutes in [30, 60, 120]:
            future_time = now_utc + timedelta(minutes=minutes)
            future_trips = await db_client.get_trips_to_poll(future_time)
            
            new_trips = len(future_trips) - len(trips_to_poll)
            print(f"   ⏰ In {minutes} minutes: {new_trips} additional trips will be polled")
        
        # 4. Trip status breakdown (for trips in polling queue)
        print("\n3️⃣ TRIP STATUS BREAKDOWN...")
        status_counts = {}
        for trip in all_trips:
            status = getattr(trip, 'status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in status_counts.items():
            print(f"   📊 {status}: {count} trips")
        
        # 5. Check for potential problems
        print("\n4️⃣ POTENTIAL ISSUES...")
        
        past_trips = [
            trip for trip in all_trips 
            if trip.departure_date < now_utc - timedelta(hours=6)
        ]
        
        if past_trips:
            print(f"   🚨 {len(past_trips)} trips are 6+ hours past departure")
            print("      These should be marked LANDED or cleaned up")
            for trip in past_trips[:5]:  # Show first 5
                print(f"      • {trip.flight_number} - {trip.departure_date}")
        else:
            print("   ✅ No old trips found")
        
        # 6. Estimate API usage
        print("\n5️⃣ API USAGE ESTIMATES...")
        daily_polls = len(trips_to_poll) * (24 * 60 // 30)  # Every 30 min
        print(f"   📈 Estimated daily API calls: {daily_polls}")
        
        if daily_polls > 100:
            print("   🚨 WARNING: High API usage detected!")
        elif daily_polls > 50:
            print("   ⚠️  CAUTION: Moderate API usage")
        else:
            print("   ✅ GOOD: Low API usage")
        
        print(f"\n🎯 RECOMMENDATION:")
        if daily_polls == 0:
            print("   Perfect! No API calls will be made.")
        elif daily_polls < 20:
            print("   Excellent - very low API usage.")
        elif daily_polls < 50:
            print("   Good - reasonable API usage.")
        else:
            print("   Consider cleaning up old trips or adjusting polling logic.")
            
    except Exception as e:
        print(f"❌ Error monitoring API usage: {e}")
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(monitor_api_usage()) 