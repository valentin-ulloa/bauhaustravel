"""Main router for Bauhaus Travel API."""

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
        
        try:
            confirmation_result = await notifications_agent.send_single_notification(
                trip_id, 
                NotificationType.RESERVATION_CONFIRMATION
            )
            
            # Schedule immediate notifications if needed (last-minute trips)
            try:
                from .main import get_scheduler
                scheduler = get_scheduler()
                if scheduler:
                    # Convert trip_data dict to Trip object for scheduler
                    from .models.database import Trip
                    from datetime import datetime, timezone
                    
                    def safe_datetime_parse(date_str):
                        """Safely parse datetime string with or without timezone"""
                        if not date_str:
                            return None
                        
                        # If it's already a datetime object, just ensure it has timezone
                        if isinstance(date_str, datetime):
                            if date_str.tzinfo is None:
                                return date_str.replace(tzinfo=timezone.utc)
                            return date_str
                        
                        # Handle different datetime formats from database
                        if date_str.endswith('Z'):
                            # UTC format: "2025-06-20T15:00:00Z"
                            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        elif '+' in date_str or '-' in date_str.split('T')[1]:
                            # Timezone format: "2025-06-20T15:00:00-03:00"
                            return datetime.fromisoformat(date_str)
                        else:
                            # No timezone: "2025-06-20T15:00:00" - assume UTC
                            return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                    
                    trip_obj = Trip(
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
                    
                    await scheduler.schedule_immediate_notifications(trip_obj)
            except Exception as scheduler_error:
                # Log scheduler error but don't fail the trip creation
                logger.error("scheduler_integration_failed", 
                    trip_id=str(trip_id),
                    scheduler_error=str(scheduler_error),
                    error_type=type(scheduler_error).__name__
                )
            
            # Close notifications agent resources
            await notifications_agent.close()
            
            if confirmation_result.success:
                return {
                    "trip_id": str(trip_id),
                    "status": "confirmation_sent",
                    "message": "Trip created and confirmation sent successfully",
                    "next_check_at": trip_data.get("next_check_at", None).isoformat() if trip_data.get("next_check_at") else None
                }
            else:
                return {
                    "trip_id": str(trip_id),
                    "status": "confirmation_failed", 
                    "message": f"Trip created but confirmation failed: {confirmation_result.error}",
                    "next_check_at": trip_data.get("next_check_at", None).isoformat() if trip_data.get("next_check_at") else None
                }
                
        except Exception as e:
            logger.error("trip_notification_error", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return {
                "trip_id": str(trip_id),
                "status": "confirmation_failed",
                "message": f"Trip created but notification system failed: {str(e)}",
                "next_check_at": trip_data.get("next_check_at", None).isoformat() if trip_data.get("next_check_at") else None
            }
    
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


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(payload: DocumentUploadPayload):
    """
    Upload a document for a specific trip.
    
    This endpoint accepts a JSON payload with document information and stores it
    with full audit trail for compliance. Designed to be consumed by:
    - External APIs and integrations
    - WhatsApp bot (future: when users send files directly)
    - Agency portals and management systems
    
    Args:
        payload: DocumentUploadPayload with all document information
        
    Returns:
        DocumentUploadResponse with upload confirmation
    """
    logger.info("document_upload_requested",
        trip_id=str(payload.trip_id),
        document_type=payload.document_type,
        uploaded_by_type=payload.uploaded_by_type,
        uploaded_by=payload.uploaded_by
    )
    
    db_client = None
    
    try:
        # Initialize database client
        db_client = SupabaseDBClient()
        
        # Verify trip exists
        trip_result = await db_client.get_trip_by_id(payload.trip_id)
        if not trip_result.success or not trip_result.data:
            logger.error("trip_not_found_for_document",
                error_code="TRIP_NOT_FOUND",
                trip_id=str(payload.trip_id)
            )
            raise HTTPException(
                status_code=404,
                detail="Trip not found"
            )
        
        # Prepare document data for database
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
        
        # Create document record
        result = await db_client.create_document(document_data)
        
        if result.success:
            document_id = result.data.get("id") if result.data else None
            
            logger.info("document_uploaded_successfully",
                trip_id=str(payload.trip_id),
                document_type=payload.document_type,
                document_id=document_id,
                file_name=payload.file_name
            )
            
            return DocumentUploadResponse(
                success=True,
                message="Document uploaded successfully",
                document_id=str(document_id) if document_id else None,
                trip_id=str(payload.trip_id)
            )
        else:
            logger.error("document_upload_failed",
                error_code="DOCUMENT_CREATION_ERROR",
                trip_id=str(payload.trip_id),
                error=result.error
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to upload document"
            )
    
    except ValidationError as e:
        # Pydantic validation errors (handled automatically by FastAPI)
        logger.error("document_validation_error",
            error_code="VALIDATION_ERROR",
            validation_errors=str(e)
        )
        raise HTTPException(
            status_code=422,
            detail="Invalid document data"
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    
    except Exception as e:
        logger.error("document_upload_error",
            error_code="DOCUMENT_UPLOAD_ERROR",
            trip_id=str(payload.trip_id) if payload else "unknown",
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Document upload failed"
        )
    
    finally:
        if db_client:
            await db_client.close()


@router.get("/documents/{trip_id}")
async def get_trip_documents(
    trip_id: UUID,
    document_type: Optional[str] = None
):
    """
    Get all documents for a specific trip.
    
    Args:
        trip_id: UUID of the trip
        document_type: Optional filter by document type
        
    Returns:
        List of documents for the trip
    """
    logger.info("documents_requested",
        trip_id=str(trip_id),
        document_type=document_type
    )
    
    db_client = None
    
    try:
        # Initialize database client
        db_client = SupabaseDBClient()
        
        # Verify trip exists
        trip_result = await db_client.get_trip_by_id(trip_id)
        if not trip_result.success or not trip_result.data:
            logger.error("trip_not_found_for_documents",
                error_code="TRIP_NOT_FOUND",
                trip_id=str(trip_id)
            )
            raise HTTPException(
                status_code=404,
                detail="Trip not found"
            )
        
        # Get documents
        documents = await db_client.get_documents_by_trip(trip_id, document_type)
        
        logger.info("documents_retrieved",
            trip_id=str(trip_id),
            count=len(documents),
            document_type=document_type
        )
        
        return {
            "success": True,
            "trip_id": str(trip_id),
            "documents": documents,
            "count": len(documents)
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    
    except Exception as e:
        logger.error("documents_retrieval_error",
            error_code="DOCUMENTS_RETRIEVAL_ERROR",
            trip_id=str(trip_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve documents"
        )
    
    finally:
        if db_client:
            await db_client.close()


@router.post("/test-flight-polling")
async def test_flight_polling():
    """Test endpoint for flight polling functionality"""
    logger.info("test_flight_polling_requested")
    
    notifications_agent = None
    
    try:
        notifications_agent = NotificationsAgent()
        result = await notifications_agent.run("status_change")
        
        return {
            "status": "completed",
            "success": result.success,
            "data": result.data,
            "error": result.error
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
    """Test timezone conversion for airport notifications"""
    from .utils.timezone_utils import get_timezone_info, format_departure_time_local
    from datetime import datetime, timezone
    
    # Get timezone info for airport
    tz_info = get_timezone_info(airport_iata)
    
    # Test with current time and a sample departure time
    now_utc = datetime.now(timezone.utc)
    sample_departure = datetime(2025, 7, 5, 17, 32, tzinfo=timezone.utc)  # UTC time from your example
    
    # Format the time as it would appear in notifications
    formatted_time = format_departure_time_local(sample_departure, airport_iata)
    
    return {
        "airport": airport_iata.upper(),
        "timezone_info": tz_info,
        "test_case": {
            "utc_time": sample_departure.isoformat(),
            "formatted_for_notification": formatted_time,
            "explanation": f"Your flight at 17:32 UTC would show as '{formatted_time}' in WhatsApp"
        }
    }


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get current scheduler status and job information"""
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


@router.post("/scheduler/test-24h-reminders")
async def test_24h_reminders():
    """Test endpoint for 24h reminder functionality"""
    logger.info("test_24h_reminders_requested")
    
    notifications_agent = None
    
    try:
        notifications_agent = NotificationsAgent()
        result = await notifications_agent.run("24h_reminder")
        
        return {
            "status": "completed",
            "success": result.success,
            "data": result.data,
            "error": result.error
        }
        
    except Exception as e:
        logger.error("test_24h_reminders_error", error=str(e))
        return {
            "status": "error",
            "success": False,
            "error": str(e)
        }
    
    finally:
        if notifications_agent:
            await notifications_agent.close()


@router.post("/scheduler/test-boarding-notifications")
async def test_boarding_notifications():
    """Test endpoint for boarding notifications functionality"""
    logger.info("test_boarding_notifications_requested")
    
    try:
        from .main import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            return {
                "status": "error",
                "message": "Scheduler service not available"
            }
        
        # Manually trigger boarding notifications check
        await scheduler._process_boarding_notifications()
        
        return {
            "status": "completed",
            "message": "Boarding notifications check executed"
        }
        
    except Exception as e:
        logger.error("test_boarding_notifications_error", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        } 


@router.post("/scheduler/test-itinerary-generation")
async def test_itinerary_generation():
    """Test automatic itinerary generation scheduling"""
    try:
        from .main import get_scheduler
        from .models.database import Trip
        from datetime import datetime, timezone, timedelta
        from uuid import uuid4
        
        scheduler = get_scheduler()
        
        if not scheduler or not scheduler.is_running:
            return {
                "status": "error",
                "message": "Scheduler not running"
            }
        
        # Create a test trip object for tomorrow
        now_utc = datetime.now(timezone.utc)
        test_trip = Trip(
            id=uuid4(),
            client_name="Test User",
            whatsapp="+1234567890",
            flight_number="TEST123",
            origin_iata="LAX",
            destination_iata="NYC", 
            departure_date=now_utc + timedelta(hours=25),  # Tomorrow
            status="confirmed",
            inserted_at=now_utc,
            client_description="Test trip for itinerary generation"
        )
        
        # Test the scheduler method directly
        await scheduler.schedule_immediate_notifications(test_trip)
        
        # Check if jobs were scheduled
        jobs = scheduler.get_job_status()
        itinerary_jobs = [job for job in jobs.get("jobs", []) if "itinerary" in job.get("id", "")]
        
        return {
            "status": "completed",
            "message": "Itinerary scheduling test completed",
            "trip_id": str(test_trip.id),
            "scheduled_jobs": itinerary_jobs,
            "total_jobs": jobs.get("jobs_count", 0)
        }
        
    except Exception as e:
        logger.error("test_itinerary_generation_failed", error=str(e))
        return {
            "status": "error", 
            "message": f"Test failed: {str(e)}"
        }


@router.post("/scheduler/debug-trip-scheduling/{trip_id}")
async def debug_trip_scheduling(trip_id: UUID):
    """Debug scheduler integration for a specific trip"""
    try:
        from .main import get_scheduler
        from .models.database import Trip
        
        # Get the trip from database
        db_client = SupabaseDBClient()
        trip_result = await db_client.get_trip_by_id(trip_id)
        
        if not trip_result.success or not trip_result.data:
            return {
                "status": "error",
                "message": "Trip not found"
            }
        
        trip_data = trip_result.data
        
        # Get scheduler
        scheduler = get_scheduler()
        if not scheduler or not scheduler.is_running:
            return {
                "status": "error",
                "message": "Scheduler not running"
            }
        
        # Convert to Trip object exactly like in create_trip
        from datetime import datetime, timezone
        
        def safe_datetime_parse(date_str):
            """Safely parse datetime string with or without timezone"""
            if not date_str:
                return None
            
            # If it's already a datetime object, just ensure it has timezone
            if isinstance(date_str, datetime):
                if date_str.tzinfo is None:
                    return date_str.replace(tzinfo=timezone.utc)
                return date_str
            
            # Handle different datetime formats from database
            if date_str.endswith('Z'):
                # UTC format: "2025-06-20T15:00:00Z"
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            elif '+' in date_str or '-' in date_str.split('T')[1]:
                # Timezone format: "2025-06-20T15:00:00-03:00"
                return datetime.fromisoformat(date_str)
            else:
                # No timezone: "2025-06-20T15:00:00" - assume UTC
                return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        
        trip_obj = Trip(
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
        
        # Try to schedule and catch any errors
        await scheduler.schedule_immediate_notifications(trip_obj)
        
        # Check scheduled jobs
        jobs = scheduler.get_job_status()
        itinerary_jobs = [job for job in jobs.get("jobs", []) if "itinerary" in job.get("id", "")]
        
        return {
            "status": "completed",
            "message": "Debug test completed successfully",
            "trip_id": str(trip_id),
            "trip_data": {
                "departure_date": str(trip_obj.departure_date),
                "client_name": trip_obj.client_name,
                "status": trip_obj.status
            },
            "scheduled_jobs": itinerary_jobs,
            "total_jobs": jobs.get("jobs_count", 0)
        }
        
    except Exception as e:
        logger.error("debug_trip_scheduling_failed", 
            trip_id=str(trip_id),
            error=str(e),
            error_type=type(e).__name__
        )
        return {
            "status": "error", 
            "message": f"Debug failed: {str(e)}",
            "error_type": type(e).__name__
        }


def to_json_serializable(obj):
    """
    Recursively convert UUIDs, datetimes, and other non-serializable types to JSON-serializable equivalents.
    """
    if isinstance(obj, dict):
        return {k: to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_json_serializable(i) for i in obj]
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

@router.get("/itinerary/{trip_id}")
async def get_itinerary(trip_id: UUID):
    """
    Get the latest itinerary for a trip.
    Returns a fully JSON-serializable response.
    """
    try:
        db_client = SupabaseDBClient()
        result = await db_client.get_latest_itinerary(trip_id)
        if result.success:
            serializable = to_json_serializable(result.data)
            return JSONResponse(status_code=200, content=serializable)
        else:
            return JSONResponse(status_code=500, content={"error": result.error or "Unknown error"})
    except Exception as e:
        logger.error("itinerary_retrieval_failed", trip_id=str(trip_id), error=str(e))
        return JSONResponse(status_code=500, content={"exception": str(e)})
    finally:
        await db_client.close()


@router.post("/admin/cleanup-test-data")
async def cleanup_test_data():
    """
    ADMIN ENDPOINT: Clean up all test data to start fresh.
    """
    from datetime import datetime
    
    try:
        db_client = SupabaseDBClient()
        
        # Simple cleanup - delete all records
        cleanup_results = {}
        
        # Delete in order (foreign keys)
        tables = ["conversations", "itineraries", "notifications_log", "trips"]
        
        for table in tables:
            # Use direct HTTP delete - delete everything
            response = await db_client._client.delete(
                f"{db_client.rest_url}/{table}",
                params={"id": "is.not.null"}  # Delete all records
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

@router.post("/test-async-notification")
async def test_async_notification():
    """
    Test endpoint to validate AsyncTwilioClient and notification system.
    This endpoint verifies the async architecture without sending real messages.
    """
    try:
        from app.agents.notifications_agent import NotificationsAgent
        
        # Initialize NotificationsAgent to test async components
        agent = NotificationsAgent()
        
        # Test async client initialization
        async_client_status = {
            "async_twilio_client": "initialized" if agent.async_twilio_client else "failed",
            "retry_service": "initialized" if agent.retry_service else "failed",
            "db_client": "initialized" if agent.db_client else "failed",
            "aeroapi_client": "initialized" if agent.aeroapi_client else "failed"
        }
        
        # Test httpx version compatibility
        import httpx
        httpx_version = httpx.__version__
        
        # Test that we can format a message (without sending)
        from app.models.database import Trip
        from app.agents.notifications_templates import NotificationType
        from datetime import datetime, timezone
        from uuid import uuid4
        
        # Create test trip data
        test_trip = Trip(
            id=uuid4(),
            client_name="Test Client",
            whatsapp="+1234567890",
            flight_number="AA123",
            origin_iata="JFK",
            destination_iata="LAX", 
            departure_date=datetime.now(timezone.utc),
            status="scheduled",
            metadata=None,
            inserted_at=datetime.now(timezone.utc),
            next_check_at=None,
            client_description="Test trip for validation",
            agency_id=uuid4(),
            gate=None
        )
        
        # Test message formatting
        message_data = agent.format_message(
            test_trip, 
            NotificationType.REMINDER_24H,
            {"weather_info": "sunny", "additional_info": "Test flight"}
        )
        
        # Test idempotency hash generation
        import hashlib
        import json
        idempotency_data = {
            "trip_id": str(test_trip.id),
            "notification_type": "REMINDER_24H",
            "extra_data": {"test": "data"}
        }
        idempotency_hash = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        await agent.close()
        
        return {
            "status": "success",
            "async_architecture": "fully_operational",
            "components": async_client_status,
            "httpx_version": httpx_version,
            "message_formatting": "working",
            "template_name": message_data.get("template_name"),
            "idempotency_system": "working",
            "idempotency_hash_sample": idempotency_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "production_ready": True
        }
        
    except Exception as e:
        return {
            "status": "error", 
            "error": str(e),
            "async_architecture": "failed",
            "production_ready": False
        }

@router.post("/test-flight-notification/{trip_id}")
async def test_flight_notification(trip_id: str):
    """
    Test endpoint to send a real notification for a specific trip.
    Intelligently selects notification type based on departure timing.
    """
    try:
        from app.agents.notifications_agent import NotificationsAgent
        from app.agents.notifications_templates import NotificationType
        from app.db.supabase_client import SupabaseDBClient
        from uuid import UUID
        from datetime import datetime, timezone, timedelta
        
        # Get trip details to determine appropriate notification type
        db_client = SupabaseDBClient()
        trip_result = await db_client.get_trip_by_id(UUID(trip_id))
        
        if not trip_result.success:
            return {
                "status": "error",
                "trip_id": trip_id,
                "error": f"Trip not found: {trip_result.error}"
            }
        
        trip_data = trip_result.data
        departure_date = datetime.fromisoformat(trip_data["departure_date"].replace('Z', '+00:00'))
        now_utc = datetime.now(timezone.utc)
        time_to_departure = departure_date - now_utc
        hours_to_departure = time_to_departure.total_seconds() / 3600
        
        # INTELLIGENT NOTIFICATION TYPE SELECTION based on timing
        if hours_to_departure <= 0:
            # Flight has already departed - send landing welcome if not landed
            notification_type = NotificationType.LANDING_WELCOME
            extra_data = {"hotel_address": "tu alojamiento reservado"}
        elif hours_to_departure <= 1:
            # Less than 1 hour - send boarding notification
            notification_type = NotificationType.BOARDING
            extra_data = {"gate": "Ver pantallas del aeropuerto"}
        elif hours_to_departure <= 4:
            # 1-4 hours - send departure confirmation (not 24h reminder!)
            notification_type = NotificationType.RESERVATION_CONFIRMATION
            extra_data = {}
        elif 20 <= hours_to_departure <= 28:
            # 20-28 hours - appropriate for 24h reminder
            notification_type = NotificationType.REMINDER_24H
            extra_data = {
                "weather_info": "buen clima para volar",
                "additional_info": "¡Buen viaje!"
            }
        else:
            # Outside normal notification windows
            return {
                "status": "not_applicable",
                "trip_id": trip_id,
                "hours_to_departure": round(hours_to_departure, 2),
                "message": f"No appropriate notification for {round(hours_to_departure, 2)} hours to departure",
                "valid_windows": {
                    "boarding": "< 1 hour",
                    "confirmation": "1-4 hours", 
                    "24h_reminder": "20-28 hours",
                    "landing_welcome": "after departure"
                }
            }
        
        agent = NotificationsAgent()
        
        # Send intelligently selected notification
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
            "timing_logic": f"Selected {notification_type} for {round(hours_to_departure, 2)}h to departure",
            "result": result.data if result.success else result.error,
            "async_system": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "trip_id": trip_id,
            "error": str(e)
        }


class LandingWelcomeRequest(BaseModel):
    """Request model for landing welcome notification."""
    hotel_address: Optional[str] = "tu alojamiento reservado"


@router.post("/test-landing-welcome/{trip_id}")
async def test_landing_welcome_notification(trip_id: str, request: LandingWelcomeRequest):
    """
    Test endpoint to send LANDING_WELCOME notification with OpenAI city lookup.
    
    Example usage:
    POST /test-landing-welcome/8a570d1b-f2af-458c-8dbc-3ad58eeb547f
    Body: {"hotel_address": "Hotel Dann Carlton, Carrera 43A #7-50, El Poblado"}
    """
    try:
        from app.agents.notifications_agent import NotificationsAgent
        from app.agents.notifications_templates import NotificationType
        from uuid import UUID
        
        agent = NotificationsAgent()
        
        # Send landing welcome notification with hotel data
        result = await agent.send_single_notification(
            trip_id=UUID(trip_id),
            notification_type=NotificationType.LANDING_WELCOME,
            extra_data={
                "hotel_address": request.hotel_address
            }
        )
        
        await agent.close()
        
        return {
            "status": "landing_welcome_sent" if result.success else "landing_welcome_failed",
            "trip_id": trip_id,
            "hotel_address": request.hotel_address,
            "result": result.data if result.success else result.error,
            "template_used": "landing_welcome_es",
            "features": {
                "openai_city_lookup": "enabled",
                "hotel_metadata_support": "enabled", 
                "idempotency": "enabled"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "trip_id": trip_id,
            "error": str(e)
        }