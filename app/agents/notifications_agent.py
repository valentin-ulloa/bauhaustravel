"""NotificationsAgent for Bauhaus Travel - handles flight notifications via WhatsApp."""

import os
import json
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog

from ..db.supabase_client import SupabaseDBClient
from ..models.database import Trip, DatabaseResult
from .notifications_templates import NotificationType, WhatsAppTemplates
from ..services.aeroapi_client import AeroAPIClient, FlightStatus
from ..services.async_twilio_client import AsyncTwilioClient
from ..services.notification_retry_service import NotificationRetryService
from ..utils.flight_schedule_utils import calculate_unified_next_check, should_suppress_notification_unified
from ..utils.timezone_utils import format_departure_time_human

logger = structlog.get_logger()


class NotificationsAgent:
    """
    Unified notifications agent with simplified architecture.
    
    CONSOLIDATED FEATURES:
    - Unified next_check_at logic (no more duplications)
    - Centralized quiet hours policy  
    - Optimized AeroAPI usage with intelligent caching
    - Dynamic message content using database data
    """
    
    def __init__(self):
        """Initialize the NotificationsAgent with required services."""
        self.db_client = SupabaseDBClient()
        self.aeroapi_client = AeroAPIClient()
        
        # Async Twilio setup
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([account_sid, auth_token, self.twilio_phone]):
            raise ValueError("Missing Twilio credentials in environment variables")
        
        self.async_twilio_client = AsyncTwilioClient(account_sid, auth_token)
        self.retry_service = NotificationRetryService()
        
        service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
        if not service_sid:
            raise ValueError("Missing TWILIO_MESSAGING_SERVICE_SID")
        self.messaging_service_sid = service_sid
        
        logger.info("notifications_agent_initialized", 
            async_architecture=True,
            unified_polling=True,
            intelligent_caching=True
        )
    
    async def run(self, trigger_type: str, **kwargs) -> DatabaseResult:
        """
        Main entry point for the NotificationsAgent.
        
        Args:
            trigger_type: "24h_reminder" | "status_change" | "landing_detected"
            **kwargs: Additional parameters based on trigger type
            
        Returns:
            DatabaseResult with operation status
        """
        logger.info("notifications_agent_triggered", 
            trigger_type=trigger_type
        )
        
        try:
            if trigger_type == "24h_reminder":
                return await self.schedule_24h_reminders()
            elif trigger_type == "status_change":
                return await self.poll_flight_changes()
            elif trigger_type == "landing_detected":
                return await self.poll_landed_flights()
            else:
                return DatabaseResult(success=False, error=f"Unknown trigger type: {trigger_type}")
                
        except Exception as e:
            logger.error("notifications_agent_error", 
                trigger_type=trigger_type,
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def schedule_24h_reminders(self) -> DatabaseResult:
        """
        Send 24h flight reminders with UNIFIED quiet hours policy.
        """
        logger.info("scheduling_24h_reminders")
        
        now_utc = datetime.now(timezone.utc)
        reminder_window_start = now_utc + timedelta(hours=23, minutes=30)
        reminder_window_end = now_utc + timedelta(hours=24, minutes=30)
        
        try:
            all_trips = await self.db_client.get_trips_to_poll(reminder_window_end)
            
            reminder_trips = [
                trip for trip in all_trips 
                if reminder_window_start <= trip.departure_date <= reminder_window_end
            ]
            
            success_count = 0
            
            for trip in reminder_trips:
                # Check if reminder already sent
                history = await self.db_client.get_notification_history(
                    trip.id, NotificationType.REMINDER_24H.value.upper()
                )
                
                if any(log.delivery_status == "SENT" for log in history):
                    continue
                
                # UNIFIED quiet hours check
                should_suppress = should_suppress_notification_unified(
                    "REMINDER_24H", now_utc, trip.origin_iata
                )
                if should_suppress:
                    logger.info("24h_reminder_suppressed_quiet_hours", 
                        trip_id=str(trip.id),
                        origin_iata=trip.origin_iata
                    )
                    continue
                
                # Send reminder with DYNAMIC content from database
                result = await self.send_notification(
                    trip=trip,
                    notification_type=NotificationType.REMINDER_24H,
                    extra_data=await self._get_dynamic_reminder_data(trip)
                )
                
                if result.success:
                    success_count += 1
            
            logger.info("24h_reminders_completed", 
                processed=len(reminder_trips),
                sent=success_count
            )
            
            return DatabaseResult(success=True, data={"sent": success_count})
            
        except Exception as e:
            logger.error("24h_reminders_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    async def _get_dynamic_reminder_data(self, trip: Trip) -> Dict[str, Any]:
        """
        Get dynamic reminder data from database instead of hardcoding.
        
        Uses trip metadata, agency settings, and real-time weather.
        """
        try:
            # Get agency-specific messages if available
            agency_id_str = str(trip.agency_id) if hasattr(trip, 'agency_id') and trip.agency_id else None
            
            # Try to get real weather for destination
            try:
                from ..config.messages import MessageConfig
                weather_info = await MessageConfig.get_weather_text_async(
                    trip.destination_iata, 
                    agency_id_str
                )
            except Exception:
                weather_info = "buen clima para viajar"
            
            # Get trip-specific information from metadata
            additional_info = "¡Buen viaje!"
            if hasattr(trip, 'metadata') and trip.metadata:
                if isinstance(trip.metadata, dict):
                    additional_info = trip.metadata.get(
                        'custom_message', 
                        trip.metadata.get('notes', additional_info)
                    )
            
            return {
                "weather_info": weather_info,
                "additional_info": additional_info
            }
            
        except Exception as e:
            logger.warning("dynamic_reminder_data_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
            return {
                "weather_info": "buen clima para viajar",
                "additional_info": "¡Buen viaje!"
            }
    
    async def poll_flight_changes(self) -> DatabaseResult:
        """
        Poll flight changes with OPTIMIZED AeroAPI usage and UNIFIED next_check_at.
        """
        logger.info("polling_flight_changes_optimized")
        
        now_utc = datetime.now(timezone.utc)
        
        try:
            # Get trips that need status polling
            trips_to_check = await self.db_client.get_trips_to_poll(now_utc)
            
            # Filter active trips only
            active_trips = [
                trip for trip in trips_to_check 
                if trip.departure_date > now_utc
            ]
            
            success_count = 0
            notifications_sent = 0
            
            for trip in active_trips:
                try:
                    # Get current status with INTELLIGENT CACHING
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    current_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if not current_status:
                        # Update next check anyway using UNIFIED logic
                        next_check = calculate_unified_next_check(
                            trip.departure_date, now_utc, "UNKNOWN"
                        )
                        if next_check:
                            await self.db_client.update_next_check_at(trip.id, next_check)
                        success_count += 1
                        continue
                    
                    # Get previous status for comparison
                    previous_status = await self._get_previous_flight_status(trip)
                    
                    # Detect changes with SIMPLIFIED logic
                    changes = self._detect_meaningful_changes(current_status, previous_status)
                    
                    # Save current status
                    await self._save_flight_status_optimized(trip, current_status)
                    
                    # Update trip status if landed
                    if self._is_flight_landed(current_status):
                        await self.db_client.update_trip_status(trip.id, {"status": "LANDED"})
                    
                    # Process changes and send notifications
                    for change in changes:
                        await self._process_flight_change_simplified(trip, change, current_status)
                        notifications_sent += 1
                    
                    # UNIFIED next_check_at calculation
                    estimated_arrival = None
                    if current_status.estimated_in:
                        try:
                            estimated_arrival = datetime.fromisoformat(
                                current_status.estimated_in.replace('Z', '+00:00')
                            )
                        except:
                            pass
                    
                    next_check = calculate_unified_next_check(
                        trip.departure_date, 
                        now_utc, 
                        current_status.status,
                        estimated_arrival
                    )
                    
                    if next_check:
                        await self.db_client.update_next_check_at(trip.id, next_check)
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error("flight_status_check_failed", 
                        trip_id=str(trip.id),
                        error=str(e)
                    )
            
            logger.info("flight_changes_poll_completed", 
                total_checked=len(active_trips),
                success=success_count,
                notifications_sent=notifications_sent
            )
            
            return DatabaseResult(
                success=True,
                data={"checked": len(active_trips), "updates": notifications_sent}
            )
            
        except Exception as e:
            logger.error("flight_changes_poll_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    def _detect_meaningful_changes(
        self, 
        current_status: FlightStatus, 
        previous_status: Optional[FlightStatus]
    ) -> List[Dict[str, Any]]:
        """
        SIMPLIFIED change detection - only meaningful changes that need notifications.
        
        Eliminates ping-pong detection complexity while maintaining accuracy.
        """
        if not previous_status:
            return []
        
        changes = []
        
        # Status change with business impact
        if current_status.status != previous_status.status:
            if self._is_notifiable_status_change(current_status.status):
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
        
        # Significant departure time change (>= 15 minutes)
        if self._is_significant_delay(current_status, previous_status):
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
                "notification_type": "cancelled"
            })
        
        return changes
    
    def _is_significant_delay(
        self, 
        current_status: FlightStatus, 
        previous_status: FlightStatus
    ) -> bool:
        """
        SIMPLIFIED delay detection - only significant delays (>= 15 minutes).
        """
        if not current_status.estimated_out or not previous_status.estimated_out:
            return False
        
        try:
            current_dt = datetime.fromisoformat(current_status.estimated_out.replace('Z', '+00:00'))
            previous_dt = datetime.fromisoformat(previous_status.estimated_out.replace('Z', '+00:00'))
            
            delay_minutes = (current_dt - previous_dt).total_seconds() / 60
            
            # Only notify for delays >= 15 minutes
            return delay_minutes >= 15
            
        except Exception:
            return False
    
    def _is_notifiable_status_change(self, status: str) -> bool:
        """Check if status change requires notification."""
        status_lower = status.lower()
        return any(keyword in status_lower for keyword in [
            'delay', 'late', 'cancel', 'board', 'landed', 'arrived'
        ])
    
    def _map_status_to_notification(self, status: str) -> str:
        """Map flight status to notification type."""
        status_lower = status.lower()
        
        if 'delay' in status_lower or 'late' in status_lower:
            return "delayed"
        elif 'cancel' in status_lower:
            return "cancelled"
        elif 'board' in status_lower:
            return "boarding"
        elif 'landed' in status_lower or 'arrived' in status_lower:
            return "landing"
        else:
            return "delayed"  # Default for unknown status changes
    
    def _is_flight_landed(self, status: FlightStatus) -> bool:
        """Check if flight has landed using multiple indicators."""
        return (
            "arrived" in status.status.lower() or 
            "gate arrival" in status.status.lower() or
            (status.progress_percent and status.progress_percent >= 100) or
            status.actual_in is not None
        )
    
    async def _get_previous_flight_status(self, trip: Trip) -> Optional[FlightStatus]:
        """Get the last known flight status from database."""
        try:
            latest_status = await self.db_client.get_latest_flight_status(trip.id)
            
            if latest_status:
                return FlightStatus(
                    ident=latest_status["flight_number"],
                    status=latest_status["status"],
                    gate_origin=latest_status["gate_origin"],
                    gate_destination=latest_status["gate_destination"],
                    estimated_out=latest_status["estimated_out"],
                    actual_out=latest_status["actual_out"],
                    estimated_in=latest_status["estimated_in"],
                    actual_in=latest_status["actual_in"]
                )
            else:
                # Fallback to trip data
                return FlightStatus(
                    ident=trip.flight_number,
                    status=trip.status or "Scheduled",
                    gate_origin=getattr(trip, 'gate', None),
                    estimated_out=trip.departure_date.isoformat()
                )
        except Exception as e:
            logger.error("previous_status_retrieval_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
            return None
    
    async def _save_flight_status_optimized(self, trip: Trip, status: FlightStatus):
        """Save flight status with OPTIMIZED database updates."""
        try:
            flight_date = trip.departure_date.strftime("%Y-%m-%d")
            
            # Save to history
            await self.db_client.save_flight_status(
                trip_id=trip.id,
                flight_number=status.ident,
                flight_date=flight_date,
                status=status.status,
                gate_origin=status.gate_origin,
                gate_destination=status.gate_destination,
                estimated_out=status.estimated_out,
                actual_out=status.actual_out,
                estimated_in=status.estimated_in,
                actual_in=status.actual_in,
                source="unified_polling"
            )
            
            # Update trip with comprehensive data
            await self.db_client.update_trip_comprehensive(trip.id, status, update_metadata=True)
            
        except Exception as e:
            logger.error("flight_status_save_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
    
    async def _process_flight_change_simplified(
        self, 
        trip: Trip, 
        change: Dict[str, Any], 
        current_status: FlightStatus
    ):
        """
        SIMPLIFIED flight change processing with UNIFIED quiet hours.
        """
        try:
            notification_type = change["notification_type"]
            
            # UNIFIED quiet hours check (only REMINDER_24H suppressed)
            now_utc = datetime.now(timezone.utc)
            should_suppress = should_suppress_notification_unified(
                notification_type, now_utc, trip.origin_iata
            )
            
            if should_suppress:
                logger.info("notification_suppressed_quiet_hours", 
                    trip_id=str(trip.id),
                    notification_type=notification_type
                )
                return
            
            # Prepare extra data with DYNAMIC content
            extra_data = await self._get_dynamic_change_data(trip, change, current_status)
            
            # Map to enum
            notification_enum = self._map_notification_string_to_enum(notification_type)
            if not notification_enum:
                return
            
            # Send notification
            result = await self.send_notification(trip, notification_enum, extra_data)
            
            if result.success:
                logger.info("flight_change_notification_sent", 
                    trip_id=str(trip.id),
                    change_type=change["type"],
                    notification_type=notification_type
                )
        
        except Exception as e:
            logger.error("flight_change_processing_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
    
    async def _get_dynamic_change_data(
        self, 
        trip: Trip, 
        change: Dict[str, Any], 
        current_status: FlightStatus
    ) -> Dict[str, Any]:
        """
        Get dynamic change data using database information instead of hardcoding.
        """
        extra_data = {}
        
        change_type = change["type"]
        notification_type = change["notification_type"]
        
        if change_type == "gate_change":
            extra_data["new_gate"] = change["new_value"]
            extra_data["old_gate"] = change["old_value"]
            
        elif change_type == "departure_time_change":
            # Format time using proper timezone
            new_time = change["new_value"]
            if new_time and "T" in new_time:
                try:
                    dt = datetime.fromisoformat(new_time.replace('Z', '+00:00'))
                    formatted_time = format_departure_time_human(dt, trip.origin_iata)
                    extra_data["new_departure_time"] = formatted_time
                except:
                    extra_data["new_departure_time"] = "Por confirmar"
            else:
                extra_data["new_departure_time"] = "Por confirmar"
                
        elif notification_type == "boarding":
            # PRIORITY: Use real gate data from current status or DB
            gate_info = (
                current_status.gate_origin or 
                getattr(trip, 'gate', None) or
                "Ver pantallas del aeropuerto"
            )
            extra_data["gate"] = gate_info
        
        return extra_data
    
    def _map_notification_string_to_enum(self, notification_type: str) -> Optional[NotificationType]:
        """Map string notification type to enum."""
        mapping = {
            "delayed": NotificationType.DELAYED,
            "cancelled": NotificationType.CANCELLED,
            "boarding": NotificationType.BOARDING,
            "gate_change": NotificationType.GATE_CHANGE,
            "landing": NotificationType.LANDING_WELCOME
        }
        return mapping.get(notification_type)
    
    async def poll_landed_flights(self) -> DatabaseResult:
        """
        Check for landed flights with OPTIMIZED detection.
        """
        logger.info("polling_landed_flights_optimized")
        
        now_utc = datetime.now(timezone.utc)
        
        try:
            potential_landing_time = now_utc - timedelta(hours=8)
            trips_to_check = await self.db_client.get_trips_after_departure(potential_landing_time)
            
            landed_count = 0
            
            for trip in trips_to_check:
                try:
                    # Check if landing notification already sent
                    history = await self.db_client.get_notification_history(
                        trip.id, NotificationType.LANDING_WELCOME.value.upper()
                    )
                    
                    if any(log.delivery_status == "SENT" for log in history):
                        continue
                    
                    # Get current status
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    current_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if current_status and self._is_flight_landed(current_status):
                        # Update trip status
                        await self.db_client.update_trip_status(trip.id, {"status": "LANDED"})
                        
                        # Save status to history
                        await self._save_flight_status_optimized(trip, current_status)
                        
                        # Check quiet hours at destination
                        from ..utils.timezone_utils import is_quiet_hours_local
                        is_quiet = is_quiet_hours_local(now_utc, trip.destination_iata)
                        
                        if not is_quiet:
                            # Send landing welcome
                            result = await self.send_notification(
                                trip=trip,
                                notification_type=NotificationType.LANDING_WELCOME,
                                extra_data=await self._get_dynamic_landing_data(trip)
                            )
                            
                            if result.success:
                                landed_count += 1
                                logger.info("landing_welcome_sent", trip_id=str(trip.id))
                        else:
                            logger.info("landing_notification_deferred_quiet_hours", 
                                trip_id=str(trip.id),
                                destination_iata=trip.destination_iata
                            )
                    
                except Exception as e:
                    logger.error("landing_detection_failed_for_trip", 
                        trip_id=str(trip.id),
                        error=str(e)
                    )
            
            return DatabaseResult(success=True, data={"landed_flights": landed_count})
            
        except Exception as e:
            logger.error("landing_detection_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    async def _get_dynamic_landing_data(self, trip: Trip) -> Dict[str, Any]:
        """
        Get dynamic landing data from trip metadata and database.
        """
        hotel_address = "tu alojamiento reservado"
        
        # Try to get hotel info from trip metadata
        if hasattr(trip, 'metadata') and trip.metadata:
            if isinstance(trip.metadata, dict):
                hotel_address = (
                    trip.metadata.get("hotel_address") or 
                    trip.metadata.get("accommodation_address") or
                    trip.metadata.get("hotel_name") or
                    hotel_address
                )
        
        return {"hotel_address": hotel_address}
    
    async def send_notification(
        self, 
        trip: Trip, 
        notification_type: NotificationType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Send WhatsApp notification with SIMPLIFIED idempotency.
        """
        notification_type_db = notification_type.value.upper()
        
        # SIMPLIFIED idempotency hash
        idempotency_data = {
            "trip_id": str(trip.id),
            "notification_type": notification_type_db,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")  # Daily uniqueness
        }
        idempotency_hash = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # Check if notification already sent today
        try:
            existing = await self.db_client.execute_query(
                """
                SELECT id FROM notifications_log 
                WHERE trip_id = %s AND notification_type = %s AND idempotency_hash = %s 
                AND delivery_status = 'SENT'
                LIMIT 1
                """,
                (str(trip.id), notification_type_db, idempotency_hash)
            )
            
            if existing.data:
                return DatabaseResult(success=True, data={"status": "already_sent_today"})
        except Exception:
            pass  # Continue with send attempt
        
        try:
            # Format message
            message_data = await self.format_message(trip, notification_type, extra_data)
            
            # Send with retry
            async def send_func():
                result = await self.async_twilio_client.send_template_message(
                    to=f"whatsapp:{trip.whatsapp}",
                    messaging_service_sid=self.messaging_service_sid,
                    content_sid=message_data["template_sid"],
                    content_variables=message_data["template_variables"]
                )
                
                if result.error_code:
                    return DatabaseResult(
                        success=False,
                        error=f"Twilio error {result.error_code}: {result.error_message}"
                    )
                
                return DatabaseResult(
                    success=True,
                    data={"message_sid": result.sid, "status": result.status}
                )
            
            send_result = await self.retry_service.send_with_retry(
                send_func=send_func,
                max_attempts=3,
                context={
                    "trip_id": str(trip.id),
                    "notification_type": notification_type_db
                }
            )
            
            # Log result
            await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,
                sent_at=datetime.now(timezone.utc),
                status="SENT" if send_result.success else "FAILED",
                template_name=message_data["template_name"],
                twilio_message_sid=send_result.data.get("message_sid") if send_result.success else None,
                error_message=send_result.error if not send_result.success else None,
                retry_count=send_result.data.get("retry_count", 0) if send_result.data else 0,
                idempotency_hash=idempotency_hash
            )
            
            return send_result
            
        except Exception as e:
            await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,
                sent_at=datetime.now(timezone.utc),
                status="FAILED",
                template_name=WhatsAppTemplates.get_template_info(notification_type)["name"],
                error_message=str(e),
                idempotency_hash=idempotency_hash
            )
            
            return DatabaseResult(success=False, error=str(e))
    
    async def format_message(
        self, 
        trip: Trip, 
        notification_type: NotificationType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Format WhatsApp message using DYNAMIC data from database.
        """
        # Use human-readable time formatting
        formatted_departure_time = format_departure_time_human(trip.departure_date, trip.origin_iata)
        
        trip_data = {
            "client_name": trip.client_name,
            "flight_number": trip.flight_number,
            "origin_iata": trip.origin_iata,
            "destination_iata": trip.destination_iata,
            "departure_date": trip.departure_date.isoformat(),
            "departure_time": formatted_departure_time,
            "status": trip.status,
            "metadata": getattr(trip, 'metadata', {})
        }
        
        if extra_data:
            trip_data.update(extra_data)
        
        # Delegate to templates with enhanced data
        if notification_type == NotificationType.REMINDER_24H:
            weather_info = extra_data.get("weather_info", "buen clima") if extra_data else "buen clima"
            additional_info = extra_data.get("additional_info", "¡Buen viaje!") if extra_data else "¡Buen viaje!"
            return WhatsAppTemplates.format_24h_reminder(trip_data, weather_info, additional_info)
        
        elif notification_type == NotificationType.DELAYED:
            new_departure_time = extra_data.get("new_departure_time", "Por confirmar") if extra_data else "Por confirmar"
            return WhatsAppTemplates.format_delayed_flight(trip_data, new_departure_time)
        
        elif notification_type == NotificationType.GATE_CHANGE:
            new_gate = extra_data.get("new_gate", "Por confirmar") if extra_data else "Por confirmar"
            return WhatsAppTemplates.format_gate_change(trip_data, new_gate)
        
        elif notification_type == NotificationType.CANCELLED:
            return WhatsAppTemplates.format_cancelled_flight(trip_data)
        
        elif notification_type == NotificationType.BOARDING:
            gate = extra_data.get("gate", "Ver pantallas") if extra_data else "Ver pantallas"
            return WhatsAppTemplates.format_boarding_call(trip_data, gate)
        
        elif notification_type == NotificationType.RESERVATION_CONFIRMATION:
            return WhatsAppTemplates.format_reservation_confirmation(trip_data)
        
        elif notification_type == NotificationType.ITINERARY_READY:
            return WhatsAppTemplates.format_itinerary_ready(trip_data)
        
        elif notification_type == NotificationType.LANDING_WELCOME:
            hotel_address = extra_data.get("hotel_address", "tu alojamiento reservado") if extra_data else "tu alojamiento reservado"
            return await WhatsAppTemplates.format_landing_welcome_async(trip_data, hotel_address)
        
        else:
            raise ValueError(f"Unknown notification type: {notification_type}")
    
    async def send_single_notification(
        self, 
        trip_id: UUID, 
        notification_type: NotificationType, 
        extra_data: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """Send a single notification for a specific trip."""
        try:
            trip_result = await self.db_client.get_trip_by_id(trip_id)
            if not trip_result.success or not trip_result.data:
                return DatabaseResult(success=False, error=f"Trip {trip_id} not found")
            
            trip = Trip(**trip_result.data)
            return await self.send_notification(trip, notification_type, extra_data)
            
        except Exception as e:
            return DatabaseResult(success=False, error=str(e))
    
    async def check_single_trip_status(self, trip: Trip) -> DatabaseResult:
        """
        Check flight status for a single trip with UNIFIED logic.
        """
        try:
            flight_date_str = trip.departure_date.strftime("%Y-%m-%d")
            current_status = await self.aeroapi_client.get_flight_status(
                trip.flight_number,
                flight_date_str
            )
            
            if not current_status:
                return DatabaseResult(
                    success=True,
                    data={"trip_id": str(trip.id), "status": "no_flight_data"}
                )
            
            # Get previous status and detect changes
            previous_status = await self._get_previous_flight_status(trip)
            changes = self._detect_meaningful_changes(current_status, previous_status)
            
            # Update trip and save status
            await self.db_client.update_trip_comprehensive(trip.id, current_status)
            await self._save_flight_status_optimized(trip, current_status)
            
            # Process changes
            notifications_sent = 0
            for change in changes:
                try:
                    await self._process_flight_change_simplified(trip, change, current_status)
                    notifications_sent += 1
                except Exception as change_error:
                    logger.error("single_trip_change_processing_failed",
                        trip_id=str(trip.id),
                        error=str(change_error)
                    )
            
            return DatabaseResult(
                success=True,
                data={
                    "trip_id": str(trip.id),
                    "current_status": current_status.status,
                    "changes_detected": len(changes),
                    "notifications_sent": notifications_sent
                }
            )
            
        except Exception as e:
            return DatabaseResult(success=False, error=str(e))
    
    async def send_free_text(
        self,
        whatsapp_number: str,
        message: str,
        attachments: Optional[List[str]] = None
    ) -> DatabaseResult:
        """Send free text message for ConciergeAgent."""
        try:
            async def send_func():
                result = await self.async_twilio_client.send_text_message(
                    to=f"whatsapp:{whatsapp_number}",
                    messaging_service_sid=self.messaging_service_sid,
                    body=message
                )
                
                if result.error_code:
                    return DatabaseResult(
                        success=False,
                        error=f"Twilio error {result.error_code}: {result.error_message}"
                    )
                
                return DatabaseResult(
                    success=True,
                    data={"message_sid": result.sid, "status": result.status}
                )
            
            send_result = await self.retry_service.send_with_retry(
                send_func=send_func,
                max_attempts=3,
                context={"to_number": whatsapp_number, "message_type": "free_text"}
            )
            
            # Handle attachments if message sent successfully
            if send_result.success and attachments:
                for attachment_url in attachments:
                    try:
                        await self.async_twilio_client.send_media_message(
                            to=f"whatsapp:{whatsapp_number}",
                            messaging_service_sid=self.messaging_service_sid,
                            media_url=attachment_url
                        )
                    except Exception as e:
                        logger.error("attachment_send_exception",
                            to_number=whatsapp_number,
                            attachment_url=attachment_url,
                            error=str(e)
                        )
            
            return send_result
            
        except Exception as e:
            return DatabaseResult(success=False, error=str(e))
    
    async def close(self):
        """Clean up resources."""
        await self.db_client.close()
        logger.info("notifications_agent_closed") 