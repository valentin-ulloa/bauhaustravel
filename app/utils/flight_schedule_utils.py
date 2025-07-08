"""
Unified flight schedule utilities - Single source of truth for polling logic.

Eliminates duplication between NotificationsAgent and SchedulerService.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import structlog

logger = structlog.get_logger()


def calculate_unified_next_check(
    departure_time: datetime,
    now_utc: datetime,
    current_status: str = "SCHEDULED",
    estimated_arrival: Optional[datetime] = None
) -> Optional[datetime]:
    """
    UNIFIED next_check_at calculation - single source of truth.
    
    Eliminates inconsistencies between NotificationsAgent and SchedulerService.
    
    Args:
        departure_time: Flight departure time (UTC)
        now_utc: Current time (UTC)
        current_status: Current flight status
        estimated_arrival: Expected arrival time if available
        
    Returns:
        Next check time (UTC) or None if no more polling needed
    """
    time_until_departure = departure_time - now_utc
    hours_until_departure = time_until_departure.total_seconds() / 3600
    
    # Check if flight has landed (no more polling needed)
    if any(keyword in current_status.lower() for keyword in ['landed', 'arrived', 'completed']):
        logger.info("flight_landed_no_more_polling",
            departure_time=departure_time.isoformat(),
            current_status=current_status
        )
        return None
    
    # PRE-DEPARTURE PHASE
    if hours_until_departure > 24:
        next_check = now_utc + timedelta(hours=6)
    elif hours_until_departure > 4:
        next_check = now_utc + timedelta(hours=1)
    elif hours_until_departure > 0:
        next_check = now_utc + timedelta(minutes=15)
    
    # POST-DEPARTURE PHASE (in-flight or landed)
    else:
        if estimated_arrival:
            time_until_arrival = estimated_arrival - now_utc
            hours_until_arrival = time_until_arrival.total_seconds() / 3600
            
            if hours_until_arrival > 1:
                # In-flight, more than 1h to arrival
                next_check = now_utc + timedelta(minutes=30)
            elif hours_until_arrival > -0.5:  # Up to 30min past expected
                # Arrival phase - precise landing detection
                next_check = now_utc + timedelta(minutes=10)
            else:
                # More than 30min past arrival - likely landed
                next_check = now_utc + timedelta(hours=1)
        else:
            # No arrival time - generic in-flight polling
            next_check = now_utc + timedelta(minutes=30)
    
    logger.info("unified_next_check_calculated",
        departure_time=departure_time.isoformat(),
        hours_until_departure=round(hours_until_departure, 2),
        current_status=current_status,
        next_check=next_check.isoformat(),
        phase="pre_departure" if hours_until_departure > 0 else "post_departure"
    )
    
    return next_check


def get_polling_phase(departure_time: datetime, now_utc: datetime) -> str:
    """
    Get current polling phase for logging/debugging.
    
    Returns:
        Phase name: "far_future", "approaching", "imminent", "in_flight", "arrival"
    """
    hours_until_departure = (departure_time - now_utc).total_seconds() / 3600
    
    if hours_until_departure > 24:
        return "far_future"
    elif hours_until_departure > 4:
        return "approaching"
    elif hours_until_departure > 0:
        return "imminent"
    else:
        return "in_flight"


def should_suppress_notification_unified(
    notification_type: str,
    now_utc: datetime,
    airport_iata: str
) -> bool:
    """
    UNIFIED quiet hours policy - single source of truth.
    
    BUSINESS RULE:
    - Only REMINDER_24H respects quiet hours (22:00-07:00 local)
    - ALL other notifications (DELAYED, CANCELLED, GATE_CHANGE) send 24/7
    
    Args:
        notification_type: Type of notification
        now_utc: Current time (UTC)
        airport_iata: Airport code for timezone
        
    Returns:
        True if should suppress, False if should send
    """
    from .timezone_utils import is_quiet_hours_local
    
    # Only suppress REMINDER_24H during quiet hours
    if notification_type.upper() != "REMINDER_24H":
        return False
    
    # For reminders, check quiet hours in local airport time
    return is_quiet_hours_local(now_utc, airport_iata) 