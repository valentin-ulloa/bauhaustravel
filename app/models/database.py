"""Database models for Bauhaus Travel."""

from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


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
    notification_type: Literal["24h_reminder", "status_change", "landing"]
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