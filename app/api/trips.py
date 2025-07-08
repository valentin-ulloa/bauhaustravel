from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from uuid import UUID

router = APIRouter()

@router.post("/create-test-trip")
async def create_test_trip(
    client_name: str = "Test Client",
    whatsapp: str = "+1234567890", 
    flight_number: str = "AA123",
    origin_iata: str = "JFK",
    destination_iata: str = "LAX",
    hours_from_now: int = 25,  # Default 25h for 24h reminder testing
    specific_date: str = None  # Allow override with specific date (YYYY-MM-DD HH:MM format)
):
    """
    Create a test trip for validation purposes.
    
    FIXED: 
    - Adds duplicate validation
    - Sends confirmation notification automatically
    - Supports specific date override
    - Includes complete flight metadata
    """
    try:
        from app.db.supabase_client import SupabaseDBClient
        from app.models.database import TripCreate
        from app.agents.notifications_agent import NotificationsAgent
        from app.agents.notifications_templates import NotificationType
        
        db_client = SupabaseDBClient()
        
        # Calculate departure date
        if specific_date:
            # Parse specific date format: "2025-07-08 22:05"
            try:
                local_departure = datetime.strptime(specific_date, "%Y-%m-%d %H:%M")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD HH:MM")
        else:
            # Use hours_from_now calculation
            base_time = datetime.now() + timedelta(hours=hours_from_now)
            local_departure = base_time.replace(second=0, microsecond=0)
        
        # FIXED: Check for duplicate trips
        duplicate_check = await db_client.check_duplicate_trip(
            whatsapp=whatsapp,
            flight_number=flight_number, 
            departure_date=local_departure
        )
        
        if duplicate_check.success and duplicate_check.data.get("exists"):
            return {
                "success": False,
                "error": "DUPLICATE_TRIP",
                "message": f"Trip already exists for {flight_number} on {local_departure.strftime('%Y-%m-%d')}",
                "existing_count": duplicate_check.data.get("count", 0)
            }
        
        # FIXED: Add complete flight metadata
        flight_metadata = {
            "flight_details": {
                "airline": flight_number[:2],  # Extract airline code
                "departure_terminal": "2" if origin_iata == "LHR" else "1",
                "check_in_time": (local_departure - timedelta(hours=4)).isoformat(),
                "expected_arrival": (local_departure + timedelta(hours=13)).isoformat() if flight_number == "SQ321" else (local_departure + timedelta(hours=6)).isoformat(),
                "aircraft_type": "A350" if flight_number == "SQ321" else "B777"
            },
            "created_via": "test_api",
            "creation_timestamp": datetime.now().isoformat()
        }
        
        # Create TripCreate object
        trip_create = TripCreate(
            client_name=client_name,
            whatsapp=whatsapp,
            flight_number=flight_number,
            origin_iata=origin_iata,
            destination_iata=destination_iata,
            departure_date=local_departure,  # LOCAL TIME - auto-converted to UTC
            agency_id=UUID("00000000-0000-0000-0000-000000000001"),  # Default test agency
            client_description=f"Test flight created via API - {flight_number} on {local_departure.strftime('%Y-%m-%d %H:%M')} local time",
            metadata=flight_metadata  # FIXED: Include complete metadata
        )
        
        # Create trip in database
        result = await db_client.create_trip(trip_create)
        
        if result.success:
            trip_data = result.data
            
            # FIXED: Send confirmation notification automatically
            notifications_agent = NotificationsAgent()
            try:
                # Create Trip object for notification
                from app.models.database import Trip
                trip = Trip(**trip_data)
                
                # Send booking confirmation
                notification_result = await notifications_agent.send_notification(
                    trip=trip,
                    notification_type=NotificationType.RESERVATION_CONFIRMATION
                )
                
                confirmation_sent = notification_result.success
                confirmation_error = None if notification_result.success else notification_result.error
                
            except Exception as notif_error:
                confirmation_sent = False
                confirmation_error = str(notif_error)
            finally:
                await notifications_agent.close()
            
            # Display local time for user clarity
            from app.utils.timezone_utils import convert_utc_to_local_airport
            stored_utc = datetime.fromisoformat(trip_data["departure_date"].replace('Z', '+00:00'))
            display_local = convert_utc_to_local_airport(stored_utc, origin_iata)
            
            return {
                "success": True,
                "trip_id": str(trip_data["id"]),
                "message": "Test trip created successfully",
                "flight_number": flight_number,
                "departure_local": display_local.strftime('%Y-%m-%d %H:%M'),
                "departure_utc": trip_data["departure_date"],
                "next_check_at": trip_data.get("next_check_at"),
                "metadata_included": True,
                "estimated_arrival": trip_data.get("estimated_arrival"),
                "confirmation_notification": {
                    "sent": confirmation_sent,
                    "error": confirmation_error
                }
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "message": "Failed to create test trip"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Exception during test trip creation"
        }
    finally:
        if 'db_client' in locals():
            await db_client.close() 