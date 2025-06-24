"""Main FastAPI application for Bauhaus Travel."""

import os
import sys
import structlog
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from .api.webhooks import router as webhooks_router
from .router import router as trips_router
from .api.conversations import router as conversations_router
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
    description="AI-powered travel assistant with autonomous agents",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhooks_router)
app.include_router(trips_router)
app.include_router(conversations_router, prefix="/conversations", tags=["conversations"])


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
    """Enhanced health check endpoint for Railway debugging."""
    env_status = {
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
        "PORT": os.getenv("PORT", "not_set"),
        "has_supabase_url": bool(os.getenv("SUPABASE_URL")),
        "has_supabase_key": bool(os.getenv("SUPABASE_KEY")),
        "has_openai_key": bool(os.getenv("OPENAI_API_KEY")),
        "has_twilio_sid": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "has_aero_key": bool(os.getenv("AERO_API_KEY"))
    }
    
    scheduler_status = scheduler_service.get_job_status() if scheduler_service else {"status": "not_started"}
    
    return {
        "status": "healthy",
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