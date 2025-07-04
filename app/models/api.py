"""API models for Bauhaus Travel endpoints."""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from uuid import UUID


class DocumentUploadPayload(BaseModel):
    """Payload for document upload endpoint."""
    
    trip_id: UUID = Field(..., description="UUID of the trip this document belongs to")
    document_type: str = Field(..., description="Type of document", example="boarding_pass")
    file_url: str = Field(..., description="URL where the document is stored", example="https://www.orimi.com/pdf-test.pdf")
    file_name: Optional[str] = Field(None, description="Original filename", example="boarding_pass_test.pdf")
    uploaded_by: str = Field(default="api_integration", description="Who uploaded the document", example="valentin")
    uploaded_by_type: str = Field(default="api_integration", description="Type of uploader", example="client")
    agency_id: Optional[UUID] = Field(None, description="Agency ID for multi-tenant support")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata as JSON object")
    
    @validator('document_type')
    def validate_document_type(cls, v):
        """Validate document type is one of the allowed values."""
        valid_types = [
            'boarding_pass', 'hotel_reservation', 'car_rental', 
            'transfer', 'insurance', 'tour_reservation'
        ]
        if v not in valid_types:
            raise ValueError(f'document_type must be one of: {", ".join(valid_types)}')
        return v
    
    @validator('uploaded_by_type')
    def validate_uploaded_by_type(cls, v):
        """Validate uploader type is one of the allowed values."""
        valid_types = ['agency_agent', 'system', 'client', 'api_integration']
        if v not in valid_types:
            raise ValueError(f'uploaded_by_type must be one of: {", ".join(valid_types)}')
        return v
    
    @validator('file_url')
    def validate_file_url(cls, v):
        """Basic URL validation."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('file_url must be a valid HTTP/HTTPS URL')
        return v
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "trip_id": "a8bff854-da9f-44e8-9f71-16bbb7438891",
                "document_type": "boarding_pass",
                "file_url": "https://www.orimi.com/pdf-test.pdf",
                "file_name": "boarding_pass_test.pdf",
                "uploaded_by": "valentin",
                "uploaded_by_type": "client"
            }
        }


class DocumentUploadResponse(BaseModel):
    """Response for document upload endpoint."""
    
    success: bool = Field(..., description="Whether the upload was successful")
    message: str = Field(..., description="Human-readable message")
    document_id: Optional[str] = Field(None, description="ID of the created document")
    trip_id: str = Field(..., description="Trip ID the document was attached to")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Document uploaded successfully",
                "document_id": "doc_123456789",
                "trip_id": "a8bff854-da9f-44e8-9f71-16bbb7438891"
            }
        }


# ========================
# AGENCY MODELS (TC-005)
# ========================

class AgencyCreate(BaseModel):
    """Model for creating a new agency."""
    
    name: str = Field(..., min_length=2, max_length=100, description="Agency name", example="Viajes Premium")
    email: str = Field(..., description="Contact email", example="info@viajespremium.com")
    phone: Optional[str] = Field(None, description="Contact phone", example="+5491140383422")
    website: Optional[str] = Field(None, description="Agency website", example="https://viajespremium.com")
    country: str = Field(default="AR", description="Country code", example="AR")
    
    @validator('email')
    def validate_email(cls, v):
        """Basic email validation."""
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower()
    
    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number format."""
        if v and not v.startswith('+'):
            raise ValueError('Phone number must include country code (e.g., +5491140383422)')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Viajes Premium",
                "email": "info@viajespremium.com",
                "phone": "+5491140383422",
                "website": "https://viajespremium.com",
                "country": "AR"
            }
        }


class AgencyResponse(BaseModel):
    """Response model for agency operations."""
    
    id: UUID = Field(..., description="Agency UUID")
    name: str = Field(..., description="Agency name")
    email: str = Field(..., description="Contact email")
    phone: Optional[str] = Field(None, description="Contact phone")
    website: Optional[str] = Field(None, description="Agency website")
    country: str = Field(..., description="Country code")
    status: str = Field(..., description="Agency status")
    branding: Dict[str, Any] = Field(default_factory=dict, description="Branding configuration")
    pricing_tier: str = Field(..., description="Pricing tier")
    created_at: str = Field(..., description="Creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "a8bff854-da9f-44e8-9f71-16bbb7438891",
                "name": "Viajes Premium",
                "email": "info@viajespremium.com",
                "phone": "+5491140383422",
                "website": "https://viajespremium.com",
                "country": "AR",
                "status": "active",
                "branding": {
                    "display_name": "Viajes Premium",
                    "color": "#ff6b6b",
                    "logo_url": ""
                },
                "pricing_tier": "startup",
                "created_at": "2025-01-16T10:30:00Z"
            }
        }


class AgencyStats(BaseModel):
    """Agency statistics and metrics."""
    
    total_trips: int = Field(..., description="Total trips created")
    active_trips: int = Field(..., description="Active trips (upcoming)")
    total_conversations: int = Field(..., description="Total AI conversations")
    satisfaction_rate: float = Field(..., description="Customer satisfaction rate (0-1)")
    revenue_current_month: float = Field(..., description="Revenue current month (USD)")
    revenue_total: float = Field(..., description="Total revenue (USD)")
    top_destinations: list = Field(..., description="Top destination cities")
    avg_response_time: float = Field(..., description="Average AI response time (seconds)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_trips": 145,
                "active_trips": 23,
                "total_conversations": 892,
                "satisfaction_rate": 0.94,
                "revenue_current_month": 12450.0,
                "revenue_total": 45230.0,
                "top_destinations": ["Miami", "Barcelona", "Paris", "Rome"],
                "avg_response_time": 1.8
            }
        }


class AgencyBranding(BaseModel):
    """Agency branding configuration."""
    
    display_name: str = Field(..., description="Name shown to customers", example="Viajes Premium")
    color: Optional[str] = Field(None, description="Brand color (hex)", example="#ff6b6b")
    logo_url: Optional[str] = Field(None, description="Logo URL", example="https://example.com/logo.png")
    welcome_message: Optional[str] = Field(None, description="Custom welcome message")
    
    @validator('color')
    def validate_color(cls, v):
        """Validate hex color format."""
        if v and not v.startswith('#'):
            v = f"#{v}"
        if v and len(v) != 7:
            raise ValueError('Color must be in hex format (#rrggbb)')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "display_name": "Viajes Premium",
                "color": "#ff6b6b",
                "logo_url": "https://viajespremium.com/logo.png",
                "welcome_message": "¡Bienvenido a Viajes Premium! Tu asistente AI está aquí para ayudarte."
            }
        } 