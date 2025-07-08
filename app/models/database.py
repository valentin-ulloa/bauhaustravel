"""Database models for Bauhaus Travel."""

import re
from datetime import datetime
from typing import Optional, Literal, List
from uuid import UUID
from pydantic import BaseModel, Field, validator


class TripCreate(BaseModel):
    """
    Model for creating new trips.
    
    TIMEZONE POLICY ENFORCEMENT:
    =============================
    All departure_date inputs are treated as LOCAL TIME of the origin airport
    and automatically converted to UTC for storage. This ensures consistency
    across all entry points and eliminates timezone confusion.
    """
    client_name: str = Field(..., min_length=1, max_length=100)
    whatsapp: str = Field(..., min_length=10, max_length=20)  # International format
    flight_number: str = Field(..., min_length=3, max_length=10)
    origin_iata: str = Field(..., min_length=3, max_length=3)
    destination_iata: str = Field(..., min_length=3, max_length=3)
    departure_date: datetime  # INPUT: Local airport time, STORAGE: Converted to UTC
    status: str = "SCHEDULED"  # Default status
    metadata: Optional[dict] = None
    client_description: Optional[str] = None
    agency_id: Optional[UUID] = None  # Agency association

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
    
    @validator('departure_date')
    def convert_local_to_utc(cls, v, values):
        """
        ARCHITECTURAL VALIDATION: Convert local departure time to UTC.
        
        This enforces the timezone policy at the model level, ensuring
        all departure times are consistently stored as UTC regardless
        of entry point (API, manual script, test, etc.).
        
        Args:
            v: departure_date input (assumed to be local airport time)
            values: other validated fields (need origin_iata)
            
        Returns:
            UTC datetime for database storage
        """
        # Import here to avoid circular imports
        from ..utils.timezone_utils import parse_local_time_to_utc
        
        origin_iata = values.get('origin_iata')
        if not origin_iata:
            raise ValueError('origin_iata must be provided before departure_date')
        
        # Convert local time to UTC using our timezone policy
        utc_datetime = parse_local_time_to_utc(v, origin_iata)
        
        return utc_datetime


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
    gate: Optional[str] = None  # Flight departure gate (e.g., "A12", "B3")
    estimated_arrival: Optional[datetime] = None  # Estimated arrival time from AeroAPI


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


class TripContext(BaseModel):
    trip: dict
    itinerary: Optional[dict]
    documents: List[dict]
    recent_messages: List[dict] 