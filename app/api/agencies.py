from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from uuid import UUID
import structlog
from app.models.api import AgencyCreate, AgencyResponse, AgencyStats
from app.db.supabase_client import SupabaseDBClient

logger = structlog.get_logger()
router = APIRouter(prefix="/agencies", tags=["agencies"])

@router.post("/", response_model=AgencyResponse)
async def create_agency(agency: AgencyCreate):
    """Create a new agency account"""
    db_client = SupabaseDBClient()
    try:
        # Check if agency already exists
        existing = await db_client.get_agency_by_email(agency.email)
        if existing:
            raise HTTPException(status_code=409, detail="Agency already exists")
        
        # Create agency
        result = await db_client.create_agency(agency.model_dump())
        if not result.success:
            raise HTTPException(status_code=500, detail="Failed to create agency")
        
        logger.info("agency_created", agency_id=result.data["id"], name=agency.name)
        return AgencyResponse(**result.data)
    
    finally:
        await db_client.close()

@router.get("/{agency_id}/stats", response_model=AgencyStats)
async def get_agency_stats(agency_id: UUID):
    """Get agency statistics and metrics"""
    db_client = SupabaseDBClient()
    try:
        stats = await db_client.get_agency_stats(agency_id)
        if not stats.success:
            raise HTTPException(status_code=404, detail="Agency not found")
        
        return AgencyStats(**stats.data)
    
    finally:
        await db_client.close()

@router.get("/{agency_id}/trips")
async def get_agency_trips(agency_id: UUID, limit: int = 50):
    """Get all trips for an agency"""
    db_client = SupabaseDBClient()
    try:
        trips = await db_client.get_trips_by_agency(agency_id, limit)
        return {"trips": trips, "total": len(trips)}
    
    finally:
        await db_client.close()

@router.post("/{agency_id}/branding")
async def update_agency_branding(agency_id: UUID, branding: dict):
    """Update agency branding configuration"""
    db_client = SupabaseDBClient()
    try:
        result = await db_client.update_agency_branding(agency_id, branding)
        if not result.success:
            raise HTTPException(status_code=500, detail="Failed to update branding")
        
        logger.info("agency_branding_updated", agency_id=agency_id)
        return {"message": "Branding updated successfully"}
    
    finally:
        await db_client.close() 