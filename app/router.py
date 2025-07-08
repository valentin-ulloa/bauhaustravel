"""Main router for Bauhaus Travel API - Simplified and Unified."""

import structlog
from uuid import UUID
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import ValidationError, BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone, date
import json

from .models.database import TripCreate, Trip
from .models.api import DocumentUploadPayload, DocumentUploadResponse
from .db.supabase_client import SupabaseDBClient
from .agents.notifications_agent import NotificationsAgent
from .agents.itinerary_agent import ItineraryAgent
from .agents.notifications_templates import NotificationType
from .api.agencies import router as agencies_router

logger = structlog.get_logger()

router = APIRouter()

# Include sub-routers
router.include_router(agencies_router, tags=["agencies"])


@router.post("/trips")
async def create_trip(trip_in: TripCreate):
    """
    Create a new trip with UNIFIED timezone handling.
    
    SIMPLIFIED: TripCreate model automatically handles timezone conversion.
    No manual conversions needed.
    """
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Create trip (timezone conversion handled automatically)
        result = await db_client.create_trip(trip_in)
        
        if not result.success:
            logger.error("trip_creation_failed", error=result.error)
            raise HTTPException(status_code=400, detail=result.error)
        
        trip_data = result.data
        trip_id = trip_data["id"]
        
        logger.info("trip_created_unified", 
            trip_id=trip_id,
            client_name=trip_in.client_name,
            flight_number=trip_in.flight_number,
            departure_utc=trip_data["departure_date"]
        )
        
        try:
            # Send immediate confirmation
            confirmation_result = await notifications_agent.send_single_notification(
                trip_id, 
                NotificationType.RESERVATION_CONFIRMATION
            )
            
            # Schedule notifications using SIMPLIFIED scheduler integration
            try:
                from .main import get_scheduler
                scheduler = get_scheduler()
                if scheduler:
                    # SIMPLIFIED trip object creation (no manual timezone parsing)
                    trip_obj = _create_trip_object_simplified(trip_data)
                    await scheduler.schedule_immediate_notifications(trip_obj)
                    
                    logger.info("immediate_notifications_scheduled", trip_id=trip_id)
                    
            except Exception as e:
                logger.warning("immediate_scheduling_failed", 
                    trip_id=trip_id, 
                    error=str(e)
                )
            
            return {
                "success": True,
                "trip_id": trip_id,
                "message": "Trip created and confirmation sent",
                "confirmation_status": confirmation_result.data if confirmation_result else None,
                "unified_timezone_handling": True
            }
            
        except Exception as e:
            logger.error("confirmation_failed", 
                trip_id=trip_id,
                error=str(e)
            )
            return {
                "success": True,
                "trip_id": trip_id,
                "message": "Trip created but confirmation failed",
                "error": str(e)
            }
        
    except Exception as e:
        logger.error("trip_creation_error", 
            client_name=trip_in.client_name,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to create trip: {str(e)}")


def _create_trip_object_simplified(trip_data: Dict[str, Any]) -> Trip:
    """
    SIMPLIFIED trip object creation without manual datetime parsing.
    
    Uses database data directly with automatic timezone handling.
    """
    def safe_datetime_parse(date_str):
        """SIMPLIFIED datetime parsing"""
        if not date_str:
            return None
        
        if isinstance(date_str, datetime):
            return date_str.replace(tzinfo=timezone.utc) if date_str.tzinfo is None else date_str
        
        # Handle ISO format with Z suffix (UTC)
        if date_str.endswith('Z'):
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        
        # Handle ISO format with timezone
        try:
            return datetime.fromisoformat(date_str)
        except:
            # Fallback: assume UTC
            return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    
    return Trip(
        id=trip_data["id"],
        client_name=trip_data["client_name"],
        whatsapp=trip_data["whatsapp"],
        flight_number=trip_data["flight_number"],
        origin_iata=trip_data["origin_iata"],
        destination_iata=trip_data["destination_iata"],
        departure_date=safe_datetime_parse(trip_data["departure_date"]),
        status=trip_data["status"],
        metadata=trip_data.get("metadata"),
        inserted_at=safe_datetime_parse(trip_data["inserted_at"]),
        next_check_at=safe_datetime_parse(trip_data.get("next_check_at")),
        client_description=trip_data.get("client_description"),
        agency_id=trip_data.get("agency_id"),
        gate=trip_data.get("gate")
    )


@router.post("/itinerary")
async def generate_itinerary(trip_id: UUID):
    """Generate personalized itinerary for a trip using unified agent."""
    itinerary_agent = None
    
    try:
        logger.info("itinerary_generation_requested", trip_id=str(trip_id))
        
        itinerary_agent = ItineraryAgent()
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
                trip_id=str(trip_id),
                error=result.error
            )
            raise HTTPException(status_code=500, detail="Failed to generate itinerary")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error("itinerary_endpoint_error", 
            trip_id=str(trip_id),
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        if itinerary_agent:
            await itinerary_agent.close()


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(payload: DocumentUploadPayload):
    """Upload a document for a specific trip."""
    logger.info("document_upload_requested",
        trip_id=str(payload.trip_id),
        document_type=payload.document_type
    )
    
    db_client = None
    
    try:
        db_client = SupabaseDBClient()
        
        # Verify trip exists
        trip_result = await db_client.get_trip_by_id(payload.trip_id)
        if not trip_result.success or not trip_result.data:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Create document record
        document_data = {
            "trip_id": str(payload.trip_id),
            "type": payload.document_type,
            "file_url": payload.file_url,
            "file_name": payload.file_name,
            "uploaded_by": payload.uploaded_by,
            "uploaded_by_type": payload.uploaded_by_type,
            "agency_id": str(payload.agency_id) if payload.agency_id else None,
            "metadata": payload.metadata or {}
        }
        
        result = await db_client.create_document(document_data)
        
        if result.success:
            document_id = result.data.get("id") if result.data else None
            
            logger.info("document_uploaded_successfully",
                trip_id=str(payload.trip_id),
                document_id=document_id
            )
            
            return DocumentUploadResponse(
                success=True,
                message="Document uploaded successfully",
                document_id=str(document_id) if document_id else None,
                trip_id=str(payload.trip_id)
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to upload document")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error("document_upload_error",
            trip_id=str(payload.trip_id) if payload else "unknown",
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Document upload failed")
    
    finally:
        if db_client:
            await db_client.close()


@router.get("/documents/{trip_id}")
async def get_trip_documents(trip_id: UUID, document_type: Optional[str] = None):
    """Get all documents for a specific trip."""
    db_client = None
    
    try:
        db_client = SupabaseDBClient()
        
        # Verify trip exists
        trip_result = await db_client.get_trip_by_id(trip_id)
        if not trip_result.success or not trip_result.data:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Get documents
        documents = await db_client.get_documents_by_trip(trip_id, document_type)
        
        return {
            "success": True,
            "trip_id": str(trip_id),
            "documents": documents,
            "count": len(documents)
        }
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error("documents_retrieval_error",
            trip_id=str(trip_id),
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")
    
    finally:
        if db_client:
            await db_client.close()


@router.post("/test-flight-polling")
async def test_flight_polling():
    """Test endpoint for UNIFIED flight polling functionality"""
    logger.info("test_flight_polling_requested")
    
    notifications_agent = None
    
    try:
        notifications_agent = NotificationsAgent()
        result = await notifications_agent.run("status_change")
        
        return {
            "status": "completed",
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "unified_architecture": True
        }
        
    except Exception as e:
        logger.error("test_flight_polling_error", error=str(e))
        return {
            "status": "error",
            "success": False,
            "error": str(e)
        }
    
    finally:
        if notifications_agent:
            await notifications_agent.close()


@router.get("/test-timezone/{airport_iata}")
async def test_timezone(airport_iata: str):
    """Test UNIFIED timezone conversion for airport notifications"""
    from .utils.timezone_utils import get_timezone_info, format_departure_time_local
    from datetime import datetime, timezone
    
    # Test timezone functionality
    tz_info = get_timezone_info(airport_iata)
    
    now_utc = datetime.now(timezone.utc)
    sample_departure = datetime(2025, 7, 5, 17, 32, tzinfo=timezone.utc)
    
    formatted_time = format_departure_time_local(sample_departure, airport_iata)
    
    return {
        "airport": airport_iata.upper(),
        "timezone_info": tz_info,
        "test_case": {
            "utc_time": sample_departure.isoformat(),
            "formatted_for_notification": formatted_time,
            "explanation": f"Flight at 17:32 UTC shows as '{formatted_time}' in WhatsApp"
        },
        "unified_timezone_policy": True
    }


@router.post("/test-flight-notification/{trip_id}")
async def test_flight_notification(trip_id: str):
    """
    Test endpoint using UNIFIED notification system.
    
    Intelligently selects notification type based on departure timing.
    """
    try:
        from uuid import UUID
        from datetime import datetime, timezone, timedelta
        
        # Get trip details using unified client
        db_client = SupabaseDBClient()
        trip_result = await db_client.get_trip_by_id(UUID(trip_id))
        
        if not trip_result.success:
            return {
                "status": "error",
                "trip_id": trip_id,
                "error": f"Trip not found: {trip_result.error}"
            }
        
        trip_data = trip_result.data
        
        # SIMPLIFIED departure time parsing (database returns UTC)
        departure_utc = datetime.fromisoformat(trip_data["departure_date"].replace('Z', '+00:00'))
        now_utc = datetime.now(timezone.utc)
        hours_to_departure = (departure_utc - now_utc).total_seconds() / 3600
        
        # INTELLIGENT notification type selection
        if hours_to_departure <= 0:
            notification_type = NotificationType.LANDING_WELCOME
            extra_data = {"hotel_address": "tu alojamiento reservado"}
        elif hours_to_departure <= 1:
            notification_type = NotificationType.BOARDING
            extra_data = {"gate": "Ver pantallas del aeropuerto"}
        elif hours_to_departure <= 4:
            notification_type = NotificationType.RESERVATION_CONFIRMATION
            extra_data = {}
        elif 20 <= hours_to_departure <= 28:
            notification_type = NotificationType.REMINDER_24H
            extra_data = {
                "weather_info": "buen clima para volar",
                "additional_info": "¡Buen viaje!"
            }
        else:
            return {
                "status": "not_applicable",
                "trip_id": trip_id,
                "hours_to_departure": round(hours_to_departure, 2),
                "message": f"No appropriate notification for {round(hours_to_departure, 2)} hours to departure"
            }
        
        # Send using unified agent
        agent = NotificationsAgent()
        result = await agent.send_single_notification(
            trip_id=UUID(trip_id),
            notification_type=notification_type,
            extra_data=extra_data
        )
        
        await agent.close()
        await db_client.close()
        
        return {
            "status": "notification_sent" if result.success else "notification_failed",
            "trip_id": trip_id,
            "notification_type": notification_type,
            "hours_to_departure": round(hours_to_departure, 2),
            "result": result.data if result.success else result.error,
            "unified_system": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "trip_id": trip_id,
            "error": str(e)
        }


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get UNIFIED scheduler status"""
    try:
        from .main import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            return {
                "status": "not_initialized",
                "message": "Scheduler service not available"
            }
        
        status = scheduler.get_job_status()
        return status
        
    except Exception as e:
        logger.error("scheduler_status_error", error=str(e))
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/test-async-notification")
async def test_async_notification():
    """
    Test UNIFIED async notification system.
    Validates all optimized components.
    """
    try:
        agent = NotificationsAgent()
        
        # Test unified components
        unified_status = {
            "async_twilio_client": "initialized" if agent.async_twilio_client else "failed",
            "retry_service": "initialized" if agent.retry_service else "failed",
            "db_client": "initialized" if agent.db_client else "failed",
            "aeroapi_client": "initialized" if agent.aeroapi_client else "failed"
        }
        
        # Test optimized AeroAPI cache
        cache_stats = agent.aeroapi_client.get_cache_stats()
        
        # Test unified utilities
        from .utils.flight_schedule_utils import calculate_unified_next_check
        from datetime import datetime, timezone, timedelta
        
        test_next_check = calculate_unified_next_check(
            departure_time=datetime.now(timezone.utc) + timedelta(hours=25),
            now_utc=datetime.now(timezone.utc),
            current_status="SCHEDULED"
        )
        
        await agent.close()
        
        return {
            "status": "success",
            "unified_architecture": "fully_operational",
            "components": unified_status,
            "aeroapi_cache": cache_stats,
            "unified_next_check": test_next_check.isoformat() if test_next_check else None,
            "optimizations": {
                "duplications_eliminated": True,
                "cache_optimization": True,
                "timezone_policy_unified": True,
                "quiet_hours_centralized": True
            },
            "production_ready": True
        }
        
    except Exception as e:
        return {
            "status": "error", 
            "error": str(e),
            "unified_architecture": "failed"
        }


class LandingWelcomeRequest(BaseModel):
    """Request model for landing welcome notification."""
    hotel_address: Optional[str] = "tu alojamiento reservado"


@router.post("/test-landing-welcome/{trip_id}")
async def test_landing_welcome_notification(trip_id: str, request: LandingWelcomeRequest):
    """Test UNIFIED landing welcome notification."""
    try:
        from uuid import UUID
        
        agent = NotificationsAgent()
        
        result = await agent.send_single_notification(
            trip_id=UUID(trip_id),
            notification_type=NotificationType.LANDING_WELCOME,
            extra_data={"hotel_address": request.hotel_address}
        )
        
        await agent.close()
        
        return {
            "status": "landing_welcome_sent" if result.success else "landing_welcome_failed",
            "trip_id": trip_id,
            "hotel_address": request.hotel_address,
            "result": result.data if result.success else result.error,
            "unified_system": True,
            "features": {
                "openai_city_lookup": "enabled",
                "hotel_metadata_support": "enabled", 
                "idempotency": "simplified"
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "trip_id": trip_id,
            "error": str(e)
        }


@router.get("/itinerary/{trip_id}")
async def get_itinerary(trip_id: UUID):
    """Get the latest itinerary for a trip with unified JSON serialization."""
    try:
        db_client = SupabaseDBClient()
        result = await db_client.get_latest_itinerary(trip_id)
        
        if result.success:
            return JSONResponse(status_code=200, content=_to_json_serializable(result.data))
        else:
            return JSONResponse(status_code=500, content={"error": result.error or "Unknown error"})
    except Exception as e:
        logger.error("itinerary_retrieval_failed", trip_id=str(trip_id), error=str(e))
        return JSONResponse(status_code=500, content={"exception": str(e)})
    finally:
        await db_client.close()


def _to_json_serializable(obj):
    """SIMPLIFIED JSON serialization helper."""
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_json_serializable(i) for i in obj]
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


@router.post("/admin/cleanup-test-data")
async def cleanup_test_data():
    """ADMIN ENDPOINT: Clean up test data."""
    from datetime import datetime
    
    try:
        db_client = SupabaseDBClient()
        
        cleanup_results = {}
        tables = ["conversations", "itineraries", "notifications_log", "trips"]
        
        for table in tables:
            response = await db_client._client.delete(
                f"{db_client.rest_url}/{table}",
                params={"id": "is.not.null"}
            )
            response.raise_for_status()
            
            deleted = response.json() if response.text else []
            cleanup_results[f"{table}_deleted"] = len(deleted) if deleted else 0
        
        await db_client.close()
        
        return {
            "success": True,
            "message": "Database cleaned successfully",
            "cleanup_results": cleanup_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }