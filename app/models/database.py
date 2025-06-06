"""Database models for Bauhaus Travel."""

import re
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field, validator


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

    @validator('whatsapp')
    def validate_whatsapp(cls, v):
        """Validate WhatsApp number format."""
        if not v:
            raise ValueError('WhatsApp number is required')
        
        # Remove common separators
        clean_number = re.sub(r'[^\d+]', '', v)
        
        # Basic validation: starts with + and has 10-15 digits
        if not re.match(r'^\+\d{10,15}$', clean_number):
            raise ValueError('WhatsApp number must be in international format (+1234567890)')
        
        return clean_number


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
    agency_id: Optional[UUID] = None


class NotificationLog(BaseModel):
    """Model for notifications_log table records."""
    id: Optional[UUID] = None
    trip_id: UUID
    notification_type: Literal[
        "RESERVATION_CONFIRMATION", 
        "REMINDER_24H", 
        "DELAYED", 
        "GATE_CHANGE", 
        "CANCELLED", 
        "BOARDING",
        "ITINERARY_READY"
    ]
    template_name: str
    delivery_status: Literal["SENT", "FAILED", "PENDING"] = "PENDING"
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    twilio_message_sid: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgencyPlace(BaseModel):
    """Model for agency_places table records."""
    id: Optional[UUID] = None
    agency_id: Optional[UUID] = None
    name: str
    address: Optional[str] = None
    city: str
    country: str  # ISO-2 code
    lat: Optional[float] = None
    lng: Optional[float] = None
    type: Optional[str] = None
    rating: Optional[float] = None
    opening_hours: Optional[str] = None
    tags: Optional[list[str]] = None


class Itinerary(BaseModel):
    """Model for itineraries table records."""
    id: Optional[UUID] = None
    trip_id: UUID
    version: int = 1
    status: str = "draft"  # draft | approved | regenerating
    generated_at: Optional[datetime] = None
    raw_prompt: Optional[str] = None
    raw_response: Optional[str] = None
    parsed_itinerary: dict  # JSON structure with days/items


class DatabaseResult(BaseModel):
    """Generic result wrapper for database operations."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    affected_rows: int = 0 