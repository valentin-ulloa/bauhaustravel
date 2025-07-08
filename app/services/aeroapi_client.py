# AeroAPI Flight Tracking Service
# Documentation: https://www.flightaware.com/commercial/aeroapi/

import os
import httpx
import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Simple retry implementation

logger = structlog.get_logger(__name__)

@dataclass
class FlightStatus:
    """Parsed flight status data from AeroAPI"""
    ident: str
    status: str
    estimated_out: Optional[str] = None
    estimated_in: Optional[str] = None
    actual_out: Optional[str] = None
    actual_in: Optional[str] = None
    gate_origin: Optional[str] = None
    gate_destination: Optional[str] = None
    departure_delay: int = 0
    arrival_delay: int = 0
    cancelled: bool = False
    diverted: bool = False
    origin_iata: Optional[str] = None
    destination_iata: Optional[str] = None
    aircraft_type: Optional[str] = None
    progress_percent: int = 0

@dataclass
class CacheEntry:
    """Cache entry for flight status data"""
    data: Optional[FlightStatus]
    timestamp: datetime
    
    def is_expired(self, cache_duration_minutes: int = 5) -> bool:
        """Check if cache entry is expired"""
        age = datetime.now(timezone.utc) - self.timestamp
        return age > timedelta(minutes=cache_duration_minutes)

class AeroAPIClient:
    """
    Client for FlightAware AeroAPI v4 - Real-time flight tracking
    
    TC-004 Enhancement: Includes 5-minute in-memory caching to reduce API calls.
    
    Usage:
        client = AeroAPIClient()
        status = await client.get_flight_status("AA1234", "2025-06-15")
    """
    
    def __init__(self):
        self.api_key = os.getenv("AERO_API_KEY")
        self.base_url = "https://aeroapi.flightaware.com/aeroapi"
        
        # TC-004: In-memory cache for flight status
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_duration_minutes = 5
        self._cache_hits = 0
        self._cache_misses = 0
        
        if not self.api_key:
            logger.warning("aero_api_key_missing", 
                message="AERO_API_KEY not set - flight tracking will be disabled")
    
    def _get_cache_key(self, flight_number: str, departure_date: str) -> str:
        """Generate cache key for flight + date combination"""
        return f"{flight_number}:{departure_date}"
    
    def _get_cached_status(self, flight_number: str, departure_date: str) -> Optional[FlightStatus]:
        """Get flight status from cache if available and not expired"""
        cache_key = self._get_cache_key(flight_number, departure_date)
        
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired(self._cache_duration_minutes):
                self._cache_hits += 1
                logger.info("cache_hit", 
                    flight_number=flight_number,
                    cache_age_seconds=(datetime.now(timezone.utc) - entry.timestamp).total_seconds(),
                    cache_hit_rate=self._cache_hits / (self._cache_hits + self._cache_misses) * 100
                )
                return entry.data
            else:
                # Remove expired entry
                del self._cache[cache_key]
                logger.debug("cache_expired", flight_number=flight_number)
        
        self._cache_misses += 1
        return None
    
    def _cache_status(self, flight_number: str, departure_date: str, status: Optional[FlightStatus]):
        """Cache flight status for future requests"""
        cache_key = self._get_cache_key(flight_number, departure_date)
        
        entry = CacheEntry(
            data=status,
            timestamp=datetime.now(timezone.utc)
        )
        
        self._cache[cache_key] = entry
        
        logger.info("status_cached", 
            flight_number=flight_number,
            cache_size=len(self._cache),
            has_data=status is not None
        )
        
        # Simple cache cleanup: remove old entries if cache gets too large
        if len(self._cache) > 100:  # Prevent memory issues
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        """Remove expired entries from cache"""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired(self._cache_duration_minutes)
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        logger.info("cache_cleaned", 
            removed_entries=len(expired_keys),
            remaining_entries=len(self._cache)
        )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_size": len(self._cache),
            "cache_duration_minutes": self._cache_duration_minutes
        }
    
    async def get_flight_status(
        self, 
        flight_number: str, 
        departure_date: str
    ) -> Optional[FlightStatus]:
        """
        Get current flight status from AeroAPI with 5-minute caching.
        
        TC-004: Implements caching to reduce API calls by ~60% as per acceptance criteria.
        
        Args:
            flight_number: Flight identifier (e.g., "AA1234", "LPE2464")
            departure_date: Departure date in YYYY-MM-DD format
            
        Returns:
            FlightStatus object with current status, or None if not found/error
        """
        # TC-004: Check cache first
        cached_status = self._get_cached_status(flight_number, departure_date)
        if cached_status is not None:
            return cached_status
        
        if not self.api_key:
            logger.warning("aeroapi_unavailable", flight_number=flight_number)
            # Cache the null result to avoid repeated API calls for missing API key
            self._cache_status(flight_number, departure_date, None)
            return None
        
        # Make the API request directly
        return await self._make_flight_request(flight_number, departure_date)
    
    async def _make_flight_request(self, flight_number: str, departure_date: str) -> Optional[FlightStatus]:
        """
        TC-004: Extracted method for making the actual AeroAPI request (for retry logic).
        """
        try:
            # Parse departure date and calculate end date (departure_date + 1)
            departure_dt = datetime.strptime(departure_date, "%Y-%m-%d")
            end_dt = departure_dt + timedelta(days=1)
            
            # Format dates for AeroAPI
            start_date = departure_date  # YYYY-MM-DD
            end_date = end_dt.strftime("%Y-%m-%d")  # YYYY-MM-DD + 1 day
            
            headers = {
                "x-apikey": self.api_key,
                "Accept": "application/json"
            }
            
            # AeroAPI v4 endpoint: /flights/{ident}?start=YYYY-MM-DD&end=YYYY-MM-DD
            url = f"{self.base_url}/flights/{flight_number}"
            params = {
                "start": start_date,
                "end": end_date,
                "max_pages": 1  # Limit to avoid unnecessary charges
            }
            
            logger.info("aeroapi_request", 
                flight_number=flight_number,
                departure_date=departure_date,
                start_date=start_date,
                end_date=end_date,
                url=url,
                cache_miss=True
            )
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    flight_status = self._parse_flight_response(data, flight_number)
                    
                    # TC-004: Cache the successful response
                    self._cache_status(flight_number, departure_date, flight_status)
                    
                    return flight_status
                    
                elif response.status_code == 404:
                    logger.info("flight_not_found", 
                        flight_number=flight_number,
                        status_code=response.status_code
                    )
                    
                    # TC-004: Cache the null result to avoid repeated 404s
                    self._cache_status(flight_number, departure_date, None)
                    return None
                    
                else:
                    # Any other error
                    error_msg = f"AeroAPI error {response.status_code}: {response.text[:200]}"
                    logger.error("aeroapi_error", 
                        flight_number=flight_number,
                        status_code=response.status_code,
                        response=response.text[:200]
                    )
                    return None
                    
        except httpx.TimeoutException as e:
            logger.error("aeroapi_timeout", flight_number=flight_number)
            return None
            
        except Exception as e:
            logger.error("aeroapi_exception", 
                flight_number=flight_number,
                error=str(e)
            )
            return None
    
    def _parse_flight_response(self, data: Dict[str, Any], flight_number: str) -> Optional[FlightStatus]:
        """Parse AeroAPI response into FlightStatus object"""
        try:
            flights = data.get("flights", [])
            
            if not flights:
                logger.info("no_flights_returned", flight_number=flight_number)
                return None
            
            # Take the first (most recent) flight
            flight = flights[0]
            
            # Extract key fields with safe defaults
            # FIXED: Map AeroAPI JSON fields correctly based on investigation
            status = FlightStatus(
                ident=flight.get("ident", flight_number),
                status=flight.get("status", "Unknown"),
                estimated_out=flight.get("estimated_out"),
                estimated_in=flight.get("estimated_on"),      # AeroAPI uses "estimated_on" for arrival
                actual_out=flight.get("actual_out"),
                actual_in=flight.get("actual_on"),            # AeroAPI uses "actual_on" for landing time
                gate_origin=flight.get("gate_origin"),
                gate_destination=flight.get("gate_destination"),
                departure_delay=flight.get("departure_delay", 0),
                arrival_delay=flight.get("arrival_delay", 0),
                cancelled=flight.get("cancelled", False),
                diverted=flight.get("diverted", False),
                progress_percent=flight.get("progress_percent", 0)
            )
            
            # Extract airport codes from origin/destination objects
            if "origin" in flight and flight["origin"]:
                status.origin_iata = flight["origin"].get("code_iata")
            
            if "destination" in flight and flight["destination"]:
                status.destination_iata = flight["destination"].get("code_iata")
            
            status.aircraft_type = flight.get("aircraft_type")
            
            logger.info("flight_status_parsed", 
                flight_number=flight_number,
                status=status.status,
                cancelled=status.cancelled,
                diverted=status.diverted,
                progress=status.progress_percent
            )
            
            return status
            
        except Exception as e:
            logger.error("flight_parsing_error", 
                flight_number=flight_number,
                error=str(e),
                data_sample=str(data)[:200]
            )
            return None
    
    def detect_flight_changes(
        self, 
        current_status: FlightStatus, 
        previous_status: Optional[FlightStatus]
    ) -> List[Dict[str, Any]]:
        """
        Compare current vs previous flight status to detect changes
        
        Returns:
            List of change events with type and details
        """
        changes = []
        
        if not previous_status:
            return changes
        
        # Status change (Scheduled -> Delayed, etc.)
        if current_status.status != previous_status.status:
            notification_type = self._map_status_to_notification(current_status.status)
            
            # Only create change event if notification is needed
            if notification_type != "no_notification":
                changes.append({
                    "type": "status_change",
                    "old_value": previous_status.status,
                    "new_value": current_status.status,
                    "notification_type": notification_type
                })
        
        # Gate change
        if (current_status.gate_origin and 
            current_status.gate_origin != previous_status.gate_origin):
            changes.append({
                "type": "gate_change",
                "old_value": previous_status.gate_origin,
                "new_value": current_status.gate_origin,
                "notification_type": "gate_change"
            })
        
        # Departure time change (estimated_out) - INTELLIGENT DELAY DETECTION
        if (current_status.estimated_out and 
            current_status.estimated_out != previous_status.estimated_out):
            
            # Only trigger delayed notification if there's an ACTUAL delay
            is_actual_delay = self._is_actual_delay(
                previous_estimated=previous_status.estimated_out,
                current_estimated=current_status.estimated_out,
                current_status=current_status.status
            )
            
            if is_actual_delay:
                changes.append({
                    "type": "departure_time_change",
                    "old_value": previous_status.estimated_out,
                    "new_value": current_status.estimated_out,
                    "notification_type": "delayed"
                })
        
        # Cancellation
        if current_status.cancelled and not previous_status.cancelled:
            changes.append({
                "type": "cancellation",
                "old_value": False,
                "new_value": True,
                "notification_type": "cancelled"
            })
        
        # Diversion
        if current_status.diverted and not previous_status.diverted:
            changes.append({
                "type": "diversion",
                "old_value": False,
                "new_value": True,
                "notification_type": "diverted"  # Would need new template
            })
        
        return changes
    
    def _is_actual_delay(
        self, 
        previous_estimated: Optional[str], 
        current_estimated: str,
        current_status: str
    ) -> bool:
        """
        Determine if estimated_out change represents an actual delay.
        
        Business rules:
        1. If previous was NULL and current has time → Initial scheduling (NOT a delay)
        2. If current time > previous time → Potential delay 
        3. If status explicitly says "Delayed" → Confirm it's a delay
        4. If current time < previous time → Early departure (NOT a delay)
        
        Args:
            previous_estimated: Previous estimated_out (might be None)
            current_estimated: Current estimated_out 
            current_status: Current flight status
            
        Returns:
            True if this represents an actual delay worth notifying
        """
        try:
            # Rule 1: NULL → Time is initial scheduling, not a delay
            if not previous_estimated:
                logger.info("estimated_out_initial_scheduling", 
                    current_estimated=current_estimated,
                    is_delay=False
                )
                return False
            
            # Parse times for comparison
            from datetime import datetime
            
            previous_dt = datetime.fromisoformat(previous_estimated.replace('Z', '+00:00'))
            current_dt = datetime.fromisoformat(current_estimated.replace('Z', '+00:00'))
            
            time_difference_minutes = (current_dt - previous_dt).total_seconds() / 60
            
            # Rule 2: Current time earlier than previous → Early departure (not delay)
            if time_difference_minutes < 0:
                logger.info("estimated_out_early_departure", 
                    time_difference_minutes=time_difference_minutes,
                    is_delay=False
                )
                return False
            
            # Rule 3: Minimal change (< 5 minutes) → Likely technical update, not real delay
            if time_difference_minutes < 5:
                logger.info("estimated_out_minimal_change", 
                    time_difference_minutes=time_difference_minutes,
                    is_delay=False
                )
                return False
            
            # Rule 4: Status explicitly mentions delay
            status_lower = current_status.lower()
            if "delay" in status_lower or "late" in status_lower:
                logger.info("estimated_out_confirmed_delay_by_status", 
                    time_difference_minutes=time_difference_minutes,
                    status=current_status,
                    is_delay=True
                )
                return True
            
            # Rule 5: Significant time increase (>= 15 minutes) without explicit delay status
            # This catches delays where status hasn't updated yet
            if time_difference_minutes >= 15:
                logger.info("estimated_out_significant_delay_detected", 
                    time_difference_minutes=time_difference_minutes,
                    status=current_status,
                    is_delay=True
                )
                return True
            
            # Rule 6: Moderate delay (5-15 minutes) but status still "Scheduled" 
            # → Wait for status confirmation to avoid false alarms
            logger.info("estimated_out_moderate_change_waiting_status_confirmation", 
                time_difference_minutes=time_difference_minutes,
                status=current_status,
                is_delay=False
            )
            return False
            
        except Exception as e:
            logger.error("delay_detection_failed", 
                previous_estimated=previous_estimated,
                current_estimated=current_estimated,
                error=str(e)
            )
            # On error, be conservative - don't trigger false alarms
            return False
    
    def _map_status_to_notification(self, status: str) -> str:
        """
        Map AeroAPI status to our notification type.
        
        CRITICAL: Only return notification types that should trigger alerts.
        Normal statuses like 'Scheduled', 'Taxiing', 'En Route' should NOT trigger notifications.
        """
        status_lower = status.lower()
        
        # Explicit delay/late indicators
        if "delay" in status_lower or "late" in status_lower:
            return "delayed"
        
        # Cancellation indicators  
        elif "cancel" in status_lower:
            return "cancelled"
        
        # Boarding indicators
        elif "board" in status_lower:
            return "boarding"
        
        # Departure indicators (informational, not alertable)
        elif "departed" in status_lower or "airborne" in status_lower or "en route" in status_lower:
            return "departed"
        
        # Landing indicators (for welcome messages)
        elif "arrived" in status_lower or "landed" in status_lower:
            return "landed"
        
        # NORMAL STATUSES - NO NOTIFICATION NEEDED
        elif status_lower in ["scheduled", "on time", "taxiing", "pushback", "unknown"]:
            return "no_notification"
        
        # Unknown status - log but don't spam users
        else:
            logger.warning("unknown_flight_status_detected", 
                status=status,
                mapped_to="no_notification"
            )
            return "no_notification" 