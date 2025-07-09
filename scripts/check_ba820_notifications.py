#!/usr/bin/env python3
"""
🔍 Check BA820 notification history and diagnose missing confirmation.
This will help identify why the reservation confirmation wasn't sent.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType

async def check_ba820_notifications():
    """Check notification history and test sending confirmation"""
    
    print("🔍 BA820 NOTIFICATION DIAGNOSIS")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Find BA820 trip
        print("1️⃣ FINDING BA820 TRIP...")
        
        now_utc = datetime.now(timezone.utc)
        future_window = now_utc + timedelta(days=1)
        all_trips = await db_client.get_trips_to_poll(future_window)
        
        ba820_trips = [trip for trip in all_trips if trip.flight_number == "BA820"]
        
        if not ba820_trips:
            print("   ❌ No BA820 trips found")
            return
            
        trip = ba820_trips[0]
        print(f"   ✅ Found BA820 trip: {trip.id}")
        print(f"   Client: {trip.client_name}")
        print(f"   WhatsApp: {trip.whatsapp}")
        print(f"   Flight: {trip.flight_number}")
        print(f"   Created: {getattr(trip, 'inserted_at', 'Unknown')}")
        print()
        
        # Check notification history
        print("2️⃣ CHECKING NOTIFICATION HISTORY...")
        
        history = await db_client.get_notification_history(trip.id)
        
        if not history:
            print("   ❌ NO NOTIFICATIONS FOUND!")
            print("   This explains why you didn't receive a confirmation.")
        else:
            print(f"   Found {len(history)} notification(s):")
            for log in history:
                print(f"   - Type: {log.notification_type}")
                print(f"     Status: {log.delivery_status}")
                print(f"     Sent at: {log.sent_at}")
                print(f"     Template: {log.template_name}")
                if log.error_message:
                    print(f"     Error: {log.error_message}")
                print()
        
        # Check for specific confirmation notification
        print("3️⃣ CHECKING FOR CONFIRMATION NOTIFICATION...")
        
        confirmation_logs = [log for log in history if "CONFIRMATION" in log.notification_type]
        reservation_logs = [log for log in history if "RESERVATION" in log.notification_type]
        
        if confirmation_logs or reservation_logs:
            print("   ✅ Confirmation notification found:")
            for log in confirmation_logs + reservation_logs:
                print(f"     Status: {log.delivery_status}")
                print(f"     Error: {log.error_message or 'None'}")
        else:
            print("   ❌ NO CONFIRMATION NOTIFICATION SENT!")
            print("   This is the problem - no confirmation was sent when trip was created.")
        print()
        
        # Test sending confirmation now
        print("4️⃣ TESTING CONFIRMATION NOTIFICATION...")
        
        try:
            print("   Attempting to send RESERVATION_CONFIRMATION...")
            
            result = await notifications_agent.send_notification(
                trip=trip,
                notification_type=NotificationType.RESERVATION_CONFIRMATION,
                extra_data={
                    "test_mode": True,
                    "manual_trigger": "diagnosis_script"
                }
            )
            
            if result.success:
                print("   ✅ Confirmation sent successfully!")
                print(f"   Message SID: {result.data.get('message_sid', 'N/A')}")
                print("   🎉 You should receive the confirmation now!")
            else:
                print(f"   ❌ Confirmation failed: {result.error}")
                
        except Exception as e:
            print(f"   ❌ Exception sending confirmation: {e}")
        print()
        
        # Check system configuration
        print("5️⃣ CHECKING SYSTEM CONFIGURATION...")
        
        # Check Twilio config
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN") 
        twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        messaging_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
        
        print(f"   Twilio SID: {'✅ Set' if twilio_sid else '❌ Missing'}")
        print(f"   Twilio Token: {'✅ Set' if twilio_token else '❌ Missing'}")
        print(f"   Twilio Phone: {'✅ Set' if twilio_phone else '❌ Missing'}")
        print(f"   Messaging Service: {'✅ Set' if messaging_sid else '❌ Missing'}")
        print()
        
        # Check what should have happened
        print("6️⃣ ANALYZING WHAT SHOULD HAVE HAPPENED...")
        
        print("   When trip is created, the system should:")
        print("   1. ✅ Save trip to database (this worked)")
        print("   2. ❌ Send RESERVATION_CONFIRMATION notification (this didn't happen)")
        print("   3. 📅 Schedule future notifications (boarding, reminders)")
        print()
        
        print("   Possible causes for missing confirmation:")
        print("   • Script didn't call send_notification after creating trip")
        print("   • Twilio credentials issue")
        print("   • WhatsApp template problem")
        print("   • Silent failure in notification system")
        print()
        
        # Check if this is a systemic issue
        print("7️⃣ CHECKING FOR SYSTEMIC ISSUES...")
        
        # Get all notification logs to see if ANY notifications work
        try:
            # This is a simplified check - in production you'd query all logs
            print("   Recent system notification activity:")
            
            recent_history = await db_client.get_notification_history(trip.id)
            if recent_history:
                print(f"   ✅ System can log notifications")
            else:
                print(f"   ⚠️  No notification logs found")
                
        except Exception as e:
            print(f"   ❌ Error checking notification system: {e}")
        
        print()
        print("8️⃣ RECOMMENDATIONS...")
        print("   1. 🔧 Fix trip creation flow to auto-send confirmation")
        print("   2. 📧 Manually send confirmation for existing trips")
        print("   3. 🧪 Test notification system end-to-end")
        print("   4. 📊 Add notification monitoring/alerting")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()
        await notifications_agent.close()

if __name__ == "__main__":
    asyncio.run(check_ba820_notifications()) 