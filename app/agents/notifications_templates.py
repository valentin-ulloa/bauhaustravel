"""WhatsApp template definitions for Bauhaus Travel notifications."""

import os
from typing import Dict, Any
from enum import Enum
from datetime import datetime


class NotificationType(str, Enum):
    """Notification types for template selection."""
    RESERVATION_CONFIRMATION = "reservation_confirmation"
    REMINDER_24H = "reminder_24h"
    DELAYED = "delayed"
    GATE_CHANGE = "gate_change"
    CANCELLED = "cancelled"
    BOARDING = "boarding"
    ITINERARY_READY = "itinerary_ready"
    LANDING_WELCOME = "landing_welcome"


class WhatsAppTemplates:
    """Centralized WhatsApp template management with actual Twilio template SIDs."""
    
    # Actual Twilio template SIDs and names
    TEMPLATES = {
        NotificationType.RESERVATION_CONFIRMATION: {
            "name": "copy_confirmacion_reserva", 
            "sid": "HXb777321419cee086713f1cb529d7fe51"
        },
        NotificationType.REMINDER_24H: {
            "name": "recordatorio_24h",
            "sid": "HXf79f6f380e09de4f1b953f7045c6aa19"
        },
        NotificationType.DELAYED: {
            "name": "demorado", 
            "sid": "HXd5b757e51d032582949292a65a5afee1"
        },
        NotificationType.GATE_CHANGE: {
            "name": "cambio_gate",
            "sid": "HXd38d96ab6414b96fe214b132253c364e"
        },
        NotificationType.CANCELLED: {
            "name": "cancelado",
            "sid": "HX1672fabd1ce98f5b7d06f1306ba3afcc"
        },
        NotificationType.BOARDING: {
            "name": "embarcando",
            "sid": "HX3571933547ed2f3b6e4c6dc64a84f3b7"
        },
        NotificationType.ITINERARY_READY: {
            "name": "itinerario",
            "sid": "HXa031416ae1602595485bfda7df043545"
        },
        NotificationType.LANDING_WELCOME: {
            "name": "landing_welcome_es",
            "sid": "HXb9775d224136e998bca4772d854b7169"  
        }
    }
    
    @classmethod
    def get_template_info(cls, notification_type: NotificationType) -> Dict[str, str]:
        """Get Twilio template info (name and SID) for notification type."""
        template_info = cls.TEMPLATES[notification_type]
        
        # FIXED: Validate that LANDING_WELCOME template SID is properly configured
        if notification_type == NotificationType.LANDING_WELCOME:
            landing_sid = template_info["sid"]
            if not landing_sid or landing_sid == "HXb9775d224136e998bca4772d854b7169":
                # Using default placeholder SID, check if environment variable is set
                env_sid = os.getenv("TWILIO_TEMPLATE_LANDING_SID")
                if not env_sid:
                    raise ValueError(
                        "LANDING_WELCOME template requires TWILIO_TEMPLATE_LANDING_SID environment variable. "
                        "Please set it to your actual Twilio template SID."
                    )
        
        return template_info
    
    @classmethod
    def get_template_sid(cls, notification_type: NotificationType) -> str:
        """Get Twilio template SID for notification type."""
        return cls.TEMPLATES[notification_type]["sid"]
    
    @classmethod
    def format_24h_reminder(cls, trip_data: Dict[str, Any], weather_info: str = "", additional_info: str = "") -> Dict[str, Any]:
        """
        Format 24h flight reminder template variables.
        
        Template: recordatorio_24h (HXf79f6f380e09de4f1b953f7045c6aa19)
        Variables: {{1}} name, {{2}} origin, {{3}} departure_time, {{4}} weather, {{5}} destination, {{6}} additional_info
        """
        from ..config.messages import MessageConfig
        from ..utils.timezone_utils import format_departure_time_local
        
        # FIXED: Use format_departure_time_local for 24h reminders to avoid grammatical errors
        # This gives clean format like "8 Jul 11:30 hs" instead of "Mar 8 Jul 11:30 hs"
        departure_datetime = trip_data.get("departure_date")
        if isinstance(departure_datetime, str):
            from datetime import datetime
            departure_datetime = datetime.fromisoformat(departure_datetime.replace('Z', '+00:00'))
        
        # Use local time formatting without weekday for 24h reminders
        formatted_departure = format_departure_time_local(departure_datetime, trip_data["origin_iata"])
        
        template_info = cls.TEMPLATES[NotificationType.REMINDER_24H]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"],        # name
                "2": trip_data["origin_iata"],        # origin
                "3": formatted_departure,             # departure_time (clean format without weekday)
                "4": weather_info or MessageConfig.get_weather_text(),   # weather
                "5": trip_data["destination_iata"],   # destination
                "6": additional_info or MessageConfig.get_good_trip_text() # additional_info
            }
        }
    
    @classmethod
    def format_delayed_flight(cls, trip_data: Dict[str, Any], new_departure_time: str) -> Dict[str, Any]:
        """
        Format delayed flight notification.
        
        Template: demorado (HXd5b757e51d032582949292a65a5afee1)
        Variables: {{1}} name, {{2}} flight_number, {{3}} new_departure_time
        """
        from ..utils.timezone_utils import format_departure_time_human
        from ..config.messages import MessageConfig
        
        # Format new_departure_time if it's not already human readable
        if new_departure_time and new_departure_time != "Por confirmar":
            try:
                if "T" in new_departure_time:  # ISO format
                    dt = datetime.fromisoformat(new_departure_time.replace('Z', '+00:00'))
                    formatted_time = format_departure_time_human(dt, trip_data["origin_iata"])
                else:
                    formatted_time = new_departure_time  # Already formatted
            except:
                formatted_time = MessageConfig.get_eta_unknown_text()
        else:
            formatted_time = MessageConfig.get_eta_unknown_text()
        
        template_info = cls.TEMPLATES[NotificationType.DELAYED]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"],    # name
                "2": trip_data["flight_number"],  # flight_number
                "3": formatted_time               # new_departure_time (human readable)
            }
        }
    
    @classmethod
    def format_gate_change(cls, trip_data: Dict[str, Any], new_gate: str) -> Dict[str, Any]:
        """
        Format gate change notification.
        
        Template: cambio_gate (HXd38d96ab6414b96fe214b132253c364e)
        Variables: {{1}} name, {{2}} flight_number, {{3}} new_gate
        """
        template_info = cls.TEMPLATES[NotificationType.GATE_CHANGE]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"],    # name
                "2": trip_data["flight_number"],  # flight_number
                "3": new_gate                     # new_gate
            }
        }
    
    @classmethod
    def format_cancelled_flight(cls, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format cancelled flight notification.
        
        Template: cancelado (HX1672fabd1ce98f5b7d06f1306ba3afcc)
        Variables: {{1}} name, {{2}} flight_number
        """
        template_info = cls.TEMPLATES[NotificationType.CANCELLED]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"],    # name
                "2": trip_data["flight_number"]   # flight_number
            }
        }
    
    @classmethod
    def format_boarding_call(cls, trip_data: Dict[str, Any], gate: str) -> Dict[str, Any]:
        """
        Format boarding call notification.
        
        Template: embarcando (HX3571933547ed2f3b6e4c6dc64a84f3b7)
        Variables: {{1}} flight_number, {{2}} gate
        """
        template_info = cls.TEMPLATES[NotificationType.BOARDING]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["flight_number"],  # flight_number
                "2": gate                         # gate
            }
        }
    
    @classmethod
    def format_reservation_confirmation(cls, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format reservation confirmation notification.
        
        Template: confirmacion_reserva (HX01a541412cda42dd91bff6995fdc3f4a)
        Variables: {{1}} name, {{2}} flight_number, {{3}} origin, {{4}} destination, {{5}} departure_date (formatted with day of week)
        """
        from ..utils.timezone_utils import format_departure_time_human
        
        # Parse departure date (comes from DB as UTC ISO string)
        departure_datetime = datetime.fromisoformat(trip_data["departure_date"].replace('Z', '+00:00'))
        
        # FIXED: Use format_departure_time_human to include day of week (Lun, Mar, etc.)
        origin_iata = trip_data["origin_iata"]
        formatted_time = format_departure_time_human(departure_datetime, origin_iata)
        
        template_info = cls.TEMPLATES[NotificationType.RESERVATION_CONFIRMATION]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"],       # name
                "2": trip_data["flight_number"],     # flight_number
                "3": trip_data["origin_iata"],       # origin
                "4": trip_data["destination_iata"],  # destination
                "5": formatted_time                  # departure_date (formatted with day of week: "Lun 8 Jul 02:30 hs (EZE)")
            }
        }
    
    @classmethod
    def format_itinerary_ready(cls, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format itinerary ready notification.
        
        Template: itinerario (HXa031416ae1602595485bfda7df043545)
        Variables: {{1}} name
        """
        template_info = cls.TEMPLATES[NotificationType.ITINERARY_READY]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"],
            "template_variables": {
                "1": trip_data["client_name"]  # name
            }
        }
    
    @classmethod
    async def format_landing_welcome_async(cls, trip_data: Dict[str, Any], hotel_address: str = "tu alojamiento reservado") -> Dict[str, Any]:
        """
        Format landing welcome notification with async city name lookup.
        
        Template: landing_welcome_es (HXb9775d224136e998bca4772d854b7169)
        Message: ¡Llegaste a {{1}}! 🛬
                Tu alojamiento te espera en {{2}}.
                Si necesitás algo, estamos a disposición. ¡Disfrutá tu viaje! 🌍
        Variables: {{1}} destination_city, {{2}} hotel_address
        """
        from ..utils.timezone_utils import get_city_name_from_iata
        
        destination_iata = trip_data["destination_iata"]
        
        # Use async function to get city name (with OpenAI fallback)
        destination_city = await get_city_name_from_iata(destination_iata)
        
        # ENHANCED: Check for hotel information in multiple places with 'stay' as unified field name
        from ..config.messages import MessageConfig
        default_hotel_text = MessageConfig.get_hotel_placeholder()
        
        if hotel_address == default_hotel_text:
            # Priority 1: Check 'stay' field directly (unified field)
            if trip_data.get("stay"):
                hotel_address = trip_data["stay"]
            # Priority 2: Check metadata with multiple possible field names
            elif "metadata" in trip_data and trip_data["metadata"]:
                metadata = trip_data.get("metadata", {})
                if isinstance(metadata, dict):
                    # Look for hotel information in metadata (fallback compatibility)
                    hotel_info = (
                        metadata.get("stay") or  # Primary unified field name
                        metadata.get("hotel_address") or 
                        metadata.get("accommodation_address") or
                        metadata.get("hotel_name") or
                        metadata.get("hotel_info", {}).get("name") if isinstance(metadata.get("hotel_info"), dict) else None or
                        default_hotel_text
                    )
                    hotel_address = hotel_info
        
        template_info = cls.TEMPLATES[NotificationType.LANDING_WELCOME]
        return {
            "template_sid": template_info["sid"],
            "template_name": template_info["name"], 
            "template_variables": {
                "1": destination_city,    # destination_city (from OpenAI if needed)
                "2": hotel_address       # hotel_address from stay field or metadata fallback
            }
        }
    
    @classmethod
    def validate_template_exists(cls, notification_type: NotificationType) -> bool:
        """Check if template exists for notification type."""
        return notification_type in cls.TEMPLATES


# Template validation helpers
def get_required_variables(notification_type: NotificationType) -> list[str]:
    """Get required variables for each template type."""
    required_vars = {
        NotificationType.RESERVATION_CONFIRMATION: ["client_name", "flight_number", "origin_iata", "destination_iata", "departure_time"],
        NotificationType.REMINDER_24H: ["client_name", "origin_iata", "departure_time", "destination_iata"],
        NotificationType.DELAYED: ["client_name", "flight_number"],
        NotificationType.GATE_CHANGE: ["client_name", "flight_number"],
        NotificationType.CANCELLED: ["client_name", "flight_number"],
        NotificationType.BOARDING: ["flight_number"]
    }
    return required_vars.get(notification_type, [])


# Helper function to determine notification type based on flight status change
def get_notification_type_for_status(old_status: str, new_status: str, status_data: Dict[str, Any] = None) -> NotificationType:
    """
    Determine the appropriate notification type based on flight status changes.
    
    Args:
        old_status: Previous flight status
        new_status: Current flight status  
        status_data: Additional status information (e.g., gate changes)
        
    Returns:
        NotificationType for the appropriate template
    """
    status_data = status_data or {}
    
    # Check for specific status changes
    if "CANCEL" in new_status.upper():
        return NotificationType.CANCELLED
    elif "DELAY" in new_status.upper() or "LATE" in new_status.upper():
        return NotificationType.DELAYED
    elif "BOARD" in new_status.upper():
        return NotificationType.BOARDING
    elif status_data.get("gate_changed"):
        return NotificationType.GATE_CHANGE
    else:
        # Default to delayed for any other status change
        return NotificationType.DELAYED 