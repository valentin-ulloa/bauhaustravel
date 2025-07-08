"""Supabase database client for Bauhaus Travel."""

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID
import httpx
import structlog
from ..models.database import Trip, TripCreate, NotificationLog, DatabaseResult, AgencyPlace, Itinerary, TripContext
import asyncio

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
        Query trips where next_check_at <= now_utc AND status != 'LANDED'.
        
        FIXED: Poll trips in all phases (pre-departure, in-flight, landing) until status = LANDED.
        
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
                    "next_check_at": f"lte.{now_str}",      # Due for checking
                    "status": f"neq.LANDED",                # FIXED: Exclude only LANDED flights
                    "select": "*",
                    "order": "next_check_at.asc"            # Process oldest first
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            trips = [Trip(**trip_data) for trip_data in trips_data]
            
            logger.info("trips_queried", 
                count=len(trips), 
                query_time=now_str,
                criteria="next_check_at <= now AND status != LANDED"
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
                "agency_id": str(trip_data.agency_id) if trip_data.agency_id else None,
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
        Update the next_check_at time for a trip.
        
        Args:
            trip_id: UUID of the trip to update
            next_check_at: Next check datetime in UTC
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            update_data = {
                "next_check_at": next_check_at.isoformat()
            }
            
            response = await self._client.patch(
                f"{self.rest_url}/trips",
                json=update_data,
                params={"id": f"eq.{trip_id}"}
            )
            response.raise_for_status()
            
            logger.info("trip_next_check_updated", 
                trip_id=str(trip_id),
                next_check_at=next_check_at.isoformat()
            )
            
            return DatabaseResult(success=True, affected_rows=1)
            
        except Exception as e:
            logger.error("trip_next_check_update_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def update_trip_status(self, trip_id: UUID, update_data: Dict[str, Any]) -> DatabaseResult:
        """
        Update trip fields like status, gate, etc.
        
        Args:
            trip_id: UUID of the trip to update
            update_data: Dict with fields to update (status, gate, etc.)
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            response = await self._client.patch(
                f"{self.rest_url}/trips",
                json=update_data,
                params={"id": f"eq.{trip_id}"}
            )
            response.raise_for_status()
            
            updated_trips = response.json()
            
            logger.info("trip_status_updated", 
                trip_id=str(trip_id),
                update_data=update_data,
                affected_rows=len(updated_trips)
            )
            
            return DatabaseResult(
                success=True, 
                data=updated_trips[0] if updated_trips else None,
                affected_rows=len(updated_trips)
            )
            
        except Exception as e:
            logger.error("trip_status_update_failed", 
                trip_id=str(trip_id),
                update_data=update_data,
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def log_notification_sent(
        self,
        trip_id: UUID,
        notification_type: str,
        sent_at: datetime,
        status: str,
        template_name: str,
        twilio_message_sid: Optional[str] = None,
        retry_count: int = 0,
        error_message: Optional[str] = None,
        idempotency_hash: Optional[str] = None,
        eta_round: Optional[str] = None
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
                "error_message": error_message,
                "idempotency_hash": idempotency_hash,
                "eta_round": eta_round
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

    # TC-003: User identification and conversation methods
    
    async def get_latest_trip_by_whatsapp(self, whatsapp: str, within_days: int = 90) -> Optional[Trip]:
        """
        Get the most recent trip for a WhatsApp number (for user identification).
        
        Args:
            whatsapp: WhatsApp phone number
            within_days: Only consider trips within this many days
            
        Returns:
            Trip object if found, None otherwise
        """
        try:
            # Calculate cutoff date
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=within_days)
            
            params = {
                "whatsapp": f"eq.{whatsapp}",
                "departure_date": f"gte.{cutoff_date.isoformat()}",
                "select": "*",
                "order": "departure_date.desc",
                "limit": "1"
            }
            
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params=params
            )
            response.raise_for_status()
            
            trips_data = response.json()
            
            if trips_data:
                trip = Trip(**trips_data[0])
                logger.info("trip_identified_by_whatsapp", 
                    whatsapp=whatsapp,
                    trip_id=str(trip.id),
                    flight_number=trip.flight_number
                )
                return trip
            else:
                logger.info("no_recent_trip_found", 
                    whatsapp=whatsapp,
                    within_days=within_days
                )
                return None
            
        except Exception as e:
            logger.error("trip_identification_failed", 
                whatsapp=whatsapp,
                error=str(e)
            )
            return None

    async def create_conversation(self, trip_id: UUID, sender: str, message: str, intent: Optional[str] = None) -> DatabaseResult:
        """
        Log a conversation message.
        
        Args:
            trip_id: UUID of the trip
            sender: 'user' or 'bot'
            message: Message content
            intent: Optional detected intent
            
        Returns:
            DatabaseResult with created conversation record
        """
        try:
            conversation_data = {
                "trip_id": str(trip_id),
                "sender": sender,
                "message": message,
                "intent": intent,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = await self._client.post(
                f"{self.rest_url}/conversations",
                json=conversation_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            logger.info("conversation_logged", 
                trip_id=str(trip_id),
                sender=sender,
                intent=intent,
                message_length=len(message)
            )
            
            return DatabaseResult(
                success=True,
                data=created_data[0] if created_data else None,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("conversation_logging_failed", 
                trip_id=str(trip_id),
                sender=sender,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_recent_conversations(self, trip_id: UUID, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent conversation history for context.
        
        Args:
            trip_id: UUID of the trip
            limit: Number of recent messages to retrieve
            
        Returns:
            List of conversation records
        """
        try:
            params = {
                "trip_id": f"eq.{trip_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": str(limit)
            }
            
            response = await self._client.get(
                f"{self.rest_url}/conversations",
                params=params
            )
            response.raise_for_status()
            
            conversations_data = response.json()
            
            # Reverse to get chronological order (oldest first)
            conversations_data.reverse()
            
            logger.info("conversations_retrieved", 
                trip_id=str(trip_id),
                count=len(conversations_data)
            )
            
            return conversations_data
            
        except Exception as e:
            logger.error("conversations_retrieval_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return []

    async def create_document(self, document_data: dict) -> DatabaseResult:
        """
        Store a new document record.
        
        Args:
            document_data: Dict with document fields including audit info
            
        Returns:
            DatabaseResult with created document record
        """
        try:
            response = await self._client.post(
                f"{self.rest_url}/documents",
                json=document_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            logger.info("document_created", 
                trip_id=document_data.get("trip_id"),
                document_type=document_data.get("type"),
                uploaded_by=document_data.get("uploaded_by"),
                uploaded_by_type=document_data.get("uploaded_by_type")
            )
            
            return DatabaseResult(
                success=True,
                data=created_data[0] if created_data else None,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("document_creation_failed", 
                trip_id=document_data.get("trip_id"),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_documents_by_trip(self, trip_id: UUID, document_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get documents for a trip.
        
        Args:
            trip_id: UUID of the trip
            document_type: Optional filter by document type
            
        Returns:
            List of document records
        """
        try:
            params = {
                "trip_id": f"eq.{trip_id}",
                "select": "*",
                "order": "uploaded_at.desc"
            }
            
            if document_type:
                params["type"] = f"eq.{document_type}"
            
            response = await self._client.get(
                f"{self.rest_url}/documents",
                params=params
            )
            response.raise_for_status()
            
            documents_data = response.json()
            
            logger.info("documents_retrieved", 
                trip_id=str(trip_id),
                document_type=document_type,
                count=len(documents_data)
            )
            
            return documents_data
            
        except Exception as e:
            logger.error("documents_retrieval_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return []

    async def get_complete_trip_context(self, trip_id: UUID) -> TripContext:
        """
        Carga todo el contexto relevante de un viaje en paralelo y lo valida con TripContext.
        Retorna: TripContext
        """
        trip_task = self.get_trip_by_id(trip_id)
        itinerary_task = self.get_latest_itinerary(trip_id)
        documents_task = self.get_documents_by_trip(trip_id)
        messages_task = self.get_recent_conversations(trip_id, limit=10)

        trip_result, itinerary_result, documents, messages = await asyncio.gather(
            trip_task, itinerary_task, documents_task, messages_task
        )

        trip = trip_result.data if trip_result and trip_result.success else None
        itinerary = itinerary_result.data.get("parsed_itinerary") if itinerary_result and itinerary_result.success and itinerary_result.data else None
        documents = documents if documents else []
        messages = messages if messages else []

        context = TripContext(
            trip=trip or {},
            itinerary=itinerary,
            documents=documents,
            recent_messages=messages
        )
        return context

    async def get_complete_trip_context_optimized(self, trip_id: UUID) -> TripContext:
        """
        TC-004 OPTIMIZED: Carga contexto completo con una sola query SQL usando JOINs.
        
        Ventajas vs método anterior:
        - 1 query vs 4 queries paralelas
        - Reduce latencia de red
        - Menos overhead de HTTP requests
        - Atomic data consistency
        
        Args:
            trip_id: UUID del trip
            
        Returns:
            TripContext completo
        """
        try:
            # Single query with JOINs to get all related data
            # Note: Supabase PostgREST supports embedding related tables
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "id": f"eq.{trip_id}",
                    "select": """
                        *,
                        itineraries:itineraries(
                            id, version, status, generated_at, parsed_itinerary,
                            order: version.desc,
                            limit: 1
                        ),
                        documents:documents(*),
                        conversations:conversations(
                            id, sender, message, intent, created_at,
                            order: created_at.desc,
                            limit: 10
                        )
                    """
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            
            if not trips_data:
                logger.warning("trip_not_found_optimized", trip_id=str(trip_id))
                return TripContext(trip={}, itinerary=None, documents=[], recent_messages=[])
            
            trip_raw = trips_data[0]
            
            # Extract and process embedded data
            trip = {k: v for k, v in trip_raw.items() if k not in ['itineraries', 'documents', 'conversations']}
            
            # Normalize datetime fields to match original method format
            from datetime import datetime
            datetime_fields = ['departure_date', 'inserted_at', 'next_check_at']
            for field in datetime_fields:
                if field in trip and trip[field] and isinstance(trip[field], str):
                    try:
                        # Parse and convert to Python datetime object
                        dt = datetime.fromisoformat(trip[field].replace('Z', '+00:00'))
                        trip[field] = dt
                    except:
                        pass  # Keep original value if parsing fails
            
            # Get latest itinerary
            itinerary = None
            if trip_raw.get("itineraries") and len(trip_raw["itineraries"]) > 0:
                latest_itinerary = trip_raw["itineraries"][0]
                itinerary = latest_itinerary.get("parsed_itinerary")
            
            # Get documents (already sorted)
            documents = trip_raw.get("documents", [])
            
            # Get recent conversations (reverse to chronological order)
            messages = trip_raw.get("conversations", [])
            messages.reverse()  # PostgREST returns desc, we want asc for context
            
            logger.info("trip_context_loaded_optimized", 
                trip_id=str(trip_id),
                has_itinerary=itinerary is not None,
                documents_count=len(documents),
                messages_count=len(messages)
            )
            
            context = TripContext(
                trip=trip,
                itinerary=itinerary,
                documents=documents,
                recent_messages=messages
            )
            return context
            
        except Exception as e:
            logger.error("trip_context_load_failed_optimized", 
                trip_id=str(trip_id),
                error=str(e)
            )
            # Fallback to original method on error
            logger.info("falling_back_to_original_method", trip_id=str(trip_id))
            return await self.get_complete_trip_context(trip_id)

    # ========================
    # AGENCY METHODS (TC-005)
    # ========================

    async def create_agency(self, agency_data: dict) -> DatabaseResult:
        """
        Create a new agency in the database.
        
        Args:
            agency_data: Dictionary with agency details
            
        Returns:
            DatabaseResult with created agency data or error
        """
        try:
            response = await self._client.post(
                f"{self.rest_url}/agencies",
                json=agency_data
            )
            response.raise_for_status()
            
            created_data = response.json()
            
            logger.info("agency_created", 
                agency_id=created_data[0]["id"] if created_data else None,
                name=agency_data.get("name"),
                email=agency_data.get("email")
            )
            
            return DatabaseResult(
                success=True,
                data=created_data[0] if created_data else None,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("agency_creation_failed", 
                name=agency_data.get("name"),
                email=agency_data.get("email"),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_agency_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get agency by email address.
        
        Args:
            email: Agency email address
            
        Returns:
            Agency data or None if not found
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/agencies",
                params={
                    "email": f"eq.{email}",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            agencies = response.json()
            
            return agencies[0] if agencies else None
            
        except Exception as e:
            logger.error("agency_email_lookup_failed", 
                email=email,
                error=str(e)
            )
            return None

    async def get_agency_by_id(self, agency_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get agency by ID.
        
        Args:
            agency_id: Agency UUID
            
        Returns:
            Agency data or None if not found
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/agencies",
                params={
                    "id": f"eq.{agency_id}",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            agencies = response.json()
            
            return agencies[0] if agencies else None
            
        except Exception as e:
            logger.error("agency_id_lookup_failed", 
                agency_id=str(agency_id),
                error=str(e)
            )
            return None

    async def get_agency_stats(self, agency_id: UUID) -> DatabaseResult:
        """
        Get comprehensive stats for an agency.
        
        Args:
            agency_id: Agency UUID
            
        Returns:
            DatabaseResult with stats data
        """
        try:
            from datetime import datetime, timezone, timedelta
            
            # Get current month start
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Get all trips for this agency
            trips_response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "agency_id": f"eq.{agency_id}",
                    "select": "*"
                }
            )
            trips_response.raise_for_status()
            trips = trips_response.json()
            
            # Get conversations for this agency
            conversations_response = await self._client.get(
                f"{self.rest_url}/conversations",
                params={
                    "agency_id": f"eq.{agency_id}",
                    "select": "id"
                }
            )
            conversations_response.raise_for_status()
            conversations = conversations_response.json()
            
            # Calculate stats
            total_trips = len(trips)
            active_trips = len([t for t in trips if datetime.fromisoformat(t["departure_date"].replace("Z", "+00:00")) > now])
            total_conversations = len(conversations)
            
            # Calculate revenue (placeholder - would need actual pricing logic)
            revenue_current_month = total_trips * 50.0  # Placeholder calculation
            revenue_total = total_trips * 50.0
            
            # Top destinations
            destinations = [t.get("destination_iata", "Unknown") for t in trips]
            from collections import Counter
            destination_counts = Counter(destinations)
            top_destinations = [dest for dest, count in destination_counts.most_common(4)]
            
            stats = {
                "total_trips": total_trips,
                "active_trips": active_trips,
                "total_conversations": total_conversations,
                "satisfaction_rate": 0.94,  # Placeholder - would need real satisfaction tracking
                "revenue_current_month": revenue_current_month,
                "revenue_total": revenue_total,
                "top_destinations": top_destinations,
                "avg_response_time": 1.8  # Placeholder - would need real response time tracking
            }
            
            logger.info("agency_stats_calculated",
                agency_id=str(agency_id),
                total_trips=total_trips,
                active_trips=active_trips
            )
            
            return DatabaseResult(
                success=True,
                data=stats
            )
            
        except Exception as e:
            logger.error("agency_stats_failed",
                agency_id=str(agency_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def get_trips_by_agency(self, agency_id: UUID, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get trips for a specific agency.
        
        Args:
            agency_id: Agency UUID
            limit: Maximum number of trips to return
            
        Returns:
            List of trip records
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "agency_id": f"eq.{agency_id}",
                    "select": "*",
                    "order": "inserted_at.desc",
                    "limit": str(limit)
                }
            )
            response.raise_for_status()
            
            trips = response.json()
            
            logger.info("agency_trips_retrieved",
                agency_id=str(agency_id),
                count=len(trips)
            )
            
            return trips
            
        except Exception as e:
            logger.error("agency_trips_retrieval_failed",
                agency_id=str(agency_id),
                error=str(e)
            )
            return []

    async def update_agency_branding(self, agency_id: UUID, branding: Dict[str, Any]) -> DatabaseResult:
        """
        Update agency branding configuration.
        
        Args:
            agency_id: UUID of the agency
            branding: Dict with branding configuration
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            update_data = {"branding": branding}
            
            response = await self._client.patch(
                f"{self.rest_url}/agencies",
                params={"id": f"eq.{agency_id}"},
                json=update_data
            )
            response.raise_for_status()
            
            logger.info("agency_branding_updated", 
                agency_id=str(agency_id),
                branding_keys=list(branding.keys())
            )
            
            return DatabaseResult(
                success=True,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("agency_branding_update_failed", 
                agency_id=str(agency_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    # Flight Status History Methods
    
    async def save_flight_status(
        self,
        trip_id: UUID,
        flight_number: str,
        flight_date: str,
        status: str,
        gate_origin: Optional[str] = None,
        gate_destination: Optional[str] = None,
        terminal_origin: Optional[str] = None,
        terminal_destination: Optional[str] = None,
        estimated_out: Optional[str] = None,
        actual_out: Optional[str] = None,
        estimated_in: Optional[str] = None,
        actual_in: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        source: str = "aeroapi"
    ) -> DatabaseResult:
        """
        Save flight status to history table.
        
        Args:
            trip_id: UUID of the trip
            flight_number: Flight number
            flight_date: Flight date (YYYY-MM-DD)
            status: Flight status
            gate_origin: Origin gate
            gate_destination: Destination gate
            terminal_origin: Origin terminal
            terminal_destination: Destination terminal
            estimated_out: Estimated departure time
            actual_out: Actual departure time
            estimated_in: Estimated arrival time
            actual_in: Actual arrival time
            raw_data: Raw API response data
            source: Data source (aeroapi, manual, webhook)
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            history_data = {
                "trip_id": str(trip_id),
                "flight_number": flight_number,
                "flight_date": flight_date,
                "status": status,
                "gate_origin": gate_origin,
                "gate_destination": gate_destination,
                "terminal_origin": terminal_origin,
                "terminal_destination": terminal_destination,
                "estimated_out": estimated_out,
                "actual_out": actual_out,
                "estimated_in": estimated_in,
                "actual_in": actual_in,
                "raw_data": raw_data,
                "source": source
            }
            
            response = await self._client.post(
                f"{self.rest_url}/flight_status_history",
                json=history_data
            )
            response.raise_for_status()
            
            created_record = response.json()
            
            logger.info("flight_status_saved", 
                trip_id=str(trip_id),
                flight_number=flight_number,
                status=status,
                gate_origin=gate_origin
            )
            
            return DatabaseResult(
                success=True,
                data=created_record[0] if created_record else None,
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("flight_status_save_failed", 
                trip_id=str(trip_id),
                flight_number=flight_number,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def get_latest_flight_status(self, trip_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get the most recent flight status for a trip.
        
        Args:
            trip_id: UUID of the trip
            
        Returns:
            Dict with latest flight status or None
        """
        try:
            response = await self._client.get(
                f"{self.rest_url}/flight_status_history",
                params={
                    "trip_id": f"eq.{trip_id}",
                    "order": "recorded_at.desc",
                    "limit": "1",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            history_data = response.json()
            
            if history_data:
                logger.info("latest_flight_status_retrieved", 
                    trip_id=str(trip_id),
                    status=history_data[0]["status"]
                )
                return history_data[0]
            else:
                logger.info("no_flight_status_history", trip_id=str(trip_id))
                return None
            
        except Exception as e:
            logger.error("latest_flight_status_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return None
    
    async def get_trips_after_departure(self, departure_threshold: datetime) -> List[Trip]:
        """
        Get trips that departed after the given threshold (for landing detection).
        
        Args:
            departure_threshold: Datetime threshold for departure
            
        Returns:
            List of Trip objects
        """
        try:
            threshold_str = departure_threshold.isoformat()
            
            response = await self._client.get(
                f"{self.rest_url}/trips",
                params={
                    "departure_date": f"gte.{threshold_str}",
                    "select": "*"
                }
            )
            response.raise_for_status()
            
            trips_data = response.json()
            trips = [Trip(**trip_data) for trip_data in trips_data]
            
            logger.info("trips_after_departure_retrieved", 
                count=len(trips),
                threshold=threshold_str
            )
            
            return trips
            
        except Exception as e:
            logger.error("trips_after_departure_failed", error=str(e))
            return []
    
    async def execute_query(self, query: str, params: tuple = ()) -> DatabaseResult:
        """
        Execute a raw SQL query (for complex operations).
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            DatabaseResult with query results
        """
        try:
            # Note: This is a simplified implementation
            # In production, you might want to use Supabase's RPC functionality
            # or a proper SQL client for complex queries
            
            logger.warning("execute_query_not_implemented", 
                query=query[:100] + "..." if len(query) > 100 else query
            )
            
            return DatabaseResult(
                success=False,
                error="Raw SQL queries not implemented in current Supabase client"
            )
            
        except Exception as e:
            logger.error("execute_query_failed", error=str(e))
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    async def update_trip_comprehensive(
        self, 
        trip_id: UUID, 
        flight_status: 'FlightStatus',
        update_metadata: bool = True
    ) -> DatabaseResult:
        """
        Update trip with comprehensive flight data from AeroAPI.
        
        This method ensures the trips table stays synchronized with the latest
        flight information, addressing the critical data consistency issue.
        
        Args:
            trip_id: UUID of the trip to update
            flight_status: FlightStatus object from AeroAPI
            update_metadata: Whether to update metadata field with detailed info
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            update_data = {
                "status": flight_status.status,
                "gate": flight_status.gate_origin,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Update departure_date if we have estimated_out
            if flight_status.estimated_out:
                try:
                    # Parse and convert estimated_out to proper datetime
                    estimated_dt = datetime.fromisoformat(
                        flight_status.estimated_out.replace('Z', '+00:00')
                    )
                    update_data["departure_date"] = estimated_dt.isoformat()
                except ValueError as e:
                    logger.warning("invalid_estimated_out_format", 
                        trip_id=str(trip_id),
                        estimated_out=flight_status.estimated_out,
                        error=str(e)
                    )
            
            # Update comprehensive metadata
            if update_metadata:
                metadata = {
                    "last_aeroapi_sync": datetime.now(timezone.utc).isoformat(),
                    "flight_data": {
                        "gate_destination": flight_status.gate_destination,
                        "estimated_in": flight_status.estimated_in,
                        "actual_out": flight_status.actual_out,
                        "actual_in": flight_status.actual_in,
                        "aircraft_type": flight_status.aircraft_type,
                        "progress_percent": flight_status.progress_percent,
                        "departure_delay": flight_status.departure_delay,
                        "arrival_delay": flight_status.arrival_delay,
                        "cancelled": flight_status.cancelled,
                        "diverted": flight_status.diverted,
                        "origin_iata": flight_status.origin_iata,
                        "destination_iata": flight_status.destination_iata
                    }
                }
                update_data["metadata"] = metadata
            
            # Execute update
            response = await self._client.patch(
                f"{self.rest_url}/trips",
                params={"id": f"eq.{trip_id}"},
                json=update_data
            )
            response.raise_for_status()
            
            updated_data = response.json()
            
            logger.info("trip_comprehensive_update_success", 
                trip_id=str(trip_id),
                status=flight_status.status,
                gate=flight_status.gate_origin,
                estimated_out=flight_status.estimated_out,
                updated_fields=list(update_data.keys())
            )
            
            return DatabaseResult(
                success=True,
                data=updated_data[0] if updated_data else None,
                affected_rows=1 if updated_data else 0
            )
            
        except Exception as e:
            logger.error("trip_comprehensive_update_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    async def resync_trip_from_aeroapi(self, trip_id: UUID) -> DatabaseResult:
        """
        Force resync a trip with current AeroAPI data.
        
        This method fetches fresh data from AeroAPI and updates both
        the trips table and flight_status_history.
        
        Args:
            trip_id: UUID of the trip to resync
            
        Returns:
            DatabaseResult with operation status
        """
        try:
            # Get trip data
            trip_result = await self.get_trip_by_id(trip_id)
            if not trip_result.success or not trip_result.data:
                return DatabaseResult(
                    success=False,
                    error="Trip not found"
                )
            
            trip_data = trip_result.data
            
            # Import AeroAPIClient here to avoid circular import
            from ..services.aeroapi_client import AeroAPIClient
            
            aeroapi_client = AeroAPIClient()
            
            # Get fresh flight status
            departure_date = datetime.fromisoformat(
                trip_data["departure_date"].replace('Z', '+00:00')
            )
            flight_date_str = departure_date.strftime("%Y-%m-%d")
            
            current_status = await aeroapi_client.get_flight_status(
                trip_data["flight_number"],
                flight_date_str
            )
            
            if not current_status:
                return DatabaseResult(
                    success=False,
                    error="No flight data available from AeroAPI"
                )
            
            # Update trips table comprehensively
            update_result = await self.update_trip_comprehensive(
                trip_id, 
                current_status,
                update_metadata=True
            )
            
            if not update_result.success:
                return update_result
            
            # Save to flight_status_history (if permissions allow)
            try:
                history_result = await self.save_flight_status(
                    trip_id=trip_id,
                    flight_number=current_status.ident,
                    flight_date=flight_date_str,
                    status=current_status.status,
                    gate_origin=current_status.gate_origin,
                    gate_destination=current_status.gate_destination,
                    estimated_out=current_status.estimated_out,
                    actual_out=current_status.actual_out,
                    estimated_in=current_status.estimated_in,
                    actual_in=current_status.actual_in,
                    source="manual_resync"
                )
                
                if history_result.success:
                    logger.info("flight_status_history_updated", trip_id=str(trip_id))
                else:
                    logger.warning("flight_status_history_update_failed", 
                        trip_id=str(trip_id),
                        error=history_result.error
                    )
                    
            except Exception as history_error:
                logger.warning("flight_status_history_permission_denied", 
                    trip_id=str(trip_id),
                    error=str(history_error)
                )
            
            logger.info("trip_resync_completed", 
                trip_id=str(trip_id),
                flight_number=trip_data["flight_number"],
                new_status=current_status.status,
                new_gate=current_status.gate_origin
            )
            
            return DatabaseResult(
                success=True,
                data={
                    "trip_updated": True,
                    "flight_status": {
                        "status": current_status.status,
                        "gate": current_status.gate_origin,
                        "estimated_out": current_status.estimated_out,
                        "progress": current_status.progress_percent
                    }
                },
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("trip_resync_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            ) 