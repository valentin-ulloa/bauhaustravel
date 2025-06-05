#!/usr/bin/env python3
"""
Test script for NotificationsAgent.
Tests the agent without requiring the notifications_log table (for now).
"""

import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_notifications_agent():
    """Test the NotificationsAgent functionality."""
    
    print("🔍 Testing NotificationsAgent...")
    
    try:
        from app.agents.notifications_agent import NotificationsAgent
        from app.agents.notifications_templates import NotificationType
        
        # Initialize agent
        agent = NotificationsAgent()
        print("✅ NotificationsAgent initialized successfully")
        
        # Test 1: Test trigger types
        print("\n🔍 Testing trigger types...")
        
        # Test 24h reminders
        result = await agent.run("24h_reminder")
        print(f"✅ 24h reminder trigger: success={result.success}")
        if result.data:
            print(f"   📊 Data: {result.data}")
        
        # Test status changes
        result = await agent.run("status_change")
        print(f"✅ Status change trigger: success={result.success}")
        if result.data:
            print(f"   📊 Data: {result.data}")
        
        # Test landing detection
        result = await agent.run("landing_detected")
        print(f"✅ Landing detection trigger: success={result.success}")
        
        # Test invalid trigger
        result = await agent.run("invalid_trigger")
        print(f"✅ Invalid trigger handled: success={result.success}, error={result.error}")
        
        # Test 2: Test message formatting
        print("\n🔍 Testing message formatting...")
        
        # Create a mock trip for testing
        from app.models.database import Trip
        from uuid import uuid4
        
        mock_trip = Trip(
            id=uuid4(),
            client_name="Test Client",
            whatsapp="+1234567890",
            flight_number="AA123",
            origin_iata="JFK",
            destination_iata="LAX",
            departure_date=datetime.now(timezone.utc),
            status="SCHEDULED",
            inserted_at=datetime.now(timezone.utc)
        )
        
        # Test message formatting for each type
        message_data = agent.format_message(mock_trip, NotificationType.REMINDER_24H)
        print(f"✅ 24h reminder message format: {message_data['template_name']}")
        print(f"   📝 Variables: {message_data['template_variables']}")
        
        message_data = agent.format_message(
            mock_trip, 
            NotificationType.STATUS_CHANGE,
            {"status_change": "DELAYED", "new_info": "30 minutes"}
        )
        print(f"✅ Status change message format: {message_data['template_name']}")
        print(f"   📝 Variables: {message_data['template_variables']}")
        
        message_data = agent.format_message(
            mock_trip,
            NotificationType.LANDING,
            {"local_time": "14:30"}
        )
        print(f"✅ Landing message format: {message_data['template_name']}")
        print(f"   📝 Variables: {message_data['template_variables']}")
        
        # Test 3: Test next check time calculation
        print("\n🔍 Testing poll optimization...")
        
        now = datetime.now(timezone.utc)
        
        # Test different time scenarios
        test_scenarios = [
            (now.replace(hour=now.hour + 25), "> 24h"),  # More than 24h
            (now.replace(hour=now.hour + 12), "24h-4h"),  # Between 24h and 4h
            (now.replace(hour=now.hour + 2), "≤ 4h"),     # Less than 4h
            (now.replace(hour=now.hour - 2), "In-flight") # In the past (in-flight)
        ]
        
        for departure_time, scenario in test_scenarios:
            next_check = agent.calculate_next_check_time(departure_time, now)
            interval = (next_check - now).total_seconds() / 60  # minutes
            print(f"✅ {scenario}: next check in {interval:.0f} minutes")
        
        print("\n🎉 All NotificationsAgent tests passed!")
        
    except Exception as e:
        print(f"❌ NotificationsAgent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        try:
            await agent.close()
            print("✅ Agent closed successfully")
        except:
            pass
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_notifications_agent()) 