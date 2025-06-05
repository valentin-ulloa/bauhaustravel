#!/usr/bin/env python3
"""Test script for the new send_single_notification method."""

import asyncio
import os
from uuid import UUID
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType

async def test_single_notification():
    """Test the new send_single_notification method."""
    
    # Test with the known trip ID from our database
    test_trip_id = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")  # Replace with actual trip ID
    
    # Initialize agent
    agent = NotificationsAgent()
    
    try:
        print("🧪 Testing send_single_notification method...")
        
        # Test reservation confirmation
        result = await agent.send_single_notification(
            trip_id=test_trip_id,
            notification_type=NotificationType.RESERVATION_CONFIRMATION
        )
        
        if result.success:
            print("✅ Reservation confirmation sent successfully!")
            print(f"📄 Message SID: {result.data.get('message_sid') if result.data else 'N/A'}")
        else:
            print(f"❌ Failed to send reservation confirmation: {result.error}")
        
        # Test with different notification type
        print("\n🧪 Testing 24h reminder...")
        result2 = await agent.send_single_notification(
            trip_id=test_trip_id,
            notification_type=NotificationType.REMINDER_24H,
            extra_data={"weather_info": "clima soleado", "additional_info": "¡Disfruta tu viaje!"}
        )
        
        if result2.success:
            print("✅ 24h reminder sent successfully!")
            print(f"📄 Message SID: {result2.data.get('message_sid') if result2.data else 'N/A'}")
        else:
            print(f"❌ Failed to send 24h reminder: {result2.error}")
        
    except Exception as e:
        print(f"💥 Test error: {e}")
    
    finally:
        await agent.close()

if __name__ == "__main__":
    print("🚀 Starting single notification test...")
    print("📋 Available notification types:")
    for nt in NotificationType:
        print(f"   - {nt.value}")
    print()
    
    asyncio.run(test_single_notification()) 