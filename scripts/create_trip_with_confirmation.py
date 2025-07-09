#!/usr/bin/env python3
"""
✈️ Create trips with COMPLETE flow - includes automatic confirmation.
This script uses the proper router endpoint that sends confirmations automatically.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
import httpx

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.timezone_utils import parse_local_time_to_utc

async def create_trip_complete(
    client_name: str,
    whatsapp: str,
    flight_number: str,
    origin_iata: str,
    destination_iata: str,
    departure_local: datetime,
    arrival_local: datetime = None,
    description: str = None
):
    """
    Create trip using COMPLETE flow with automatic confirmation.
    
    Args:
        client_name: Passenger name
        whatsapp: WhatsApp number (include country code)
        flight_number: Flight number (e.g., "BA820")
        origin_iata: Origin airport code (e.g., "LHR")
        destination_iata: Destination airport code (e.g., "CPH") 
        departure_local: Departure time in origin city's local time
        arrival_local: Arrival time in destination city's local time (optional)
        description: Additional description
    """
    
    print(f"✈️ CREATING {flight_number} TRIP WITH COMPLETE FLOW")
    print("=" * 60)
    
    try:
        # Convert to UTC
        departure_utc = parse_local_time_to_utc(departure_local, origin_iata)
        
        # Prepare trip data for API
        trip_data = {
            "client_name": client_name,
            "whatsapp": whatsapp,
            "flight_number": flight_number,
            "origin_iata": origin_iata,
            "destination_iata": destination_iata,
            "departure_date": departure_utc.isoformat(),
            "status": "ACTIVE",
            "metadata": {
                "source": "complete_script",
                "local_departure": departure_local.strftime("%Y-%m-%d %H:%M"),
                "timezone_origin": origin_iata,
                "created_via": "improved_script"
            },
            "client_description": description or f"Passenger for {flight_number}",
            "agency_id": None
        }
        
        print(f"📋 TRIP DETAILS:")
        print(f"   Client: {client_name}")
        print(f"   WhatsApp: {whatsapp}")
        print(f"   Flight: {flight_number}")
        print(f"   Route: {origin_iata} → {destination_iata}")
        print(f"   Departure: {departure_local} (local) → {departure_utc} (UTC)")
        if arrival_local:
            arrival_utc = parse_local_time_to_utc(arrival_local, destination_iata)
            print(f"   Arrival: {arrival_local} (local) → {arrival_utc} (UTC)")
        print()
        
        # Use the complete API endpoint (localhost during development)
        print("🚀 CALLING COMPLETE API ENDPOINT...")
        
        # Start FastAPI server in background if not running
        # For production, this would be the deployed URL
        api_url = "http://localhost:8000/trips"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(api_url, json=trip_data)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    print("   ✅ TRIP CREATED WITH COMPLETE FLOW!")
                    print(f"   Trip ID: {result.get('trip_id')}")
                    print(f"   Message: {result.get('message')}")
                    print(f"   Confirmation status: {result.get('confirmation_status')}")
                    print()
                    
                    if result.get('success'):
                        print("🎉 SUCCESS: Trip created AND confirmation sent automatically!")
                        return result.get('trip_id')
                    else:
                        print(f"⚠️  Trip created but confirmation issue: {result.get('error')}")
                        return result.get('trip_id')
                        
                else:
                    print(f"   ❌ API Error: {response.status_code}")
                    print(f"   Response: {response.text}")
                    
                    # Fallback to direct database creation
                    print("\n🔄 FALLING BACK TO DIRECT CREATION...")
                    return await create_trip_direct_with_notification(trip_data)
                    
            except httpx.ConnectError:
                print("   ⚠️  Cannot connect to API server")
                print("   💡 Start server with: uvicorn app.main:app --reload")
                print("\n🔄 FALLING BACK TO DIRECT CREATION...")
                return await create_trip_direct_with_notification(trip_data)
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

async def create_trip_direct_with_notification(trip_data):
    """Fallback: Direct creation with manual notification sending"""
    
    from app.db.supabase_client import SupabaseDBClient
    from app.models.database import TripCreate
    from app.agents.notifications_agent import NotificationsAgent
    from app.agents.notifications_templates import NotificationType
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Convert API data to TripCreate model
        departure_date = datetime.fromisoformat(trip_data["departure_date"])
        
        trip_create = TripCreate(
            client_name=trip_data["client_name"],
            whatsapp=trip_data["whatsapp"],
            flight_number=trip_data["flight_number"],
            origin_iata=trip_data["origin_iata"],
            destination_iata=trip_data["destination_iata"],
            departure_date=departure_date,
            status=trip_data["status"],
            metadata=trip_data["metadata"],
            client_description=trip_data["client_description"],
            agency_id=trip_data["agency_id"]
        )
        
        # Create trip
        print("   Creating trip in database...")
        result = await db_client.create_trip(trip_create)
        
        if not result.success:
            print(f"   ❌ Database error: {result.error}")
            return None
        
        trip_id = result.data["id"]
        print(f"   ✅ Trip created: {trip_id}")
        
        # Send confirmation
        print("   Sending confirmation notification...")
        from app.models.database import Trip
        trip = Trip(**result.data)
        
        notification_result = await notifications_agent.send_notification(
            trip=trip,
            notification_type=NotificationType.RESERVATION_CONFIRMATION
        )
        
        if notification_result.success:
            print(f"   ✅ Confirmation sent! SID: {notification_result.data.get('message_sid')}")
        else:
            print(f"   ❌ Confirmation failed: {notification_result.error}")
        
        print("\n🎉 DIRECT CREATION COMPLETED!")
        return trip_id
        
    except Exception as e:
        print(f"   ❌ Direct creation error: {e}")
        return None
    
    finally:
        await db_client.close()
        await notifications_agent.close()

async def create_ba820_example():
    """Example: Create BA820 trip with complete flow"""
    
    # BA820 details (same as before)
    return await create_trip_complete(
        client_name="Valentin",
        whatsapp="+5491140383422",
        flight_number="BA820",
        origin_iata="LHR",
        destination_iata="CPH", 
        departure_local=datetime(2025, 7, 9, 16, 20),  # London time
        arrival_local=datetime(2025, 7, 9, 19, 15),    # Copenhagen time
        description="Test passenger with complete confirmation flow"
    )

if __name__ == "__main__":
    print("🎯 CHOOSE AN OPTION:")
    print("1. Create BA820 example trip")
    print("2. Create custom trip")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        trip_id = asyncio.run(create_ba820_example())
    elif choice == "2":
        print("\n📝 Enter trip details:")
        client_name = input("Client name: ")
        whatsapp = input("WhatsApp (with country code): ")
        flight_number = input("Flight number: ")
        origin_iata = input("Origin airport code: ")
        destination_iata = input("Destination airport code: ")
        
        print("Departure date/time (origin local time):")
        date_str = input("Date (YYYY-MM-DD): ")
        time_str = input("Time (HH:MM): ")
        departure_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        
        trip_id = asyncio.run(create_trip_complete(
            client_name, whatsapp, flight_number, 
            origin_iata, destination_iata, departure_local
        ))
    else:
        print("Invalid choice")
        trip_id = None
    
    if trip_id:
        print(f"\n✅ SUCCESS! Trip ID: {trip_id}")
        print("🎉 Confirmation should have been sent automatically!")
    else:
        print("\n❌ Trip creation failed") 