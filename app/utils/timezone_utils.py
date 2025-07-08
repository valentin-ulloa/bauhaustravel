"""Timezone utilities for flight notifications.

TIMEZONE POLICY (ARCHITECTURAL):
====================================
1. INPUT: All departure times are LOCAL TIME of origin airport
2. STORAGE: Convert to UTC for database storage  
3. DISPLAY: Convert back to local time for user display

This ensures consistency across all entry points and eliminates timezone confusion.
"""

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


def parse_local_time_to_utc(local_datetime: datetime, origin_iata: str) -> datetime:
    """
    ARCHITECTURAL: Convert local airport time to UTC for storage.
    
    This is the ENTRY POINT for all departure time inputs.
    Enforces the policy: INPUT = local time, STORAGE = UTC.
    
    Args:
        local_datetime: Departure time in LOCAL airport timezone (naive or UTC-marked but representing local)
        origin_iata: IATA code for origin airport
        
    Returns:
        UTC datetime for database storage
        
    Example:
        LHR local 22:05 → UTC 21:05 (during BST)
        EZE local 14:30 → UTC 17:30 (ART = UTC-3)
    """
    import structlog
    logger = structlog.get_logger()
    
    # Remove timezone info if present (treat as naive local time)
    if local_datetime.tzinfo:
        local_datetime = local_datetime.replace(tzinfo=None)
    
    airport_tz = get_airport_timezone(origin_iata)
    if not airport_tz:
        logger.warning("airport_timezone_not_found_assuming_utc", 
            origin_iata=origin_iata,
            local_time=local_datetime.isoformat()
        )
        # Fallback: treat as UTC
        return local_datetime.replace(tzinfo=timezone.utc)
    
    # Localize to airport timezone, then convert to UTC
    localized_dt = airport_tz.localize(local_datetime)
    utc_dt = localized_dt.astimezone(timezone.utc)
    
    logger.info("local_time_converted_to_utc",
        origin_iata=origin_iata,
        local_time=local_datetime.isoformat(),
        timezone=str(airport_tz),
        utc_time=utc_dt.isoformat()
    )
    
    return utc_dt


def convert_utc_to_local_airport(utc_datetime: datetime, airport_iata: str) -> datetime:
    """
    ARCHITECTURAL: Convert UTC storage time back to local airport timezone.
    
    This is the DISPLAY POINT for all departure time outputs.
    Enforces the policy: STORAGE = UTC, DISPLAY = local time.
    
    Args:
        utc_datetime: Datetime in UTC (from database)
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
    ARCHITECTURAL: Format UTC storage time as local time for notifications.
    
    Args:
        utc_datetime: Departure time in UTC (from database)
        origin_iata: Origin airport IATA code
        
    Returns:
        Formatted string like "8 Jul 22:05 hs" in local time
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


def format_departure_time_human(utc_datetime: datetime, origin_iata: str) -> str:
    """
    ARCHITECTURAL: Format UTC storage time as human-readable local time.
    
    Args:
        utc_datetime: Departure time in UTC (from database)
        origin_iata: Origin airport IATA code
        
    Returns:
        Human readable string like "Mar 8 Jul 22:05 hs (LHR)" in local time
    """
    local_time = convert_utc_to_local_airport(utc_datetime, origin_iata)
    
    # Spanish day abbreviations
    day_names = {
        0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 
        4: "Vie", 5: "Sáb", 6: "Dom"
    }
    
    # Spanish month abbreviations  
    month_names = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
    }
    
    day_abbr = day_names[local_time.weekday()]
    month_abbr = month_names[local_time.month]
    
    return f"{day_abbr} {local_time.day} {month_abbr} {local_time.strftime('%H:%M')} hs ({origin_iata})"


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


def should_suppress_notification(
    event_type: str, 
    utc_datetime: datetime, 
    airport_iata: str
) -> bool:
    """
    Determine if notification should be suppressed based on quiet hours.
    
    CRITICAL BUSINESS RULE:
    - Only REMINDER_24H respects quiet hours (22:00-07:00)
    - All other events (DELAYED, CANCELLED, BOARDING, GATE_CHANGE) send 24/7
    
    Args:
        event_type: Notification type (REMINDER_24H, DELAYED, etc.)
        utc_datetime: Current time in UTC
        airport_iata: Airport IATA code for timezone
        
    Returns:
        True if should suppress, False if should send
    """
    # Only suppress REMINDER_24H during quiet hours
    if event_type != "REMINDER_24H":
        return False
    
    # For reminders, check quiet hours in local airport time
    return is_quiet_hours_local(utc_datetime, airport_iata)


def round_eta_to_5min(dt: datetime) -> str:
    """
    Round datetime to nearest 5 minutes for deduplication.
    
    Args:
        dt: Datetime to round
        
    Returns:
        Rounded datetime as ISO string or "TBD" if None
    """
    if not dt:
        return "TBD"
    
    # Round to nearest 5 minutes
    minutes = dt.minute
    rounded_minutes = round(minutes / 5) * 5
    
    if rounded_minutes == 60:
        rounded_dt = dt.replace(hour=dt.hour + 1, minute=0, second=0, microsecond=0)
    else:
        rounded_dt = dt.replace(minute=rounded_minutes, second=0, microsecond=0)
    
    return rounded_dt.isoformat()


def pluralize(count: int, singular: str, plural: str) -> str:
    """
    Return properly pluralized string in Spanish.
    
    Args:
        count: Number to check
        singular: Singular form (e.g., "actividad")
        plural: Plural form (e.g., "actividades")
        
    Returns:
        Properly pluralized string
    """
    return singular if count == 1 else plural


async def get_city_name_from_iata(iata_code: str) -> str:
    """
    Get city name from IATA code using OpenAI as fallback.
    
    Args:
        iata_code: 3-letter IATA airport code
        
    Returns:
        Human-readable city name in Spanish
    """
    # First try our static mapping
    city_names = {
        # Colombia
        "MDE": "Medellín", "BOG": "Bogotá", "CTG": "Cartagena", 
        "CLO": "Cali", "BAQ": "Barranquilla", "BGA": "Bucaramanga",
        
        # Argentina  
        "EZE": "Buenos Aires", "AEP": "Buenos Aires", "COR": "Córdoba",
        "MDZ": "Mendoza", "ROS": "Rosario", "IGR": "Iguazú",
        
        # Brazil
        "GRU": "São Paulo", "GIG": "Río de Janeiro", "BSB": "Brasília",
        
        # USA
        "JFK": "Nueva York", "LAX": "Los Ángeles", "MIA": "Miami",
        "ORD": "Chicago", "DFW": "Dallas",
        
        # Europe
        "MAD": "Madrid", "BCN": "Barcelona", "LHR": "Londres",
        "CDG": "París", "FCO": "Roma",
        
        # Other
        "LIM": "Lima", "SCL": "Santiago", "PTY": "Ciudad de Panamá",
        "MEX": "Ciudad de México", "CUN": "Cancún"
    }
    
    if iata_code.upper() in city_names:
        return city_names[iata_code.upper()]
    
    # Fallback: Use OpenAI to get city name
    try:
        import openai
        import os
        
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": "Eres un asistente que convierte códigos IATA de aeropuertos a nombres de ciudades en español. Responde SOLO con el nombre de la ciudad, sin explicaciones."
                },
                {
                    "role": "user",
                    "content": f"¿Cuál es el nombre de la ciudad para el aeropuerto con código IATA '{iata_code}'?"
                }
            ],
            max_tokens=20,
            temperature=0
        )
        
        city_name = response.choices[0].message.content.strip()
        
        # Log the result for future static mapping updates
        import structlog
        logger = structlog.get_logger()
        logger.info("openai_city_lookup", 
            iata_code=iata_code,
            city_name=city_name
        )
        
        return city_name
        
    except Exception as e:
        # Fallback to IATA code if OpenAI fails
        import structlog
        logger = structlog.get_logger()
        logger.warning("city_name_lookup_failed", 
            iata_code=iata_code,
            error=str(e)
        )
        return iata_code 