"""Timezone utilities for flight notifications."""

from datetime import datetime, timezone
from typing import Dict, Optional
import pytz


# IATA airport code to timezone mapping
# Based on major airports across Latin America and North America
AIRPORT_TIMEZONES = {
    # Argentina
    "EZE": "America/Argentina/Buenos_Aires",  # Ezeiza
    "AEP": "America/Argentina/Buenos_Aires",  # Jorge Newbery Airfield
    "COR": "America/Argentina/Cordoba",       # Córdoba
    "MDZ": "America/Argentina/Mendoza",       # Mendoza
    "ROS": "America/Argentina/Cordoba",       # Rosario
    
    # Brazil  
    "GRU": "America/Sao_Paulo",               # São Paulo
    "GIG": "America/Sao_Paulo",               # Rio de Janeiro
    "BSB": "America/Sao_Paulo",               # Brasília
    "CGH": "America/Sao_Paulo",               # São Paulo Congonhas
    
    # Mexico
    "MEX": "America/Mexico_City",             # Mexico City
    "CUN": "America/Cancun",                  # Cancún
    "GDL": "America/Mexico_City",             # Guadalajara
    "TIJ": "America/Tijuana",                 # Tijuana
    
    # USA
    "MIA": "America/New_York",                # Miami (Eastern)
    "LAX": "America/Los_Angeles",             # Los Angeles
    "JFK": "America/New_York",                # New York JFK
    "NYC": "America/New_York",                # New York (general)
    "ORD": "America/Chicago",                 # Chicago O'Hare
    "DFW": "America/Chicago",                 # Dallas Fort Worth
    
    # Panama
    "PTY": "America/Panama",                  # Panama City
    
    # Chile
    "SCL": "America/Santiago",                # Santiago
    
    # Colombia
    "BOG": "America/Bogota",                  # Bogotá
    
    # Peru
    "LIM": "America/Lima",                    # Lima
    
    # Uruguay
    "MVD": "America/Montevideo",              # Montevideo
    
    # Costa Rica
    "SJO": "America/Costa_Rica",              # San José
    
    # Spain (for connections)
    "MAD": "Europe/Madrid",                   # Madrid
    "BCN": "Europe/Madrid",                   # Barcelona
    
    # Turkey (for connections)
    "IST": "Europe/Istanbul",                 # Istanbul
    
    # UK (for connections)
    "LHR": "Europe/London",                   # London Heathrow
    "LGW": "Europe/London",                   # London Gatwick
}


def get_airport_timezone(iata_code: str) -> Optional[pytz.BaseTzInfo]:
    """
    Get timezone for airport IATA code.
    
    Args:
        iata_code: 3-letter IATA airport code
        
    Returns:
        pytz timezone object or None if not found
    """
    timezone_name = AIRPORT_TIMEZONES.get(iata_code.upper())
    if timezone_name:
        return pytz.timezone(timezone_name)
    return None


def convert_utc_to_local_airport(utc_datetime: datetime, airport_iata: str) -> datetime:
    """
    Convert UTC datetime to local airport timezone.
    
    Args:
        utc_datetime: Datetime in UTC
        airport_iata: IATA code for airport timezone
        
    Returns:
        Datetime converted to local airport timezone
    """
    if not utc_datetime.tzinfo:
        # If no timezone info, assume UTC
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)
    
    airport_tz = get_airport_timezone(airport_iata)
    if airport_tz:
        # Convert to airport local time
        return utc_datetime.astimezone(airport_tz)
    else:
        # Fallback: return UTC if airport not found
        return utc_datetime


def format_departure_time_local(utc_datetime: datetime, origin_iata: str) -> str:
    """
    Format departure time in local airport timezone for notifications.
    
    Args:
        utc_datetime: Departure time in UTC
        origin_iata: Origin airport IATA code
        
    Returns:
        Formatted string like "5 Jul 14:32 hs" in local time
    """
    local_time = convert_utc_to_local_airport(utc_datetime, origin_iata)
    
    # Format for Spanish notifications
    # strftime with %-d removes leading zero from day
    formatted = local_time.strftime("%-d %b %H:%M hs")
    
    # Convert month abbreviations to Spanish
    month_translations = {
        "Jan": "Ene", "Feb": "Feb", "Mar": "Mar", "Apr": "Abr",
        "May": "May", "Jun": "Jun", "Jul": "Jul", "Aug": "Ago", 
        "Sep": "Sep", "Oct": "Oct", "Nov": "Nov", "Dec": "Dic"
    }
    
    for eng, esp in month_translations.items():
        formatted = formatted.replace(eng, esp)
    
    return formatted


def is_quiet_hours_local(utc_datetime: datetime, airport_iata: str) -> bool:
    """
    Check if current time is in quiet hours (20:00-09:00) for airport timezone.
    
    Args:
        utc_datetime: Current time in UTC
        airport_iata: Airport IATA code for timezone
        
    Returns:
        True if in quiet hours, False otherwise
    """
    local_time = convert_utc_to_local_airport(utc_datetime, airport_iata)
    hour = local_time.hour
    
    # Quiet hours: 20:00 PM to 09:00 AM local time
    return hour < 9 or hour >= 20


def get_timezone_info(airport_iata: str) -> Dict[str, str]:
    """
    Get timezone information for debugging.
    
    Args:
        airport_iata: IATA airport code
        
    Returns:
        Dict with timezone information
    """
    timezone_name = AIRPORT_TIMEZONES.get(airport_iata.upper())
    if timezone_name:
        tz = pytz.timezone(timezone_name)
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)
        
        return {
            "airport": airport_iata.upper(),
            "timezone_name": timezone_name,
            "utc_offset": now_local.strftime("%z"),
            "current_local_time": now_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "is_quiet_hours": is_quiet_hours_local(now_utc, airport_iata)
        }
    else:
        return {
            "airport": airport_iata.upper(),
            "timezone_name": "NOT_FOUND",
            "error": "Airport timezone not configured"
        } 