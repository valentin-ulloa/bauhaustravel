"""Supabase database client for Bauhaus Travel."""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
import httpx
import structlog
from ..models.database import Trip, TripCreate, NotificationLog, DatabaseResult, AgencyPlace, Itinerary

logger = structlog.get_logger()


class SupabaseDBClient:
    """Async Supabase client using httpx for lightweight database operations."""
    
    def __init__(self):
        self.base_url = os.getenv("SUPABASE_URL")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not self.base_url or not self.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        
        self.rest_url = f"{self.base_url}/rest/v1"
        self.headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        # HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers=self.headers
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def get_trips_to_poll(self, now_utc: datetime) -> List[Trip]:
        """
        Query trips where next_check_at <= now_utc.
        
        Args:
            now_utc: Current UTC datetime for comparison
            
        Returns:
            List of Trip objects ready for polling
        """
        try:
            # Format datetime for Supabase query
            now_str = now_utc.isoformat()
            
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "next_check_at": f"lte.{now_str}",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            trips = [Trip(**trip_data) for trip_data in trips_data]
            
            logger.info("trips_queried", 
                count=len(trips), 
                query_time=now_str
            )
            
            return trips
            
        except Exception as e:
            logger.error("trips_query_failed", error=str(e))
            return []
    
    async def check_duplicate_trip(self, whatsapp: str, flight_number: str, departure_date: datetime) -> DatabaseResult:
        """
        Check if a trip with same whatsapp + flight_number + departure_date already exists.
        
        Args:
            whatsapp: WhatsApp number
            flight_number: Flight number
            departure_date: Departure date
            
        Returns:
            DatabaseResult with exists flag in data or error
        """
        try:
            # Format date to match database format (date only, ignore time for duplicate check)
            date_str = departure_date.strftime("%Y-%m-%d")
            
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "whatsapp": f"eq.{whatsapp}",
                    "flight_number": f"eq.{flight_number}",
                    "departure_date": f"gte.{date_str}T00:00:00",
                    "departure_date": f"lt.{date_str}T23:59:59",
                    "select": "id,flight_number"
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            
            return DatabaseResult(
                success=True,
                data={"exists": len(trips_data) > 0, "count": len(trips_data)}
            )
            
        except Exception as e:
            logger.error("duplicate_check_failed", 
                whatsapp=whatsapp,
                flight_number=flight_number,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def create_trip(self, trip_data: TripCreate) -> DatabaseResult:
        """
        Create a new trip in the database.
        
        Args:
            trip_data: TripCreate object with trip details
            
        Returns:
            DatabaseResult with created Trip object or error
        """
        try:
            # Calculate initial next_check_at (24h before departure for reminders)
            next_check_at = trip_data.departure_date - timedelta(hours=24)
            
            # Prepare data for insertion
            insert_data = {
                "client_name": trip_data.client_name,
                "whatsapp": trip_data.whatsapp,
                "flight_number": trip_data.flight_number,
                "origin_iata": trip_data.origin_iata,
                "destination_iata": trip_data.destination_iata,
                "departure_date": trip_data.departure_date.isoformat(),
                "status": trip_data.status,
                "metadata": trip_data.metadata,
                "client_description": trip_data.client_description,
                "next_check_at": next_check_at.isoformat()
            }
            
            response = await self._client.post(
                f"{self.rest_url}/trips",
                json=insert_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            if not created_data:
                raise ValueError("No data returned from trip creation")
            
            trip = Trip(**created_data[0])
            
            logger.info("trip_created", 
                trip_id=str(trip.id),
                client_name=trip.client_name,
                flight_number=trip.flight_number
            )
            
            return DatabaseResult(
                success=True,
                data=trip.model_dump(),
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("trip_creation_failed", 
                flight_number=trip_data.flight_number,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def get_trip_by_id(self, trip_id: UUID) -> DatabaseResult:
        """
        Get a single trip by its ID.
        
        Args:
            trip_id: UUID of the trip to retrieve
            
        Returns:
            DatabaseResult with Trip object or error
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "id": f"eq.{trip_id}",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            
            if not trips_data:
                logger.warning("trip_not_found", trip_id=str(trip_id))
                return DatabaseResult(
                    success=False,
                    error=f"Trip {trip_id} not found"
                )
            
            trip = Trip(**trips_data[0])
            
            logger.info("trip_retrieved", trip_id=str(trip_id))
            
            return DatabaseResult(
                success=True,
                data=trip.model_dump()
            )
            
        except Exception as e:
            logger.error("trip_retrieval_failed", 
                trip_id=str(trip_id), 
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def update_next_check_at(self, trip_id: UUID, next_check_at: datetime) -> DatabaseResult:
        """
        Update next_check_at for a specific trip.
        
        Args:
            trip_id: UUID of the trip to update
            next_check_at: Next polling datetime
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            response = await self._client.patch(
                f"{self.rest_url}/trips",
                params={"id": f"eq.{trip_id}"},
                json={"next_check_at": next_check_at.isoformat()}
            )
            response.raise_for_status()
            
            logger.info("trip_next_check_updated", 
                trip_id=str(trip_id), 
                next_check_at=next_check_at.isoformat()
            )
            
            return DatabaseResult(
                success=True,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("trip_update_failed", 
                trip_id=str(trip_id), 
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def log_notification_sent(
        self,
        trip_id: UUID,
        notification_type: str,
        sent_at: datetime,
        status: str,
        template_name: str,
        twilio_message_sid: Optional[str] = None,
        retry_count: int = 0,
        error_message: Optional[str] = None
    ) -> DatabaseResult:
        """
        Insert a notification log entry.
        
        Args:
            trip_id: UUID of the associated trip
            notification_type: Type of notification sent
            sent_at: When the notification was sent
            status: Delivery status (SENT, FAILED, PENDING)
            template_name: Twilio template used
            twilio_message_sid: Twilio's message ID (if successful)
            retry_count: Number of retry attempts
            error_message: Error details (if failed)
            
        Returns:
            DatabaseResult with operation status and created record ID
        """
        try:
            notification_data = {
                "trip_id": str(trip_id),
                "notification_type": notification_type,
                "template_name": template_name,
                "delivery_status": status,
                "sent_at": sent_at.isoformat(),
                "twilio_message_sid": twilio_message_sid,
                "retry_count": retry_count,
                "error_message": error_message
            }
            
            response = await self._client.post(
                f"{self.rest_url}/notifications_log",
                json=notification_data
            )
            # 👈 aquí es donde necesitamos ver el detalle
            if response.status_code >= 400:
                print("📄 SUPABASE ERROR:", response.status_code, response.text)
                
            response.raise_for_status()
            
            created_record = response.json()
            
            logger.info("notification_logged", 
                trip_id=str(trip_id),
                notification_type=notification_type,
                status=status,
                record_id=created_record[0]["id"] if created_record else None
            )
            
            return DatabaseResult(
                success=True,
                data=created_record[0] if created_record else None,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("notification_log_failed", 
                trip_id=str(trip_id),
                notification_type=notification_type,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def get_notification_history(self, trip_id: UUID, notification_type: Optional[str] = None) -> List[NotificationLog]:
        """
        Get notification history for a trip (useful for preventing duplicates).
        
        Args:
            trip_id: UUID of the trip
            notification_type: Optional filter by notification type
            
        Returns:
            List of NotificationLog records
        """
        try:
            params = {"trip_id": f"eq.{trip_id}", "select": "*"}
            if notification_type:
                params["notification_type"] = f"eq.{notification_type}"
            
            response = await self._client.get(
                f"{self.rest_url}/notifications_log",
                params=params
            )
            response.raise_for_status()
            
            logs_data = response.json()
            logs = [NotificationLog(**log_data) for log_data in logs_data]
            
            return logs
            
        except Exception as e:
            logger.error("notification_history_failed", 
                trip_id=str(trip_id), 
                error=str(e)
            )
            return []

    async def get_agency_places(self, agency_id: UUID, destination_city: str = None) -> List[AgencyPlace]:
        """
        Get agency places for validation.
        
        Args:
            agency_id: UUID of the agency
            destination_city: Optional filter by destination city
            
        Returns:
            List of AgencyPlace records
        """
        try:
            params = {"agency_id": f"eq.{agency_id}", "select": "*"}
            if destination_city:
                params["city"] = f"eq.{destination_city}"
            
            response = await self._client.get(
                f"{self.rest_url}/agency_places",
                params=params
            )
            response.raise_for_status()
            
            places_data = response.json()
            places = [AgencyPlace(**place_data) for place_data in places_data]
            
            logger.info("agency_places_retrieved", 
                agency_id=str(agency_id),
                city=destination_city,
                count=len(places)
            )
            
            return places
            
        except Exception as e:
            logger.error("agency_places_retrieval_failed", 
                agency_id=str(agency_id),
                error=str(e)
            )
            return []

    async def create_itinerary(self, itinerary_data: dict) -> DatabaseResult:
        """
        Create a new itinerary in the database.
        
        Args:
            itinerary_data: Dict with itinerary fields
            
        Returns:
            DatabaseResult with created Itinerary object or error
        """
        try:
            response = await self._client.post(
                f"{self.rest_url}/itineraries",
                json=itinerary_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            if not created_data:
                raise ValueError("No data returned from itinerary creation")
            
            itinerary = Itinerary(**created_data[0])
            
            logger.info("itinerary_created", 
                itinerary_id=str(itinerary.id),
                trip_id=str(itinerary.trip_id),
                version=itinerary.version
            )
            
            return DatabaseResult(
                success=True,
                data=itinerary.model_dump(),
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("itinerary_creation_failed", 
                trip_id=itinerary_data.get("trip_id"),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_latest_itinerary(self, trip_id: UUID) -> DatabaseResult:
        """
        Get the latest itinerary for a trip.
        
        Args:
            trip_id: UUID of the trip
            
        Returns:
            DatabaseResult with Itinerary object or error
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/itineraries",
                params={
                    "trip_id": f"eq.{trip_id}",
                    "order": "version.desc",
                    "limit": "1",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            itineraries_data = response.json()
            
            if not itineraries_data:
                return DatabaseResult(
                    success=False,
                    error=f"No itinerary found for trip {trip_id}"
                )
            
            itinerary = Itinerary(**itineraries_data[0])
            
            logger.info("itinerary_retrieved", 
                itinerary_id=str(itinerary.id),
                trip_id=str(trip_id),
                version=itinerary.version
            )
            
            return DatabaseResult(
                success=True,
                data=itinerary.model_dump()
            )
            
        except Exception as e:
            logger.error("itinerary_retrieval_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_agency_places(self, agency_id: UUID, destination_city: str = None) -> List[AgencyPlace]:
        """
        Get agency places for validation.
        
        Args:
            agency_id: UUID of the agency
            destination_city: Optional filter by destination city
            
        Returns:
            List of AgencyPlace records
        """
        try:
            params = {"agency_id": f"eq.{agency_id}", "select": "*"}
            if destination_city:
                params["city"] = f"eq.{destination_city}"
            
            response = await self._client.get(
                f"{self.rest_url}/agency_places",
                params=params
            )
            response.raise_for_status()
            
            places_data = response.json()
            places = [AgencyPlace(**place_data) for place_data in places_data]
            
            logger.info("agency_places_retrieved", 
                agency_id=str(agency_id),
                city=destination_city,
                count=len(places)
            )
            
            return places
            
        except Exception as e:
            logger.error("agency_places_retrieval_failed", 
                agency_id=str(agency_id),
                error=str(e)
            )
            return []

    async def create_itinerary(self, itinerary_data: dict) -> DatabaseResult:
        """
        Create a new itinerary in the database.
        
        Args:
            itinerary_data: Dict with itinerary fields
            
        Returns:
            DatabaseResult with created Itinerary object or error
        """
        try:
            response = await self._client.post(
                f"{self.rest_url}/itineraries",
                json=itinerary_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            if not created_data:
                raise ValueError("No data returned from itinerary creation")
            
            itinerary = Itinerary(**created_data[0])
            
            logger.info("itinerary_created", 
                itinerary_id=str(itinerary.id),
                trip_id=str(itinerary.trip_id),
                version=itinerary.version
            )
            
            return DatabaseResult(
                success=True,
                data=itinerary.model_dump(),
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("itinerary_creation_failed", 
                trip_id=itinerary_data.get("trip_id"),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_latest_itinerary(self, trip_id: UUID) -> DatabaseResult:
        """
        Get the latest itinerary for a trip.
        
        Args:
            trip_id: UUID of the trip
            
        Returns:
            DatabaseResult with Itinerary object or error
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/itineraries",
                params={
                    "trip_id": f"eq.{trip_id}",
                    "order": "version.desc",
                    "limit": "1",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            itineraries_data = response.json()
            
            if not itineraries_data:
                return DatabaseResult(
                    success=False,
                    error=f"No itinerary found for trip {trip_id}"
                )
            
            itinerary = Itinerary(**itineraries_data[0])
            
            logger.info("itinerary_retrieved", 
                itinerary_id=str(itinerary.id),
                trip_id=str(trip_id),
                version=itinerary.version
            )
            
            return DatabaseResult(
                success=True,
                data=itinerary.model_dump()
            )
            
        except Exception as e:
            logger.error("itinerary_retrieval_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            ) 