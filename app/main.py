"""Main FastAPI application for Bauhaus Travel."""

import os
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from .api.webhooks import router as webhooks_router
from .router import router as trips_router
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
    logger.info("application_starting")
    
    # Initialize and start scheduler
    scheduler_service = SchedulerService()
    await scheduler_service.start()
    
    logger.info("application_started", 
        scheduler_status="running",
        environment=os.getenv("ENVIRONMENT", "development")
    )
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    
    if scheduler_service:
        await scheduler_service.stop()
    
    logger.info("application_shutdown_complete")

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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Bauhaus Travel API - AI Travel Assistant",
        "status": "operational",
        "agents": [
            "NotificationsAgent - Flight updates and reminders",
            "ItineraryAgent - AI-powered travel itineraries", 
            "ConciergeAgent - 24/7 WhatsApp assistant"
        ],
        "scheduler": scheduler_service.get_job_status() if scheduler_service else {"status": "not_started"}
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "bauhaus-travel",
        "scheduler": scheduler_service.get_job_status() if scheduler_service else {"status": "not_started"}
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