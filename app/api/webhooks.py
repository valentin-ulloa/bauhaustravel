"""FastAPI webhooks for Bauhaus Travel."""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime, timezone
import structlog

from ..agents.notifications_agent import NotificationsAgent
from ..agents.notifications_templates import NotificationType
from ..models.database import Trip

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class TripInsertPayload(BaseModel):
    """Payload from Supabase when a trip is inserted."""
    type: str  # "INSERT"
    table: str  # "trips"
    record: Dict[str, Any]  # The inserted trip data
    schema: str = "public"


@router.post("/trip-confirmation")
async def trip_confirmation_webhook(
    payload: TripInsertPayload,
    background_tasks: BackgroundTasks
):
    """
    Webhook triggered when a new trip is inserted in Supabase.
    Sends booking confirmation WhatsApp message.
    """
    logger.info("trip_confirmation_webhook_triggered", 
        type=payload.type,
        table=payload.table,
        trip_id=payload.record.get("id")
    )
    
    try:
        # Validate this is a trip insert
        if payload.type != "INSERT" or payload.table != "trips":
            logger.error("invalid_webhook_payload",
                error_code="INVALID_WEBHOOK_PAYLOAD",
                payload_type=payload.type,
                table=payload.table
            )
            raise HTTPException(
                status_code=400, 
                detail="Invalid webhook payload"
            )
        
        # Parse trip data
        trip_data = payload.record
        trip = Trip(**trip_data)
        
        # Add background task to send confirmation
        background_tasks.add_task(
            send_booking_confirmation,
            trip
        )
        
        logger.info("trip_confirmation_scheduled", 
            trip_id=str(trip.id),
            client_name=trip.client_name,
            flight_number=trip.flight_number
        )
        
        return {
            "success": True,
            "message": "Booking confirmation scheduled",
            "trip_id": str(trip.id)
        }
        
    except Exception as e:
        logger.error("trip_confirmation_webhook_failed", 
            error_code="WEBHOOK_PROCESSING_ERROR",
            error=str(e),
            payload=payload.dict()
        )
        raise HTTPException(status_code=500, detail="Webhook processing failed")


async def send_booking_confirmation(trip: Trip):
    """
    Background task to send booking confirmation via WhatsApp.
    """
    logger.info("sending_booking_confirmation", 
        trip_id=str(trip.id),
        client_name=trip.client_name
    )
    
    agent = None
    try:
        # Initialize notifications agent
        agent = NotificationsAgent()
        
        # Send booking confirmation
        result = await agent.send_notification(
            trip=trip,
            notification_type=NotificationType.BOOKING_CONFIRMATION
        )
        
        if result.success:
            logger.info("booking_confirmation_sent", 
                trip_id=str(trip.id),
                message_sid=result.data.get("message_sid"),
                client_name=trip.client_name
            )
        else:
            logger.error("booking_confirmation_failed", 
                trip_id=str(trip.id),
                error=result.error
            )
    
    except Exception as e:
        logger.error("booking_confirmation_task_failed", 
            trip_id=str(trip.id),
            error=str(e)
        )
    
    finally:
        if agent:
            await agent.close()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "bauhaus-travel-webhooks"
    } 