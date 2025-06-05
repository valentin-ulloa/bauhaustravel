"""Main router for Bauhaus Travel API."""

import structlog
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .models.database import TripCreate
from .db.supabase_client import SupabaseDBClient
from .agents.notifications_agent import NotificationsAgent
from .agents.notifications_templates import NotificationType

logger = structlog.get_logger()

router = APIRouter()


@router.post("/trips")
async def create_trip(trip_in: TripCreate):
    """
    Create a new trip and send reservation confirmation.
    
    This endpoint:
    1. Inserts the trip into Supabase using SupabaseDBClient
    2. Triggers immediate reservation confirmation via NotificationsAgent
    3. Returns trip_id and confirmation status
    
    Follows the Agent architecture pattern - no DB logic in router.
    """
    db_client = None
    notifications_agent = None
    
    try:
        logger.info("trip_creation_requested", 
            flight_number=trip_in.flight_number,
            client_name=trip_in.client_name
        )
        
        # Initialize database client
        db_client = SupabaseDBClient()
        
        # Create trip in database
        create_result = await db_client.create_trip(trip_in)
        
        if not create_result.success:
            logger.error("trip_creation_failed", 
                flight_number=trip_in.flight_number,
                error=create_result.error
            )
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to create trip: {create_result.error}"
            )
        
        # Extract created trip
        trip_data = create_result.data
        trip_id = trip_data["id"]
        
        logger.info("trip_created_successfully", 
            trip_id=str(trip_id),
            flight_number=trip_data["flight_number"]
        )
        
        # Initialize notifications agent and send confirmation
        notifications_agent = NotificationsAgent()
        
        notification_result = await notifications_agent.send_single_notification(
            trip_id=trip_id,
            notification_type=NotificationType.RESERVATION_CONFIRMATION
        )
        
        if notification_result.success:
            logger.info("reservation_confirmation_sent", 
                trip_id=str(trip_id),
                message_sid=notification_result.data.get("message_sid") if notification_result.data else None
            )
            
            return JSONResponse(
                status_code=201,
                content={
                    "trip_id": str(trip_id),
                    "status": "confirmation_sent"
                }
            )
        else:
            # Trip was created but notification failed
            logger.warning("reservation_confirmation_failed", 
                trip_id=str(trip_id),
                error=notification_result.error
            )
            
            return JSONResponse(
                status_code=201,
                content={
                    "trip_id": str(trip_id),
                    "status": "confirmation_failed",
                    "error": notification_result.error
                }
            )
    
    except HTTPException:
        raise  # Re-raise FastAPI exceptions
    
    except Exception as e:
        logger.error("trip_endpoint_error", 
            flight_number=trip_in.flight_number,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    
    finally:
        # Clean up resources
        if db_client:
            await db_client.close()
        if notifications_agent:
            await notifications_agent.close() 