"""Main router for Bauhaus Travel API."""

import structlog
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .models.database import TripCreate
from .db.supabase_client import SupabaseDBClient
from .agents.notifications_agent import NotificationsAgent
from .agents.itinerary_agent import ItineraryAgent
from .agents.notifications_templates import NotificationType

logger = structlog.get_logger()

router = APIRouter()


@router.post("/trips")
async def create_trip(trip_in: TripCreate):
    """
    Create a new trip and send reservation confirmation.
    
    This endpoint:
    1. Validates phone number format (422 if invalid)
    2. Checks for duplicates (409 if exists) 
    3. Inserts the trip into Supabase using SupabaseDBClient
    4. Triggers immediate reservation confirmation via NotificationsAgent
    5. Returns trip_id and confirmation status
    
    Follows the Agent architecture pattern - no DB logic in router.
    """
    db_client = None
    notifications_agent = None
    
    try:
        logger.info("trip_creation_requested", 
            flight_number=trip_in.flight_number,
            client_name=trip_in.client_name,
            whatsapp=trip_in.whatsapp
        )
        
        # Initialize database client
        db_client = SupabaseDBClient()
        
        # Check for duplicate trips
        duplicate_check = await db_client.check_duplicate_trip(
            whatsapp=trip_in.whatsapp,
            flight_number=trip_in.flight_number,
            departure_date=trip_in.departure_date
        )
        
        if not duplicate_check.success:
            logger.error("duplicate_check_failed", 
                error_code="DUPLICATE_CHECK_FAILED",
                flight_number=trip_in.flight_number,
                error=duplicate_check.error
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to check duplicate trips"
            )
        
        if duplicate_check.data and duplicate_check.data.get("exists"):
            logger.warning("duplicate_trip_rejected", 
                whatsapp=trip_in.whatsapp,
                flight_number=trip_in.flight_number,
                departure_date=trip_in.departure_date.isoformat()
            )
            raise HTTPException(
                status_code=409,
                detail="Trip already exists for this flight and passenger"
            )
        
        # Create trip in database
        create_result = await db_client.create_trip(trip_in)
        
        if not create_result.success:
            logger.error("trip_creation_failed", 
                error_code="TRIP_CREATION_FAILED",
                flight_number=trip_in.flight_number,
                error=create_result.error
            )
            raise HTTPException(
                status_code=500, 
                detail="Failed to create trip"
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
    
    except ValidationError as e:
        logger.error("trip_validation_failed", 
            error_code="VALIDATION_ERROR",
            flight_number=trip_in.flight_number if hasattr(trip_in, 'flight_number') else 'unknown',
            validation_errors=str(e)
        )
        raise HTTPException(
            status_code=422,
            detail="Invalid request data"
        )
    
    except HTTPException:
        raise  # Re-raise FastAPI exceptions
    
    except Exception as e:
        logger.error("trip_endpoint_error", 
            error_code="INTERNAL_ERROR",
            flight_number=trip_in.flight_number if hasattr(trip_in, 'flight_number') else 'unknown',
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
    
    finally:
        # Clean up resources
        if db_client:
            await db_client.close()
        if notifications_agent:
            await notifications_agent.close()


@router.post("/itinerary")
async def generate_itinerary(trip_id: UUID):
    """
    Generate personalized itinerary for a trip.
    
    This endpoint:
    1. Loads trip data and profile (client_description)
    2. Loads agency_places if agency_id is present
    3. Generates personalized itinerary via GPT-4o mini
    4. Validates places against agency data (source="agency" vs "low_validation")
    5. Saves parsed_itinerary to database
    6. Sends WhatsApp notification when ready
    
    Follows the Agent architecture pattern.
    """
    itinerary_agent = None
    
    try:
        logger.info("itinerary_generation_requested", trip_id=str(trip_id))
        
        # Initialize itinerary agent
        itinerary_agent = ItineraryAgent()
        
        # Generate itinerary
        result = await itinerary_agent.run(trip_id)
        
        if result.success:
            logger.info("itinerary_generated_successfully", 
                trip_id=str(trip_id),
                itinerary_id=result.data.get("itinerary_id")
            )
            return JSONResponse(
                status_code=201,
                content={
                    "itinerary_id": result.data["itinerary_id"],
                    "trip_id": str(trip_id),
                    "status": "generated"
                }
            )
        else:
            logger.error("itinerary_generation_failed", 
                error_code="ITINERARY_GENERATION_FAILED",
                trip_id=str(trip_id),
                error=result.error
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to generate itinerary"
            )
    
    except HTTPException:
        raise  # Re-raise FastAPI exceptions
    
    except Exception as e:
        logger.error("itinerary_endpoint_error", 
            error_code="INTERNAL_ERROR",
            trip_id=str(trip_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
    
    finally:
        # Clean up resources
        if itinerary_agent:
            await itinerary_agent.close() 