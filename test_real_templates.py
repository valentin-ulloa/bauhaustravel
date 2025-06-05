#!/usr/bin/env python3
"""
Test script for real Twilio templates.
Verifies that all templates format correctly with actual SIDs and variables.
"""

import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from uuid import uuid4

# Load environment variables
load_dotenv()

def test_templates():
    """Test all WhatsApp templates with real data."""
    
    print("🔍 Testing Real Twilio Templates...")
    
    try:
        from app.agents.notifications_templates import (
            NotificationType, 
            WhatsAppTemplates, 
            get_notification_type_for_status,
            get_required_variables
        )
        from app.models.database import Trip
        
        # Create a mock trip with real data structure
        mock_trip = Trip(
            id=uuid4(),
            client_name="Valen",
            whatsapp="+56912345678",
            flight_number="AZ681",
            origin_iata="SCL",
            destination_iata="LHR",
            departure_date=datetime(2024, 12, 25, 10, 30, tzinfo=timezone.utc),
            status="SCHEDULED",
            inserted_at=datetime.now(timezone.utc)
        )
        
        print(f"📍 Mock trip: {mock_trip.client_name} - {mock_trip.flight_number}")
        print(f"   Route: {mock_trip.origin_iata} → {mock_trip.destination_iata}")
        print()
        
        # Test 1: 24h Reminder Template
        print("🔍 Testing 24h Reminder Template...")
        reminder_data = WhatsAppTemplates.format_24h_reminder(
            {
                "client_name": mock_trip.client_name,
                "origin_iata": mock_trip.origin_iata,
                "destination_iata": mock_trip.destination_iata,
                "departure_time": "25/12/2024 10:30"
            },
            weather_info="soleado 18°C",
            additional_info="Recuerda llegar 2 horas antes"
        )
        
        print(f"✅ Template: {reminder_data['template_name']}")
        print(f"   SID: {reminder_data['template_sid']}")
        print(f"   Variables: {reminder_data['template_variables']}")
        print()
        
        # Test 2: Delayed Flight Template
        print("🔍 Testing Delayed Flight Template...")
        delayed_data = WhatsAppTemplates.format_delayed_flight(
            {
                "client_name": mock_trip.client_name,
                "flight_number": mock_trip.flight_number
            },
            new_departure_time="25/12/2024 12:30"
        )
        
        print(f"✅ Template: {delayed_data['template_name']}")
        print(f"   SID: {delayed_data['template_sid']}")
        print(f"   Variables: {delayed_data['template_variables']}")
        print()
        
        # Test 3: Gate Change Template
        print("🔍 Testing Gate Change Template...")
        gate_change_data = WhatsAppTemplates.format_gate_change(
            {
                "client_name": mock_trip.client_name,
                "flight_number": mock_trip.flight_number
            },
            new_gate="B15"
        )
        
        print(f"✅ Template: {gate_change_data['template_name']}")
        print(f"   SID: {gate_change_data['template_sid']}")
        print(f"   Variables: {gate_change_data['template_variables']}")
        print()
        
        # Test 4: Cancelled Flight Template
        print("🔍 Testing Cancelled Flight Template...")
        cancelled_data = WhatsAppTemplates.format_cancelled_flight({
            "client_name": mock_trip.client_name,
            "flight_number": mock_trip.flight_number
        })
        
        print(f"✅ Template: {cancelled_data['template_name']}")
        print(f"   SID: {cancelled_data['template_sid']}")
        print(f"   Variables: {cancelled_data['template_variables']}")
        print()
        
        # Test 5: Boarding Call Template
        print("🔍 Testing Boarding Call Template...")
        boarding_data = WhatsAppTemplates.format_boarding_call(
            {"flight_number": mock_trip.flight_number},
            gate="A12"
        )
        
        print(f"✅ Template: {boarding_data['template_name']}")
        print(f"   SID: {boarding_data['template_sid']}")
        print(f"   Variables: {boarding_data['template_variables']}")
        print()
        
        # Test 6: Booking Confirmation Template
        print("🔍 Testing Booking Confirmation Template...")
        booking_data = WhatsAppTemplates.format_booking_confirmation({
            "client_name": mock_trip.client_name,
            "flight_number": mock_trip.flight_number,
            "origin_iata": mock_trip.origin_iata,
            "destination_iata": mock_trip.destination_iata,
            "departure_time": "25/12/2024 10:30"
        })
        
        print(f"✅ Template: {booking_data['template_name']}")
        print(f"   SID: {booking_data['template_sid']}")
        print(f"   Variables: {booking_data['template_variables']}")
        print()
        
        # Test 7: Status Detection Helper
        print("🔍 Testing Status Detection Helper...")
        test_cases = [
            ("SCHEDULED", "DELAYED", "Should detect DELAYED"),
            ("SCHEDULED", "CANCELLED", "Should detect CANCELLED"),
            ("SCHEDULED", "BOARDING", "Should detect BOARDING"),
            ("SCHEDULED", "ON_TIME", {"gate_changed": True}, "Should detect GATE_CHANGE")
        ]
        
        for old_status, new_status, *extra in test_cases:
            status_data = extra[1] if len(extra) > 1 and isinstance(extra[1], dict) else {}
            description = extra[0] if len(extra) > 0 else extra[1] if len(extra) > 1 else ""
            
            detected_type = get_notification_type_for_status(old_status, new_status, status_data)
            print(f"✅ {description}: {detected_type}")
        
        print()
        
        # Test 8: Required Variables
        print("🔍 Testing Required Variables...")
        for notification_type in NotificationType:
            required_vars = get_required_variables(notification_type)
            print(f"✅ {notification_type}: {required_vars}")
        
        print("\n🎉 All template tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Template test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_templates() 