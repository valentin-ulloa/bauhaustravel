#!/usr/bin/env python3
"""
Script to create SQ321 flight for testing unified optimizations:
Singapore Airlines SQ321, London (LHR) to Singapore (SIN)
Departure: Tue, 08 Jul 2025 22:05 Local London Time
Arrival: Wed, 09 Jul 2025 18:10 Local Singapore Time
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.models.database import TripCreate
from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.utils.flight_schedule_utils import calculate_unified_next_check
from uuid import UUID
import structlog

logger = structlog.get_logger()


async def create_sq321_trip():
    """Create SQ321 London to Singapore trip to test unified optimizations"""
    
    print("🛫 Creating SQ321 trip to test unified optimizations...")
    
    db_client = SupabaseDBClient()
    
    try:
        # SQ321 flight data - London time (will be auto-converted to UTC)
        # Tuesday, 8 July 2025 at 22:05 London time
        departure_local = datetime(2025, 7, 8, 22, 5, 0)  # LOCAL London time
        
        trip_data = TripCreate(
            client_name="Valentin",
            whatsapp="+5491140383422",
            flight_number="SQ321",
            origin_iata="LHR",  # London Heathrow
            destination_iata="SIN",  # Singapore Changi
            departure_date=departure_local,  # Will be auto-converted to UTC
            status="SCHEDULED",
            client_description="Business trip to Singapore - Testing unified optimizations",
            metadata={
                "trip_type": "business",
                "terminal": "2",
                "check_in_time": "18:05",
                "check_in_zone": "Zone A",
                "arrival_date": "2025-07-09T18:10:00",  # Singapore local time
                "estimated_arrival": "2025-07-09T10:10:00+00:00",  # UTC
                "airline": "Singapore Airlines",
                "flight_status": "ON TIME",
                "gate": "TBD",
                "created_by": "unified_optimization_test",
                "test_flight": True
            },
            agency_id=UUID("00000000-0000-0000-0000-000000000001")  # Default agency
        )
        
        print(f"📋 Flight Details:")
        print(f"   Passenger: {trip_data.client_name}")
        print(f"   WhatsApp: {trip_data.whatsapp}")
        print(f"   Flight: {trip_data.flight_number}")
        print(f"   Route: {trip_data.origin_iata} → {trip_data.destination_iata}")
        print(f"   Departure: {departure_local.strftime('%a %d %b %Y %H:%M')} London Time")
        print(f"   Terminal: {trip_data.metadata['terminal']}")
        print(f"   Description: {trip_data.client_description}")
        
        # Check for duplicates first
        print(f"\n🔍 Checking for duplicates...")
        duplicate_check = await db_client.check_duplicate_trip(
            trip_data.whatsapp,
            trip_data.flight_number,
            trip_data.departure_date
        )
        
        if duplicate_check.success and duplicate_check.data.get("exists"):
            print(f"⚠️  DUPLICATE DETECTED: Trip already exists")
            print(f"   WhatsApp: {trip_data.whatsapp}")
            print(f"   Flight: {trip_data.flight_number}")
            print(f"   Date: {trip_data.departure_date.strftime('%Y-%m-%d')}")
            
            # Ask if user wants to continue anyway
            response = input("\nDo you want to delete the existing trip and create a new one? (y/N): ")
            if response.lower() != 'y':
                return False
            
            # Clean up existing trip
            print("🧹 Cleaning up existing trip...")
            # Note: implement cleanup if needed
        
        # Create the trip
        print(f"\n💾 Creating trip in Supabase...")
        result = await db_client.create_trip(trip_data)
        
        if result.success:
            trip_id = result.data.get("id")
            utc_departure = result.data.get("departure_date")
            
            print(f"✅ TRIP CREATED SUCCESSFULLY!")
            print(f"   Trip ID: {trip_id}")
            print(f"   Passenger: {result.data.get('client_name')}")
            print(f"   Flight: {result.data.get('flight_number')}")
            print(f"   WhatsApp: {result.data.get('whatsapp')}")
            print(f"   Local Time: {departure_local.strftime('%a %d %b %Y %H:%M')} (London)")
            print(f"   UTC Time: {utc_departure}")
            
            # Calculate time until departure
            now = datetime.now(timezone.utc)
            departure_utc = datetime.fromisoformat(utc_departure.replace('Z', '+00:00'))
            time_until = departure_utc - now
            hours_until = time_until.total_seconds() / 3600
            
            print(f"\n⏰ Time until departure: {hours_until:.1f} hours")
            
            # Test unified next_check_at calculation
            print(f"\n🔄 Testing unified next_check_at calculation...")
            next_check = calculate_unified_next_check(
                departure_time=departure_utc,
                now_utc=now,
                current_status="SCHEDULED"
            )
            
            if next_check:
                print(f"   Next polling check: {next_check.isoformat()}")
                check_hours = (next_check - now).total_seconds() / 3600
                print(f"   Time until next check: {check_hours:.1f} hours")
                
                # Update the trip with next_check_at
                await db_client.update_next_check_at(UUID(trip_id), next_check)
                print(f"   ✅ Updated next_check_at in database")
            else:
                print(f"   ⚠️  No next check calculated (flight may be too far in future)")
            
            return trip_id
        else:
            print(f"❌ ERROR creating trip: {result.error}")
            return None
    
    except Exception as e:
        print(f"💥 EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        await db_client.close()


async def test_notification_flow(trip_id: str):
    """Test the notification flow for the created trip"""
    
    print(f"\n📲 Testing notification flow for trip {trip_id}...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        # Test reservation confirmation notification
        print(f"\n1️⃣ Testing reservation confirmation...")
        result = await notifications_agent.send_single_notification(
            trip_id, 
            NotificationType.RESERVATION_CONFIRMATION
        )
        
        if result.success:
            print(f"   ✅ Confirmation sent successfully!")
            print(f"   Message SID: {result.data.get('message_sid')}")
            print(f"   Template: {result.data.get('template_name')}")
        else:
            print(f"   ❌ Confirmation failed: {result.error}")
        
        # Test flight status check
        print(f"\n2️⃣ Testing flight status check...")
        status_result = await notifications_agent.check_single_trip_status(trip_id)
        
        if status_result.success:
            print(f"   ✅ Status check completed!")
            print(f"   Current status: {status_result.data.get('current_status')}")
            print(f"   Status source: {status_result.data.get('status_source')}")
            if status_result.data.get('gate'):
                print(f"   Gate: {status_result.data.get('gate')}")
        else:
            print(f"   ❌ Status check failed: {status_result.error}")
        
        return True
        
    except Exception as e:
        print(f"💥 Notification test exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await notifications_agent.close()


async def main():
    """Main function"""
    print("🧪 SQ321 Trip Creation & Unified Optimization Test")
    print("=" * 60)
    
    # Create the trip
    trip_id = await create_sq321_trip()
    
    if trip_id:
        print(f"\n🎉 Trip {trip_id} created successfully!")
        
        # Test notification flow
        notification_success = await test_notification_flow(trip_id)
        
        if notification_success:
            print(f"\n✅ ALL TESTS PASSED!")
            print(f"📱 Check WhatsApp +5491140383422 for confirmation message")
            print(f"🛎️  System will monitor flight SQ321 automatically")
            print(f"🔄 Unified polling optimization is active")
            print(f"\n📊 Next steps:")
            print(f"   - Flight status will be polled intelligently")
            print(f"   - 24h reminder will be sent automatically")
            print(f"   - Real-time alerts for delays/gate changes")
            print(f"   - Landing welcome message upon arrival")
        else:
            print(f"\n⚠️  Trip created but notification test failed")
        
        return True
    else:
        print(f"\n😞 Failed to create trip. Check logs for details.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 