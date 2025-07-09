#!/usr/bin/env python3
"""
Check status of created test trips - verify next_check_at and gate logic
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient

async def check_trips_status():
    """Check current status of both test trips"""
    db_client = SupabaseDBClient()
    
    try:
        # Get all trips for our test users
        print("🔍 CHECKING TRIPS STATUS")
        print("=" * 50)
        
        # Query trips for Valentin and Malena
        valentin_trips = await db_client.get_trips_by_whatsapp("+5491140383422")
        malena_trips = await db_client.get_trips_by_whatsapp("+5491171937231")
        
        all_trips = []
        if valentin_trips:
            all_trips.extend(valentin_trips)
        if malena_trips:
            all_trips.extend(malena_trips)
        
        if not all_trips:
            print("❌ No trips found")
            return
        
        now_utc = datetime.now(timezone.utc)
        
        for trip in all_trips:
            print(f"\n🛫 TRIP: {trip.get('client_name')} - {trip.get('flight_number')}")
            print(f"   Trip ID: {trip.get('id')}")
            print(f"   Route: {trip.get('origin_iata')} → {trip.get('destination_iata')}")
            
            # Departure analysis
            departure_utc = datetime.fromisoformat(trip.get('departure_date').replace('Z', '+00:00'))
            hours_until = (departure_utc - now_utc).total_seconds() / 3600
            print(f"   Departure UTC: {departure_utc.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Hours until departure: {hours_until:.1f}h")
            
            # Next check analysis
            next_check = trip.get('next_check_at')
            if next_check:
                next_check_utc = datetime.fromisoformat(next_check.replace('Z', '+00:00'))
                next_check_hours = (next_check_utc - now_utc).total_seconds() / 3600
                print(f"   Next check UTC: {next_check_utc.strftime('%Y-%m-%d %H:%M')}")
                print(f"   Next check in: {next_check_hours:.1f}h")
                
                # Determine polling phase
                if hours_until > 24:
                    expected_interval = "12h"
                elif hours_until > 4:
                    expected_interval = "10h"
                elif hours_until > 1:
                    expected_interval = "40min"
                elif hours_until > 0:
                    expected_interval = "15min"
                else:
                    expected_interval = "arrival_time"
                
                print(f"   Expected interval: {expected_interval}")
            else:
                print("   ❌ Next check: NOT SET")
            
            # Gate analysis
            gate = trip.get('gate')
            print(f"   Gate: {gate if gate else 'NULL (will fetch on boarding)'}")
            
            # Metadata analysis
            metadata = trip.get('metadata', {})
            flight_details = metadata.get('flight_details', {})
            metadata_gate = flight_details.get('gate')
            if metadata_gate:
                print(f"   Metadata gate: {metadata_gate}")
            
            # Status
            print(f"   Status: {trip.get('status')}")
            print(f"   Estimated arrival: {trip.get('estimated_arrival', 'Not set')}")
        
        print(f"\n📊 SCHEDULER STATUS:")
        print(f"   Unified polling: EVERY 5 MINUTES")
        print(f"   24h reminders: DAILY AT 9:00 AM")
        print(f"   Boarding notifications: EVERY 5 MINUTES") 
        print(f"   Landing detection: EVERY 30 MINUTES")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(check_trips_status()) 