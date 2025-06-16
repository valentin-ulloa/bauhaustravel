from fastapi import APIRouter, HTTPException
from uuid import UUID
from app.db.supabase_client import SupabaseDBClient
from app.models.database import DatabaseResult
import traceback
import logging

router = APIRouter()
db_client = SupabaseDBClient()

@router.get("/{trip_id}")
async def get_conversations(trip_id: UUID):
    """
    Get conversation history for a trip.
    
    Args:
        trip_id: UUID of the trip
        
    Returns:
        List of conversation records
    """
    try:
        conversations = await db_client.get_recent_conversations(trip_id)
        if not conversations:
            raise HTTPException(status_code=404, detail="No conversations found for this trip")
        return conversations
    except Exception as e:
        logging.error("conversations_endpoint_error", exc_info=True)
        raise 