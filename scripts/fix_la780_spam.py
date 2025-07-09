#!/usr/bin/env python3
"""
🚨 SPECIFIC FIX: Stop LA780 cancellation spam immediately.
This script addresses the specific LA780 issue causing repeated cancellation notifications.
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

async def fix_la780_spam():
    """Fix LA780 specific spam issue"""
    
    print("🚨 FIXING LA780 SPAM ISSUE")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    
    try:
        now_utc = datetime.now(timezone.utc)
        print(f"Current time UTC: {now_utc.isoformat()}")
        
        # 1. Find all LA780 trips
        print(f"\n1️⃣ FINDING LA780 TRIPS...")
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={
                "flight_number": "eq.LA780",
                "select": "*"
            }
        )
        response.raise_for_status()
        la780_trips = response.json()
        
        print(f"   Found {len(la780_trips)} LA780 trips")
        
        if not la780_trips:
            print("   ❌ No LA780 trips found!")
            return
        
        # 2. Analyze each LA780 trip
        for trip_data in la780_trips:
            print(f"\n🛫 LA780 TRIP ANALYSIS:")
            print(f"   Trip ID: {trip_data['id']}")
            print(f"   Client: {trip_data['client_name']}")
            print(f"   WhatsApp: {trip_data['whatsapp']}")
            print(f"   Departure: {trip_data['departure_date']}")
            print(f"   Status: {trip_data.get('status', 'NULL')}")
            print(f"   Next Check: {trip_data.get('next_check_at', 'NULL')}")
            
            # Parse departure date
            departure_str = trip_data["departure_date"]
            if departure_str.endswith('Z'):
                departure_dt = datetime.fromisoformat(departure_str.replace('Z', '+00:00'))
            else:
                departure_dt = datetime.fromisoformat(departure_str)
                if departure_dt.tzinfo is None:
                    departure_dt = departure_dt.replace(tzinfo=timezone.utc)
            
            hours_until_departure = (departure_dt - now_utc).total_seconds() / 3600
            print(f"   Hours until departure: {hours_until_departure:.1f}h")
            
            # 3. Determine correct action based on departure time
            if departure_dt < now_utc:
                # Flight has already departed
                print(f"   🛫 FLIGHT ALREADY DEPARTED")
                
                # Set to landing detection mode (check arrival time)
                # LA780 SCL->GIG is about 4 hours
                estimated_arrival = departure_dt + timedelta(hours=4)
                
                if estimated_arrival < now_utc:
                    # Should have landed already
                    print(f"   🛬 SHOULD HAVE LANDED - Setting to LANDED status")
                    
                    # Update to LANDED and remove from polling
                    update_data = {
                        "status": "LANDED",
                        "next_check_at": None
                    }
                    
                    response = await db_client._client.patch(
                        f"{db_client.rest_url}/trips",
                        json=update_data,
                        params={"id": f"eq.{trip_data['id']}"}
                    )
                    response.raise_for_status()
                    print(f"   ✅ Updated to LANDED - REMOVED FROM POLLING")
                else:
                    # Still in flight, check at arrival time
                    print(f"   ✈️  STILL IN FLIGHT - Setting check at arrival time")
                    
                    update_data = {
                        "next_check_at": estimated_arrival.isoformat()
                    }
                    
                    response = await db_client._client.patch(
                        f"{db_client.rest_url}/trips",
                        json=update_data,
                        params={"id": f"eq.{trip_data['id']}"}
                    )
                    response.raise_for_status()
                    print(f"   ✅ Next check set to: {estimated_arrival.isoformat()}")
            else:
                # Future flight, set intelligent polling
                print(f"   📅 FUTURE FLIGHT - Setting intelligent polling")
                
                correct_next_check = calculate_unified_next_check(
                    departure_time=departure_dt,
                    now_utc=now_utc,
                    current_status="SCHEDULED"
                )
                
                if correct_next_check:
                    hours_to_next_check = (correct_next_check - now_utc).total_seconds() / 3600
                    print(f"   🔧 Setting next check in {hours_to_next_check:.1f}h")
                    
                    update_data = {
                        "next_check_at": correct_next_check.isoformat()
                    }
                    
                    response = await db_client._client.patch(
                        f"{db_client.rest_url}/trips",
                        json=update_data,
                        params={"id": f"eq.{trip_data['id']}"}
                    )
                    response.raise_for_status()
                    print(f"   ✅ Next check set to: {correct_next_check.isoformat()}")
                else:
                    print(f"   ⚠️  Very far future - no immediate polling needed")
        
        # 4. Check notifications log for LA780 spam
        print(f"\n2️⃣ CHECKING NOTIFICATION SPAM...")
        
        # Get recent notifications for LA780 trips
        for trip_data in la780_trips:
            response = await db_client._client.get(
                f"{db_client.rest_url}/notifications_log",
                params={
                    "trip_id": f"eq.{trip_data['id']}",
                    "notification_type": "eq.CANCELLED",
                    "select": "sent_at,delivery_status,notification_type",
                    "order": "sent_at.desc",
                    "limit": "10"
                }
            )
            response.raise_for_status()
            notifications = response.json()
            
            if notifications:
                print(f"   🚨 SPAM DETECTED for Trip {trip_data['id']}:")
                print(f"      {len(notifications)} CANCELLED notifications found")
                for notif in notifications[:5]:  # Show last 5
                    print(f"      - {notif['sent_at']}: {notif['notification_type']} ({notif['delivery_status']})")
                
                if len(notifications) > 5:
                    print(f"      ... and {len(notifications) - 5} more")
            else:
                print(f"   ✅ No spam notifications for Trip {trip_data['id']}")
        
        # 5. Verify fix
        print(f"\n3️⃣ VERIFYING FIX...")
        
        # Check if any LA780 trips are still in polling queue
        trips_to_poll = await db_client.get_trips_to_poll(now_utc)
        la780_in_poll = [trip for trip in trips_to_poll if trip.flight_number == "LA780"]
        
        if la780_in_poll:
            print(f"   ⚠️  {len(la780_in_poll)} LA780 trips still in polling queue:")
            for trip in la780_in_poll:
                print(f"      - {trip.id} ({trip.client_name})")
        else:
            print(f"   ✅ SUCCESS: No LA780 trips in immediate polling queue!")
        
        print(f"\n🎉 LA780 SPAM FIX COMPLETED!")
        print(f"   - Set departed flights to LANDED or arrival-time polling")
        print(f"   - Set future flights to intelligent polling intervals")
        print(f"   - LA780 spam should be STOPPED immediately!")
        
    except Exception as e:
        print(f"❌ LA780 fix failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(fix_la780_spam()) 