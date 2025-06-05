#!/usr/bin/env python3
"""Test script to verify DatabaseResult dict compliance."""

import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.models.database import TripCreate, DatabaseResult
from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType

async def test_database_result_compliance():
    """Test that all DatabaseResult instances return proper dict data."""
    
    print("🧪 Testing DatabaseResult dict compliance...")
    
    # Test data
    test_trip = TripCreate(
        client_name="Test User",
        whatsapp="+1234567890",
        flight_number="TEST123",
        origin_iata="JFK",
        destination_iata="LAX",
        departure_date=datetime.now(timezone.utc).replace(hour=14, minute=30)
    )
    
    db_client = SupabaseDBClient()
    
    try:
        print("\n1️⃣ Testing create_trip() DatabaseResult...")
        
        # Test create_trip
        create_result = await db_client.create_trip(test_trip)
        
        if create_result.success:
            print("✅ create_trip() successful")
            print(f"📄 Data type: {type(create_result.data)}")
            print(f"📄 Data is dict: {isinstance(create_result.data, dict)}")
            
            if isinstance(create_result.data, dict):
                print(f"📄 Trip ID: {create_result.data.get('id')}")
                trip_id = create_result.data["id"]
                
                print("\n2️⃣ Testing get_trip_by_id() DatabaseResult...")
                
                # Test get_trip_by_id
                get_result = await db_client.get_trip_by_id(trip_id)
                
                if get_result.success:
                    print("✅ get_trip_by_id() successful")
                    print(f"📄 Data type: {type(get_result.data)}")
                    print(f"📄 Data is dict: {isinstance(get_result.data, dict)}")
                    
                    print("\n3️⃣ Testing NotificationsAgent.send_single_notification()...")
                    
                    # Test notifications agent
                    agent = NotificationsAgent()
                    
                    notification_result = await agent.send_single_notification(
                        trip_id=trip_id,
                        notification_type=NotificationType.RESERVATION_CONFIRMATION
                    )
                    
                    if notification_result.success:
                        print("✅ send_single_notification() successful")
                        print(f"📄 Message SID: {notification_result.data.get('message_sid') if notification_result.data else 'N/A'}")
                    else:
                        print(f"❌ send_single_notification() failed: {notification_result.error}")
                    
                    await agent.close()
                else:
                    print(f"❌ get_trip_by_id() failed: {get_result.error}")
            else:
                print("❌ create_trip() returned non-dict data!")
        else:
            print(f"❌ create_trip() failed: {create_result.error}")
    
    except Exception as e:
        print(f"💥 Test error: {e}")
    
    finally:
        await db_client.close()
    
    print("\n🎯 DatabaseResult compliance test completed!")

if __name__ == "__main__":
    asyncio.run(test_database_result_compliance()) 