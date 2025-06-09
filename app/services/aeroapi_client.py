# AeroAPI Flight Tracking Service
# Documentation: https://www.flightaware.com/commercial/aeroapi/

import os
import httpx
import structlog
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

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

class AeroAPIClient:
    """
    Client for FlightAware AeroAPI v4 - Real-time flight tracking
    
    Usage:
        client = AeroAPIClient()
        status = await client.get_flight_status("AA1234", "2025-06-15")
    """
    
    def __init__(self):
        self.api_key = os.getenv("AERO_API_KEY")
        self.base_url = "https://aeroapi.flightaware.com/aeroapi"
        
        if not self.api_key:
            logger.warning("aero_api_key_missing", 
                message="AERO_API_KEY not set - flight tracking will be disabled")
    
    async def get_flight_status(
        self, 
        flight_number: str, 
        departure_date: str
    ) -> Optional[FlightStatus]:
        """
        Get current flight status from AeroAPI
        
        Args:
            flight_number: Flight identifier (e.g., "AA1234", "LPE2464")
            departure_date: Departure date in YYYY-MM-DD format
            
        Returns:
            FlightStatus object with current status, or None if not found/error
        """
        if not self.api_key:
            logger.warning("aeroapi_unavailable", flight_number=flight_number)
            return None
            
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
                url=url
            )
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_flight_response(data, flight_number)
                    
                elif response.status_code == 404:
                    logger.info("flight_not_found", 
                        flight_number=flight_number,
                        status_code=response.status_code
                    )
                    return None
                    
                else:
                    logger.error("aeroapi_error", 
                        flight_number=flight_number,
                        status_code=response.status_code,
                        response=response.text[:200]
                    )
                    return None
                    
        except httpx.TimeoutException:
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
            status = FlightStatus(
                ident=flight.get("ident", flight_number),
                status=flight.get("status", "Unknown"),
                estimated_out=flight.get("estimated_out"),
                estimated_in=flight.get("estimated_in"),
                actual_out=flight.get("actual_out"),
                actual_in=flight.get("actual_in"),
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
            changes.append({
                "type": "status_change",
                "old_value": previous_status.status,
                "new_value": current_status.status,
                "notification_type": self._map_status_to_notification(current_status.status)
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
        
        # Departure time change (estimated_out)
        if (current_status.estimated_out and 
            current_status.estimated_out != previous_status.estimated_out):
            changes.append({
                "type": "departure_time_change",
                "old_value": previous_status.estimated_out,
                "new_value": current_status.estimated_out,
                "notification_type": "delayed"  # Usually indicates delay
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
    
    def _map_status_to_notification(self, status: str) -> str:
        """Map AeroAPI status to our notification type"""
        status_lower = status.lower()
        
        if "delay" in status_lower or "late" in status_lower:
            return "delayed"
        elif "cancel" in status_lower:
            return "cancelled"
        elif "board" in status_lower:
            return "boarding"
        elif "departed" in status_lower or "airborne" in status_lower:
            return "departed"
        elif "arrived" in status_lower or "landed" in status_lower:
            return "landed"
        else:
            return "delayed"  # Default fallback 