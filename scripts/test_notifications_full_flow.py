#!/usr/bin/env python3
"""
Comprehensive test for TC-001 NotificationsAgent.

Tests:
1. ✅ Reservation confirmation (already working)
2. 🧪 24h reminder detection 
3. 🧪 Flight status polling with AeroAPI
4. 🧪 Change detection logic
5. 🧪 Notification sending with templates
6. 🧪 Database logging verification

Configuration:
- SEND_REAL_MESSAGES = False (safe testing - no actual WhatsApp sends)
- TEST_WHATSAPP_NUMBER env variable for custom test number

Usage:
    python scripts/test_notifications_full_flow.py [trip_id]
    
    # To send real WhatsApp messages, edit SEND_REAL_MESSAGES = True
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.agents.notifications_agent import NotificationsAgent, NotificationType
from app.db.supabase_client import SupabaseDBClient
from app.services.aeroapi_client import AeroAPIClient, FlightStatus
from app.models.database import Trip, TripCreate
import structlog

logger = structlog.get_logger()

# Test configuration
SEND_REAL_MESSAGES = False  # Set to True to send actual WhatsApp messages
TEST_WHATSAPP = os.getenv("TEST_WHATSAPP_NUMBER", "+5491140383422")


async def create_test_trip() -> Trip:
    """Create a test trip for validation"""
    print("🚀 Creating test trip...")
    
    db_client = SupabaseDBClient()
    
    # Create trip departing in 23 hours (should trigger 24h reminder)
    departure_time = datetime.now(timezone.utc) + timedelta(hours=23)
    
    trip_data = TripCreate(
        client_name="Test NotificationsAgent",
        whatsapp=TEST_WHATSAPP,
        flight_number="AR1306",     # Real Aerolíneas Argentinas flight
        origin_iata="EZE",
        destination_iata="GRU",
        departure_date=departure_time,
        status="SCHEDULED",
        client_description="Test flight for TC-001 validation"
    )
    
    result = await db_client.create_trip(trip_data)
    
    if result.success:
        trip = Trip(**result.data)
        print(f"✅ Test trip created: {trip.id}")
        print(f"   Flight: {trip.flight_number}")
        print(f"   Departure: {trip.departure_date.isoformat()}")
        print(f"   Next check: {trip.next_check_at}")
        await db_client.close()
        return trip
    else:
        print(f"❌ Failed to create test trip: {result.error}")
        await db_client.close()
        return None


async def test_flight_status_polling(trip: Trip):
    """Test flight status polling logic"""
    print(f"\n🔍 Testing flight status polling for {trip.flight_number}...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        # Get current flight status
        departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
        current_status = await notifications_agent.aeroapi_client.get_flight_status(
            trip.flight_number, 
            departure_date_str
        )
        
        if current_status:
            print(f"✅ Flight status retrieved from AeroAPI:")
            print(f"   Status: {current_status.status}")
            print(f"   Gate: {current_status.gate_origin or 'Not assigned'}")
            print(f"   Est. departure: {current_status.estimated_out or 'N/A'}")
            print(f"   Cancelled: {current_status.cancelled}")
            print(f"   Delayed: {current_status.departure_delay} min")
            
            # Test change detection
            print(f"\n🔍 Testing change detection...")
            
            # Create mock previous status for comparison
            previous_status = FlightStatus(
                ident=trip.flight_number,
                status="Scheduled",
                gate_origin="A10",  # Different gate to test change detection
                estimated_out=trip.departure_date.isoformat()
            )
            
            changes = notifications_agent.aeroapi_client.detect_flight_changes(
                current_status, previous_status
            )
            
            print(f"✅ Detected {len(changes)} changes:")
            for change in changes:
                print(f"   - {change['type']}: {change['old_value']} → {change['new_value']}")
                print(f"     Notification: {change['notification_type']}")
            
            return current_status, changes
        else:
            print(f"❌ No flight status available for {trip.flight_number}")
            return None, []
            
    except Exception as e:
        print(f"❌ Error during flight polling: {e}")
        return None, []
    finally:
        await notifications_agent.close()


async def test_24h_reminder(trip: Trip):
    """Test 24h reminder logic"""
    print(f"\n⏰ Testing 24h reminder logic...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        # Check if trip is in 24h window
        now_utc = datetime.now(timezone.utc)
        time_until_departure = trip.departure_date - now_utc
        hours_until = time_until_departure.total_seconds() / 3600
        
        print(f"   Hours until departure: {hours_until:.1f}")
        
        if 23 <= hours_until <= 25:
            print(f"✅ Trip is in 24h reminder window")
            
            # Check if reminder already sent
            db_client = SupabaseDBClient()
            history = await db_client.get_notification_history(
                trip.id, NotificationType.REMINDER_24H.value
            )
            
            sent_reminders = [log for log in history if log.delivery_status == "SENT"]
            
            if sent_reminders:
                print(f"⚠️  24h reminder already sent ({len(sent_reminders)} times)")
                for reminder in sent_reminders:
                    print(f"   - Sent at: {reminder.sent_at}")
            else:
                print(f"✅ No 24h reminder sent yet - would send now")
                
                if SEND_REAL_MESSAGES:
                    print(f"   🚀 Sending actual 24h reminder...")
                    result = await notifications_agent.send_notification(
                        trip, NotificationType.REMINDER_24H
                    )
                    print(f"   📱 Send result: {result.success}")
                    if result.error:
                        print(f"   ❌ Error: {result.error}")
                else:
                    print(f"   ℹ️  SEND_REAL_MESSAGES=False - skipping actual send")
            
            await db_client.close()
        else:
            print(f"ℹ️  Trip not in 24h window (need 23-25h, got {hours_until:.1f}h)")
            
    except Exception as e:
        print(f"❌ Error testing 24h reminder: {e}")
    finally:
        await notifications_agent.close()


async def test_change_notification_sending(trip: Trip, changes: list):
    """Test sending change notifications"""
    if not changes:
        print(f"\n⚠️  No changes detected - simulating a delay for testing...")
        changes = [{
            "type": "status_change",
            "old_value": "Scheduled",
            "new_value": "Delayed",
            "notification_type": "delayed"
        }]
    
    print(f"\n📱 Testing change notification sending...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        for change in changes:
            print(f"   Testing {change['type']} notification...")
            
            # Map to notification type
            notification_type = notifications_agent._map_notification_type(
                change["notification_type"]
            )
            
            if notification_type:
                print(f"   ✅ Mapped to: {notification_type}")
                
                # Test message formatting
                extra_data = {
                    "old_value": change["old_value"],
                    "new_value": change["new_value"],
                    "change_type": change["type"]
                }
                
                message_data = notifications_agent.format_message(
                    trip, notification_type, extra_data
                )
                
                print(f"   ✅ Template: {message_data['template_name']}")
                print(f"   ✅ SID: {message_data['template_sid']}")
                print(f"   ✅ Variables: {message_data['template_variables']}")
                
                if SEND_REAL_MESSAGES:
                    print(f"   🚀 Sending notification...")
                    result = await notifications_agent.send_notification(
                        trip, notification_type, extra_data
                    )
                    print(f"   📱 Send result: {result.success}")
                    if result.error:
                        print(f"   ❌ Error: {result.error}")
                else:
                    print(f"   ℹ️  SEND_REAL_MESSAGES=False - skipping actual send")
                
            else:
                print(f"   ❌ Unknown notification type: {change['notification_type']}")
                
    except Exception as e:
        print(f"❌ Error testing notification sending: {e}")
    finally:
        await notifications_agent.close()


async def test_full_polling_cycle(trip: Trip):
    """Test the complete polling cycle as it would run in production"""
    print(f"\n🔄 Testing full polling cycle (as SchedulerService would run)...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        # Run the actual poll_flight_changes method
        result = await notifications_agent.poll_flight_changes()
        
        print(f"✅ Polling completed:")
        print(f"   Success: {result.success}")
        print(f"   Data: {result.data}")
        print(f"   Error: {result.error}")
        
        if result.success and result.data:
            data = result.data
            print(f"   📊 Stats:")
            print(f"      - Trips checked: {data.get('checked', 0)}")
            print(f"      - Notifications sent: {data.get('updates', 0)}")
            print(f"      - Errors: {data.get('errors', 0)}")
            print(f"      - Quiet hours: {data.get('quiet_hours', False)}")
        
    except Exception as e:
        print(f"❌ Error in full polling cycle: {e}")
    finally:
        await notifications_agent.close()


async def verify_notification_logs(trip: Trip):
    """Verify that notifications are properly logged in database"""
    print(f"\n📋 Verifying notification logs...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Get all notification history for this trip
        history = await db_client.get_notification_history(trip.id)
        
        print(f"✅ Found {len(history)} notification records:")
        
        for log in history:
            status_emoji = "✅" if log.delivery_status == "SENT" else "❌" if log.delivery_status == "FAILED" else "⏳"
            print(f"   {status_emoji} {log.notification_type} | {log.sent_at.strftime('%H:%M:%S')}")
            print(f"      Template: {log.template_name}")
            if log.twilio_message_sid:
                print(f"      Twilio SID: {log.twilio_message_sid}")
            if log.error_message:
                print(f"      Error: {log.error_message}")
            print()
                
    except Exception as e:
        print(f"❌ Error verifying logs: {e}")
    finally:
        await db_client.close()


async def main():
    """Main test orchestrator"""
    print("🧪 TC-001 NotificationsAgent Complete Validation")
    print("=" * 60)
    
    # Check if trip_id provided
    trip_id = None
    if len(sys.argv) > 1:
        try:
            trip_id = UUID(sys.argv[1])
            print(f"🎯 Using provided trip ID: {trip_id}")
        except ValueError:
            print(f"❌ Invalid trip ID format: {sys.argv[1]}")
            return
    
    # Get or create test trip
    if trip_id:
        db_client = SupabaseDBClient()
        result = await db_client.get_trip_by_id(trip_id)
        if result.success:
            trip = Trip(**result.data)
            print(f"✅ Using existing trip: {trip.flight_number}")
        else:
            print(f"❌ Trip not found: {trip_id}")
            return
        await db_client.close()
    else:
        trip = await create_test_trip()
        if not trip:
            return
    
    # Run all tests
    print(f"\n📋 Running validation tests for trip {trip.id}...")
    
    # Test 1: Flight status polling
    current_status, changes = await test_flight_status_polling(trip)
    
    # Test 2: 24h reminder logic
    await test_24h_reminder(trip)
    
    # Test 3: Change notification sending
    await test_change_notification_sending(trip, changes)
    
    # Test 4: Full polling cycle
    await test_full_polling_cycle(trip)
    
    # Test 5: Verify database logs
    await verify_notification_logs(trip)
    
    print(f"\n✅ TC-001 validation completed!")
    print(f"🎯 Trip ID for future tests: {trip.id}")


if __name__ == "__main__":
    asyncio.run(main()) 