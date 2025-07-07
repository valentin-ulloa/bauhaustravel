"""Main FastAPI application for Bauhaus Travel."""

import os
import sys
import structlog
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import traceback

from .api.webhooks import router as webhooks_router
from .router import router as trips_router
from .api.conversations import router as conversations_router
from .api.trips import router as test_trips_router
# Removed production_alerts import - module was deleted during refactor
from .services.scheduler_service import SchedulerService

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global scheduler instance
scheduler_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown"""
    global scheduler_service
    
    # Startup
    logger.info("application_starting", 
        python_version=sys.version,
        environment=os.getenv("ENVIRONMENT", "development"),
        port=os.getenv("PORT", "8000"),
        deployment_time=datetime.utcnow().isoformat()
    )
    
    # Log environment variables (safely)
    env_vars = {
        "ENVIRONMENT": os.getenv("ENVIRONMENT"),
        "PORT": os.getenv("PORT"),
        "SUPABASE_URL": "***" if os.getenv("SUPABASE_URL") else "NOT_SET",
        "SUPABASE_KEY": "***" if os.getenv("SUPABASE_KEY") else "NOT_SET",
        "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else "NOT_SET",
        "TWILIO_ACCOUNT_SID": "***" if os.getenv("TWILIO_ACCOUNT_SID") else "NOT_SET",
        "AERO_API_KEY": "***" if os.getenv("AERO_API_KEY") else "NOT_SET"
    }
    logger.info("environment_check", env_status=env_vars)
    
    try:
        # Initialize and start scheduler
        scheduler_service = SchedulerService()
        await scheduler_service.start()
        
        logger.info("application_started", 
            scheduler_status="running",
            success=True
        )
    except Exception as e:
        logger.error("application_startup_failed", error=str(e), error_type=type(e).__name__)
        raise
    
    # Start scheduler service for automated notifications
    try:
        await scheduler_service.start()
        logger.info("scheduler_started", 
                   jobs_count=len(scheduler_service.scheduler.get_jobs()),
                   startup_time=datetime.utcnow().isoformat())
    except Exception as e:
        logger.error("scheduler_startup_failed", error=str(e), traceback=traceback.format_exc())
        # Don't fail the app if scheduler fails to start
        pass
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    
    try:
        if scheduler_service:
            await scheduler_service.stop()
        logger.info("application_shutdown_complete", success=True)
    except Exception as e:
        logger.error("application_shutdown_failed", error=str(e))

# Create FastAPI application
app = FastAPI(
    title="Bauhaus Travel API",
    description="AI-powered travel assistant with WhatsApp integration",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for V0.dev and frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "http://localhost:5173",  # Vite dev server
        "https://*.vercel.app",   # Vercel deployments
        "https://*.netlify.app",  # Netlify deployments  
        "https://*.v0.dev",       # V0.dev preview
        "https://web-production-92d8d.up.railway.app"  # Same origin
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhooks_router)
app.include_router(trips_router)
app.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
app.include_router(test_trips_router, prefix="/trips", tags=["trips"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Bauhaus Travel API - AI Travel Assistant",
        "status": "operational",
        "version": "1.0.1",
        "deployment_time": datetime.utcnow().isoformat(),
        "agents": [
            "NotificationsAgent - Flight updates and reminders",
            "ItineraryAgent - AI-powered travel itineraries", 
            "ConciergeAgent - 24/7 WhatsApp assistant"
        ],
        "scheduler": scheduler_service.get_job_status() if scheduler_service else {"status": "not_started"}
    }


@app.get("/health")
async def health():
    """Enhanced health check endpoint for Railway debugging with error monitoring."""
    env_status = {
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
        "PORT": os.getenv("PORT", "not_set"),
        "has_supabase_url": bool(os.getenv("SUPABASE_URL")),
        "has_supabase_key": bool(os.getenv("SUPABASE_KEY")),
        "has_openai_key": bool(os.getenv("OPENAI_API_KEY")),
        "has_twilio_sid": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "has_aero_key": bool(os.getenv("AERO_API_KEY")),
        "has_alert_webhook": bool(os.getenv("ALERT_WEBHOOK_URL"))
    }
    
    scheduler_status = scheduler_service.get_job_status() if scheduler_service else {"status": "not_started"}
    
    # Determine overall health status
    health_status = "healthy"
    if scheduler_status.get("status") != "running":
        health_status = "warning"
    
    return {
        "status": health_status,
        "service": "bauhaus-travel",
        "timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version,
        "environment": env_status,
        "scheduler": scheduler_status
    }

@app.get("/deployment-info")
async def deployment_info():
    """Deployment debugging information."""
    return {
        "deployment_timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version,
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "port": os.getenv("PORT", "unknown"),
        "scheduler_active": scheduler_service is not None,
        "cwd": os.getcwd(),
        "python_path": sys.path[:3],  # First 3 entries
        "env_vars_count": len(os.environ),
        "platform": sys.platform
    }

@app.get("/test-concierge-timezone/{trip_id}")
async def test_concierge_timezone(trip_id: str):
    """
    Test timezone fix in ConciergeAgent without WhatsApp integration.
    
    This endpoint simulates a flight info request to verify the timezone
    conversion is working correctly.
    """
    from app.agents.concierge_agent import ConciergeAgent
    from app.db.supabase_client import SupabaseDBClient
    from app.models.database import Trip
    
    try:
        # Get the trip
        db_client = SupabaseDBClient()
        trip_result = await db_client.get_trip_by_id(trip_id)
        
        if not trip_result.success:
            return {"error": f"Trip not found: {trip_result.error}"}
        
        trip = Trip(**trip_result.data)
        
        # Test ConciergeAgent._handle_flight_info_request directly
        concierge = ConciergeAgent()
        
        # Call the method that formats flight info
        flight_info_response = await concierge._handle_flight_info_request(trip)
        
        await concierge.close()
        await db_client.close()
        
        return {
            "trip_id": trip_id,
            "flight_number": trip.flight_number,
            "origin_iata": trip.origin_iata,
            "departure_date_utc": trip.departure_date.isoformat(),
            "concierge_response": flight_info_response,
            "validation": {
                "utc_time": trip.departure_date.strftime("%H:%M"),
                "expected_local_time": "14:32 hs" if trip.origin_iata == "EZE" else "local time",
                "timezone_fix_applied": "✅ if shows local time, ❌ if shows UTC"
            }
        }
    
    except Exception as e:
        return {"error": f"Test failed: {str(e)}"}



# Utility function to access scheduler from other modules
def get_scheduler() -> SchedulerService:
    """Get the global scheduler instance"""
    return scheduler_service

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True if os.getenv("ENVIRONMENT") == "development" else False,
        log_level="info"
    ) 