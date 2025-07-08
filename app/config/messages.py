"""
Message configuration for Bauhaus Travel notifications.

This module centralizes all user-facing text to enable:
- Easy translation/localization
- White-label customization per agency
- Quick copy changes without code deployment
"""

from typing import Dict, Any
import os


class MessageConfig:
    """Configuration for notification messages and text content."""
    
    # Default Spanish messages
    DEFAULT_WEATHER_TEXT = "buen clima para volar"
    DEFAULT_GOOD_TRIP_TEXT = "¡Buen viaje!"
    DEFAULT_HOTEL_PLACEHOLDER = "tu alojamiento reservado"
    DEFAULT_GATE_PLACEHOLDER = "Ver pantallas"
    DEFAULT_ETA_UNKNOWN = "Por confirmar"
    
    # Boarding notifications
    BOARDING_GATE_FALLBACK = "Ver pantallas del aeropuerto"
    
    # Landing welcome messages
    LANDING_CITY_FALLBACK = "tu destino"
    LANDING_HOTEL_FALLBACK = "tu alojamiento reservado"
    
    # Error messages (internal)
    ERROR_FLIGHT_NOT_FOUND = "Vuelo no encontrado"
    ERROR_API_UNAVAILABLE = "Servicio temporal no disponible"
    
    @classmethod
    def get_message(cls, key: str, agency_id: str = None, fallback: str = None) -> str:
        """
        Get localized message for agency or use default.
        
        Args:
            key: Message key (e.g., 'weather_text', 'good_trip')
            agency_id: Optional agency ID for custom messages
            fallback: Fallback text if key not found
            
        Returns:
            Localized message text
        """
        # TODO: Implement agency-specific message lookup from database
        # For now, return defaults
        
        defaults = {
            "weather_text": cls.DEFAULT_WEATHER_TEXT,
            "good_trip": cls.DEFAULT_GOOD_TRIP_TEXT,
            "hotel_placeholder": cls.DEFAULT_HOTEL_PLACEHOLDER,
            "gate_placeholder": cls.DEFAULT_GATE_PLACEHOLDER,
            "eta_unknown": cls.DEFAULT_ETA_UNKNOWN,
            "boarding_gate_fallback": cls.BOARDING_GATE_FALLBACK,
            "landing_city_fallback": cls.LANDING_CITY_FALLBACK,
            "landing_hotel_fallback": cls.LANDING_HOTEL_FALLBACK
        }
        
        return defaults.get(key, fallback or key)
    
    @classmethod
    async def get_weather_text_async(cls, destination_iata: str, agency_id: str = None) -> str:
        """
        Get real weather text for 24h reminders.
        
        Args:
            destination_iata: Destination airport for weather lookup
            agency_id: Optional agency ID for custom messages
            
        Returns:
            Real weather description or fallback text
        """
        try:
            from ..services.weather_service import WeatherService
            weather_service = WeatherService()
            return await weather_service.get_weather_for_destination(destination_iata)
        except Exception:
            # Fallback to static text if weather service fails
            return cls.get_message("weather_text", agency_id, cls.DEFAULT_WEATHER_TEXT)
    
    @classmethod
    def get_weather_text(cls, agency_id: str = None) -> str:
        """Get fallback weather text for 24h reminders (sync version)."""
        return cls.get_message("weather_text", agency_id, cls.DEFAULT_WEATHER_TEXT)
    
    @classmethod
    def get_good_trip_text(cls, agency_id: str = None) -> str:
        """Get good trip text for 24h reminders."""
        return cls.get_message("good_trip", agency_id, cls.DEFAULT_GOOD_TRIP_TEXT)
    
    @classmethod
    def get_hotel_placeholder(cls, agency_id: str = None) -> str:
        """Get hotel placeholder for landing welcome."""
        return cls.get_message("hotel_placeholder", agency_id, cls.DEFAULT_HOTEL_PLACEHOLDER)
    
    @classmethod
    def get_gate_placeholder(cls, agency_id: str = None) -> str:
        """Get gate placeholder for boarding notifications."""
        return cls.get_message("gate_placeholder", agency_id, cls.DEFAULT_GATE_PLACEHOLDER)
    
    @classmethod
    def get_eta_unknown_text(cls, agency_id: str = None) -> str:
        """Get text for unknown ETA."""
        return cls.get_message("eta_unknown", agency_id, cls.DEFAULT_ETA_UNKNOWN)


# Environment-based overrides
def get_env_message(key: str, default: str) -> str:
    """Get message from environment variable or use default."""
    env_key = f"BAUHAUS_MSG_{key.upper()}"
    return os.getenv(env_key, default)


# Agency-specific message loading (future enhancement)
async def load_agency_messages(agency_id: str) -> Dict[str, str]:
    """
    Load custom messages for an agency from database.
    
    Args:
        agency_id: UUID of the agency
        
    Returns:
        Dict with custom message overrides
    """
    # TODO: Implement database lookup for agency_settings.messages
    # This would allow white-label agencies to customize all copy
    
    return {} 