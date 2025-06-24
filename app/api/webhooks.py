"""FastAPI webhooks for Bauhaus Travel."""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Form
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import structlog

from ..agents.notifications_agent import NotificationsAgent
from ..agents.notifications_templates import NotificationType
from ..agents.concierge_agent import ConciergeAgent
from ..models.database import Trip

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class TripInsertPayload(BaseModel):
    """Payload from Supabase when a trip is inserted."""
    type: str  # "INSERT"
    table: str  # "trips"
    record: Dict[str, Any]  # The inserted trip data
    schema_name: str = Field(default="public", alias="schema")  # Renamed to avoid BaseModel.schema shadowing


class TwilioInboundMessage(BaseModel):
    """Twilio WhatsApp inbound message payload."""
    MessageSid: str
    From: str  # "whatsapp:+1234567890"
    To: str    # "whatsapp:+13613094264" 
    Body: str
    NumMedia: Optional[str] = "0"
    MediaUrl0: Optional[str] = None
    MediaContentType0: Optional[str] = None


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


def normalize_phone(phone: str) -> str:
    """Normalize phone number by removing whatsapp: prefix if present."""
    return phone.replace("whatsapp:", "") if phone.startswith("whatsapp:") else phone


@router.post("/twilio")
async def twilio_whatsapp_webhook(
    background_tasks: BackgroundTasks,
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    NumMedia: str = Form(default="0"),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None)
):
    """
    Webhook to receive incoming WhatsApp messages from Twilio.
    Processes user messages via ConciergeAgent.
    """
    # Extract and normalize phone number
    whatsapp_number = normalize_phone(From)
    
    logger.info("normalized_phone", 
        raw=From,
        normalized=whatsapp_number
    )
    
    logger.info("twilio_inbound_message_received",
        message_sid=MessageSid,
        from_number=whatsapp_number,
        body_length=len(Body),
        has_media=NumMedia != "0"
    )
    
    try:
        # Add background task to process message
        background_tasks.add_task(
            process_inbound_message,
            whatsapp_number,
            Body,
            MediaUrl0,
            MediaContentType0,
            MessageSid
        )
        
        logger.info("inbound_message_queued",
            message_sid=MessageSid,
            from_number=whatsapp_number
        )
        
        # Return empty response (Twilio doesn't expect content)
        return ""
        
    except Exception as e:
        logger.error("twilio_webhook_failed",
            error_code="TWILIO_WEBHOOK_ERROR", 
            error=str(e),
            message_sid=MessageSid,
            from_number=whatsapp_number
        )
        # Still return empty to avoid Twilio retries
        return ""


async def process_inbound_message(
    whatsapp_number: str,
    message_body: str,
    media_url: Optional[str],
    media_type: Optional[str],
    message_sid: str
):
    """
    Background task to process inbound WhatsApp message.
    """
    concierge_agent = None
    
    try:
        logger.info("BACKGROUND_TASK_STARTED",
            from_number=whatsapp_number,
            message_sid=message_sid,
            message_body=message_body[:50] + "..." if len(message_body) > 50 else message_body,
            has_media=media_url is not None
        )
        
        logger.info("processing_inbound_message",
            from_number=whatsapp_number,
            message_sid=message_sid,
            has_media=media_url is not None
        )
        
        # Initialize ConciergeAgent
        logger.info("INITIALIZING_CONCIERGE_AGENT")
        try:
            concierge_agent = ConciergeAgent()
            logger.info("CONCIERGE_AGENT_INITIALIZED")
        except Exception as init_error:
            logger.error("CONCIERGE_AGENT_INIT_FAILED", error=str(init_error), error_type=type(init_error).__name__)
            raise init_error
        
        # Process the message
        logger.info("CALLING_HANDLE_INBOUND_MESSAGE")
        try:
            result = await concierge_agent.handle_inbound_message(
                whatsapp_number=whatsapp_number,
                message_body=message_body,
                media_url=media_url,
                media_type=media_type,
                message_sid=message_sid
            )
        except Exception as handle_error:
            logger.error("HANDLE_INBOUND_MESSAGE_FAILED", error=str(handle_error), error_type=type(handle_error).__name__)
            raise handle_error
        
        if result.success:
            logger.info("inbound_message_processed",
                from_number=whatsapp_number,
                message_sid=message_sid,
                response_sent=True
            )
        else:
            logger.error("inbound_message_processing_failed",
                error_code="MESSAGE_PROCESSING_FAILED",
                from_number=whatsapp_number,
                message_sid=message_sid,
                error=result.error
            )
    
    except Exception as e:
        logger.error("inbound_message_task_failed",
            error_code="BACKGROUND_TASK_ERROR",
            from_number=whatsapp_number,
            message_sid=message_sid,
            error=str(e)
        )
    
    finally:
        if concierge_agent:
            await concierge_agent.close()


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
            notification_type=NotificationType.RESERVATION_CONFIRMATION
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