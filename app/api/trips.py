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
    Default departure time is 25 hours from now to test 24h reminders.
    """
    try:
        from app.db.supabase_client import SupabaseDBClient
        from datetime import datetime, timezone, timedelta
        
        db_client = SupabaseDBClient()
        
        # Create departure time based on hours_from_now
        departure_date = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        
        # Create trip
        trip_data = {
            "client_name": client_name,
            "whatsapp": whatsapp,
            "flight_number": flight_number,
            "origin_iata": origin_iata,
            "destination_iata": destination_iata,
            "departure_date": departure_date.isoformat(),
            "status": "scheduled",
            "agency_id": "00000000-0000-0000-0000-000000000001",  # Default test agency
            "client_description": f"Test trip created for system validation - {departure_date.strftime('%Y-%m-%d %H:%M')} UTC"
        }
        
        result = await db_client.create_trip(trip_data)
        
        if result.success:
            trip_id = result.data.get("id")
            return {
                "status": "success",
                "message": "Test trip created successfully", 
                "trip_id": trip_id,
                "trip_data": trip_data,
                "departure_in_hours": hours_from_now,
                "next_steps": f"Use POST /test-flight-notification/{trip_id} to test notifications"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to create test trip",
                "error": result.error
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": "Exception creating test trip",
            "error": str(e)
        } 