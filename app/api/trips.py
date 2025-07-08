from fastapi import APIRouter

router = APIRouter()

@router.post("/create-test-trip")
async def create_test_trip(
    client_name: str = "Test Client",
    whatsapp: str = "+1234567890", 
    flight_number: str = "AA123",
    origin_iata: str = "JFK",
    destination_iata: str = "LAX",
    hours_from_now: int = 25  # Default 25h for 24h reminder testing
):
    """
    Create a test trip for validation purposes.
    
    SIMPLIFIED: Uses new timezone policy - departure time is LOCAL airport time.
    TripCreate automatically converts to UTC for storage.
    """
    try:
        from app.db.supabase_client import SupabaseDBClient
        from app.models.database import TripCreate
        from datetime import datetime, timedelta
        from uuid import UUID
        
        db_client = SupabaseDBClient()
        
        # POLICY ENFORCEMENT: Create LOCAL time for the origin airport
        # This will be automatically converted to UTC by TripCreate
        base_time = datetime.now() + timedelta(hours=hours_from_now)
        local_departure = base_time.replace(second=0, microsecond=0)  # Clean time
        
        # Create TripCreate object (auto-converts local time to UTC)
        trip_create = TripCreate(
            client_name=client_name,
            whatsapp=whatsapp,
            flight_number=flight_number,
            origin_iata=origin_iata,
            destination_iata=destination_iata,
            departure_date=local_departure,  # LOCAL TIME - auto-converted to UTC
            agency_id=UUID("00000000-0000-0000-0000-000000000001"),  # Default test agency
            client_description=f"Test trip created for system validation - Local time: {local_departure.strftime('%Y-%m-%d %H:%M')}"
        )
        
        result = await db_client.create_trip(trip_create)
        
        if result.success:
            trip_data = result.data
            
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
                "next_check_at": trip_data.get("next_check_at")
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