"""Database models for Bauhaus Travel."""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


class TripCreate(BaseModel):
    """Model for creating new trips."""
    client_name: str = Field(..., min_length=1, max_length=100)
    whatsapp: str = Field(..., min_length=10, max_length=20)  # International format
    flight_number: str = Field(..., min_length=3, max_length=10)
    origin_iata: str = Field(..., min_length=3, max_length=3)
    destination_iata: str = Field(..., min_length=3, max_length=3)
    departure_date: datetime
    status: str = "SCHEDULED"  # Default status
    metadata: Optional[dict] = None
    client_description: Optional[str] = None


class Trip(BaseModel):
    """Model for trips table records."""
    id: UUID
    client_name: str
    whatsapp: str
    flight_number: str
    origin_iata: str = Field(max_length=3)
    destination_iata: str = Field(max_length=3)
    departure_date: datetime
    status: str
    metadata: Optional[dict] = None
    inserted_at: datetime
    next_check_at: Optional[datetime] = None
    client_description: Optional[str] = None


class NotificationLog(BaseModel):
    """Model for notifications_log table records."""
    id: Optional[UUID] = None
    trip_id: UUID
    notification_type: Literal[
        "reservation_confirmation", 
        "reminder_24h", 
        "delayed", 
        "gate_change", 
        "cancelled", 
        "boarding"
    ]
    template_name: str
    delivery_status: Literal["SENT", "FAILED", "PENDING"] = "PENDING"
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    twilio_message_sid: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatabaseResult(BaseModel):
    """Generic result wrapper for database operations."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    affected_rows: int = 0 