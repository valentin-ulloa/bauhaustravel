"""Supabase database client for Bauhaus Travel."""

import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import httpx
import structlog
from ..models.database import Trip, NotificationLog, DatabaseResult

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