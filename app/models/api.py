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
        schema_extra = {
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
        schema_extra = {
            "example": {
                "success": True,
                "message": "Document uploaded successfully",
                "document_id": "doc_123456789",
                "trip_id": "a8bff854-da9f-44e8-9f71-16bbb7438891"
            }
        } 