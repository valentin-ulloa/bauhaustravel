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
from .notifications_templates import NotificationType, WhatsAppTemplates, get_notification_type_for_status
from ..services.aeroapi_client import AeroAPIClient, FlightStatus
from ..services.async_twilio_client import AsyncTwilioClient
from ..services.notification_retry_service import NotificationRetryService
from ..utils.timezone_utils import is_quiet_hours_local, format_departure_time_local, should_suppress_notification, format_departure_time_human, round_eta_to_5min

logger = structlog.get_logger()


class NotificationsAgent:
    """
    Autonomous agent for flight notifications.
    
    Handles:
    - 24h flight reminders (09:00-20:00 local time)
    - Flight status changes (delays, gate changes, cancellations)  
    - Landing welcome messages
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
            twilio_phone=self.twilio_phone,
            aeroapi_enabled=self.aeroapi_client.api_key is not None,
            async_twilio_enabled=True
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
            trigger_type=trigger_type,
            kwargs=kwargs
        )
        
        try:
            if trigger_type == "24h_reminder":
                return await self.schedule_24h_reminders()
            elif trigger_type == "status_change":
                return await self.poll_flight_changes()
            elif trigger_type == "landing_detected":
                return await self.poll_landed_flights()
            else:
                error_msg = f"Unknown trigger type: {trigger_type}"
                logger.error("unknown_trigger_type", trigger_type=trigger_type)
                return DatabaseResult(success=False, error=error_msg)
                
        except Exception as e:
            logger.error("notifications_agent_error", 
                trigger_type=trigger_type,
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def send_single_notification(
        self, 
        trip_id: UUID, 
        notification_type: NotificationType, 
        extra_data: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Send a single notification for a specific trip.
        
        This method is designed for immediate notifications (e.g., booking confirmations)
        triggered directly from API endpoints.
        
        Args:
            trip_id: UUID of the trip to send notification for
            notification_type: Type of notification to send (matches template enums)
            extra_data: Additional data for template formatting
            
        Returns:
            DatabaseResult with operation status
        """
        logger.info("sending_single_notification", 
            trip_id=str(trip_id),
            notification_type=notification_type
        )
        
        try:
            # Load trip from database
            trip_result = await self.db_client.get_trip_by_id(trip_id)
            if not trip_result.success:
                error_msg = f"Failed to load trip {trip_id}: {trip_result.error}"
                logger.error("trip_load_failed", 
                    trip_id=str(trip_id),
                    error=trip_result.error
                )
                return DatabaseResult(success=False, error=error_msg)
            
            trip_data = trip_result.data
            if not trip_data:
                error_msg = f"Trip {trip_id} not found"
                logger.error("trip_not_found", trip_id=str(trip_id))
                return DatabaseResult(success=False, error=error_msg)
            
            # Convert dict back to Trip object for send_notification method
            trip = Trip(**trip_data)
            
            # Send the notification using existing send_notification method
            result = await self.send_notification(trip, notification_type, extra_data)
            
            if result.success:
                logger.info("single_notification_sent", 
                    trip_id=str(trip_id),
                    notification_type=notification_type,
                    message_sid=result.data.get("message_sid") if result.data else None
                )
            else:
                logger.error("single_notification_failed", 
                    trip_id=str(trip_id),
                    notification_type=notification_type,
                    error=result.error
                )
            
            return result
            
        except Exception as e:
            logger.error("single_notification_error", 
                trip_id=str(trip_id),
                notification_type=notification_type,
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def schedule_24h_reminders(self) -> DatabaseResult:
        """
        Send 24h flight reminders.
        
        Business rules:
        - Send 24 hours before departure
        - Only between 09:00-20:00 local time (CRITICAL: Only reminders respect quiet hours)
        - If outside window, schedule for 09:00 same day
        """
        logger.info("scheduling_24h_reminders")
        
        # Get trips that need 24h reminders
        now_utc = datetime.now(timezone.utc)
        reminder_window_start = now_utc + timedelta(hours=23, minutes=30)  # 23.5h to 24.5h window
        reminder_window_end = now_utc + timedelta(hours=24, minutes=30)
        
        try:
            # Query trips in the 24h window
            all_trips = await self.db_client.get_trips_to_poll(reminder_window_end)
            
            # Filter for trips that need 24h reminders
            reminder_trips = [
                trip for trip in all_trips 
                if reminder_window_start <= trip.departure_date <= reminder_window_end
            ]
            
            success_count = 0
            error_count = 0
            
            for trip in reminder_trips:
                # Check if reminder already sent
                history = await self.db_client.get_notification_history(
                    trip.id, NotificationType.REMINDER_24H
                )
                
                if any(log.delivery_status == "SENT" for log in history):
                    logger.info("24h_reminder_already_sent", trip_id=str(trip.id))
                    continue
                
                # FIXED: Use new quiet hours logic - only suppress REMINDER_24H
                should_suppress = should_suppress_notification("REMINDER_24H", now_utc, trip.origin_iata)
                if should_suppress:
                    logger.info("24h_reminder_suppressed_quiet_hours", 
                        trip_id=str(trip.id),
                        origin_iata=trip.origin_iata,
                        local_quiet_hours=True
                    )
                    continue
                
                # Send notification - REMOVED DEBUG TEXT
                result = await self.send_notification(
                    trip=trip,
                    notification_type=NotificationType.REMINDER_24H,
                    extra_data={
                        "weather_info": "buen clima para volar",
                        "additional_info": "¡Buen viaje!"  # FIXED: Removed debug text
                    }
                )
                
                if result.success:
                    success_count += 1
                else:
                    error_count += 1
            
            logger.info("24h_reminders_completed", 
                processed=len(reminder_trips),
                sent=success_count,
                errors=error_count
            )
            
            return DatabaseResult(
                success=True,
                data={"sent": success_count, "errors": error_count},
                affected_rows=success_count
            )
            
        except Exception as e:
            logger.error("24h_reminders_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    async def poll_flight_changes(self) -> DatabaseResult:
        """
        Poll for flight status changes using AeroAPI and send updates.
        
        Implements smart polling based on departure proximity:
        - > 48h: No check yet
        - 30h-12h: Every 6h  
        - 12h-3h: Every 3h
        - 3h-1h: Every 30min
        - 1h-departure: Every 10min
        - In-flight: Every 30min until landing
        
        Checks for:
        - Status changes (Scheduled -> Delayed, etc.)
        - Gate changes
        - Departure time changes (estimated_out)
        - Cancellations
        - Diversions
        """
        logger.info("polling_flight_changes_with_aeroapi")
        
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        
        try:
            # Get trips that need status polling (departure > now AND next_check_at <= now)
            trips_to_check = await self.db_client.get_trips_to_poll(now_utc)
            
            # Filter for trips that should be checked (departure is in future)
            active_trips = [
                trip for trip in trips_to_check 
                if trip.departure_date > now_utc
            ]
            
            success_count = 0
            error_count = 0
            notifications_sent = 0
            
            logger.info("flight_polling_started", 
                total_trips=len(trips_to_check),
                active_trips=len(active_trips)
            )
            
            for trip in active_trips:
                try:
                    # Get current flight status from AeroAPI
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    current_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if not current_status:
                        logger.info("flight_status_not_available", 
                            trip_id=str(trip.id),
                            flight_number=trip.flight_number,
                            departure_date=departure_date_str
                        )
                        # Update next check time anyway
                        next_check = self.calculate_next_check_time(trip.departure_date, now_utc)
                        await self.db_client.update_next_check_at(trip.id, next_check)
                        success_count += 1
                        continue
                    
                    # Get previous status from our database (if any)
                    previous_status = await self._get_previous_flight_status(trip)
                    
                    # Detect changes
                    changes = self.aeroapi_client.detect_flight_changes(current_status, previous_status)
                    
                    # CONSOLIDATE PING-PONG CHANGES: Filter out A→B→A patterns in same cycle
                    consolidated_changes = self._consolidate_ping_pong_changes(changes, trip)
                    
                    # Save current status to database
                    await self._save_flight_status(trip, current_status)
                    
                    # Process each consolidated change and send notifications
                    for change in consolidated_changes:
                        # Check quiet hours based on origin airport timezone
                        is_quiet_hours = is_quiet_hours_local(now_utc, trip.origin_iata)
                        
                        if not is_quiet_hours:  # Only send notifications during allowed hours
                            await self._process_flight_change(trip, change, current_status)
                            notifications_sent += 1
                        else:
                            logger.info("notification_deferred_quiet_hours", 
                                trip_id=str(trip.id),
                                change_type=change["type"],
                                origin_iata=trip.origin_iata,
                                local_quiet_hours=True
                            )
                    
                    # Update next check time based on poll optimization rules
                    next_check = self.calculate_next_check_time(trip.departure_date, now_utc)
                    await self.db_client.update_next_check_at(trip.id, next_check)
                    
                    success_count += 1
                    
                    logger.info("flight_status_checked", 
                        trip_id=str(trip.id),
                        flight_number=trip.flight_number,
                        status=current_status.status,
                        changes_detected=len(consolidated_changes),
                        next_check=next_check.isoformat()
                    )
                
                except Exception as e:
                    logger.error("flight_status_check_failed", 
                        trip_id=str(trip.id),
                        flight_number=trip.flight_number,
                        error=str(e)
                    )
                    error_count += 1
                    
                    # Still update next check time for failed checks
                    try:
                        next_check = self.calculate_next_check_time(trip.departure_date, now_utc)
                        await self.db_client.update_next_check_at(trip.id, next_check)
                    except Exception as update_error:
                        logger.error("next_check_update_failed", 
                            trip_id=str(trip.id),
                            error=str(update_error)
                        )
            
            logger.info("flight_changes_poll_completed", 
                total_checked=len(active_trips),
                success=success_count,
                errors=error_count,
                notifications_sent=notifications_sent
            )
            
            return DatabaseResult(
                success=True,
                data={
                    "checked": len(active_trips), 
                    "updates": notifications_sent,
                    "errors": error_count
                },
                affected_rows=success_count
            )
            
        except Exception as e:
            logger.error("flight_changes_poll_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    async def _get_previous_flight_status(self, trip: Trip) -> Optional[FlightStatus]:
        """Get the last known flight status from flight_status_history table"""
        try:
            # Get latest status from history table
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
                # Fallback to trip data for first-time flights
                return FlightStatus(
                    ident=trip.flight_number,
                    status=trip.status or "Scheduled",
                    gate_origin=getattr(trip, 'gate', None),
                    estimated_out=trip.departure_date.isoformat() if trip.departure_date else None
                )
        except Exception as e:
            logger.error("previous_status_retrieval_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
            return None
    
    async def _save_flight_status(self, trip: Trip, status: FlightStatus):
        """Save current flight status to flight_status_history table"""
        try:
            # Save to flight_status_history table for precise tracking
            flight_date = trip.departure_date.strftime("%Y-%m-%d")
            
            result = await self.db_client.save_flight_status(
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
                raw_data=getattr(status, 'raw_data', None),
                source="aeroapi"
            )
            
            if result.success:
                # Also update trip table for quick access
                update_data = {
                    "status": status.status,
                    "gate": status.gate_origin
                }
                await self.db_client.update_trip_status(trip.id, update_data)
                
                logger.info("flight_status_saved", 
                    trip_id=str(trip.id),
                    status=status.status,
                    gate=status.gate_origin,
                    history_id=result.data.get("id") if result.data else None
                )
            else:
                logger.error("flight_status_history_save_failed", 
                    trip_id=str(trip.id),
                    error=result.error
                )
            
        except Exception as e:
            logger.error("flight_status_save_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
    
    async def _process_flight_change(
        self, 
        trip: Trip, 
        change: Dict[str, Any], 
        current_status: FlightStatus
    ):
        """Process a detected flight change and send appropriate notification with advanced deduplication"""
        try:
            change_type = change["type"]
            notification_type = change["notification_type"]
            
            # CRITICAL BUSINESS RULE: Only REMINDER_24H respects quiet hours
            # All other events (DELAYED, CANCELLED, BOARDING, GATE_CHANGE) send 24/7
            now_utc = datetime.now(timezone.utc)
            should_suppress = should_suppress_notification(notification_type, now_utc, trip.origin_iata)
            
            if should_suppress:
                logger.info("notification_suppressed_quiet_hours", 
                    trip_id=str(trip.id),
                    notification_type=notification_type,
                    origin_iata=trip.origin_iata
                )
                return
            
            # Prepare extra data for template formatting
            extra_data = {
                "old_value": change.get("old_value"),
                "new_value": change.get("new_value"),
                "change_type": change_type
            }
            
            # ADVANCED DEDUPLICATION FOR DELAYED NOTIFICATIONS
            if notification_type == "delayed":
                # Check 15-minute cooldown for DELAYED notifications
                if not await self._should_send_delay_notification(trip, change, now_utc):
                    return
                
                # Get the final ETA to send (prioritize concrete times over TBD)
                final_eta = self._get_prioritized_eta(change.get("new_value", ""), trip.origin_iata)
                
                # Create enhanced deduplication hash
                dedup_data = {
                    "trip_id": str(trip.id),
                    "type": "DELAYED",
                    "eta_final": final_eta
                }
                dedup_hash = hashlib.sha256(
                    json.dumps(dedup_data, sort_keys=True).encode()
                ).hexdigest()[:16]
                
                # Store the hash for deduplication
                extra_data["dedup_hash"] = dedup_hash
                extra_data["new_departure_time"] = final_eta
            
            # Add specific data based on change type
            if change_type == "gate_change":
                extra_data["new_gate"] = change["new_value"]
                extra_data["old_gate"] = change["old_value"]
            elif change_type == "departure_time_change":
                extra_data["new_departure_time"] = change["new_value"]
                extra_data["old_departure_time"] = change["old_value"]
            elif change_type == "status_change":
                extra_data["new_status"] = change["new_value"]
                extra_data["old_status"] = change["old_value"]
            
            # FIXED: Add gate information for boarding notifications
            if notification_type == "boarding":
                extra_data["gate"] = current_status.gate_origin or "Ver pantallas"
            
            # Map notification type to our enum
            notification_enum = self._map_notification_type(notification_type)
            if not notification_enum:
                logger.warning("unknown_notification_type", 
                    notification_type=notification_type,
                    change_type=change_type
                )
                return
            
            # Send notification
            result = await self.send_notification(trip, notification_enum, extra_data)
            
            if result.success:
                logger.info("flight_change_notification_sent", 
                    trip_id=str(trip.id),
                    change_type=change_type,
                    notification_type=notification_type,
                    message_sid=result.data.get("message_sid") if result.data else None
                )
            else:
                logger.error("flight_change_notification_failed", 
                    trip_id=str(trip.id),
                    change_type=change_type,
                    error=result.error
                )
        
        except Exception as e:
            logger.error("flight_change_processing_failed", 
                trip_id=str(trip.id),
                change_type=change.get("type"),
                error=str(e)
            )
    
    async def _should_send_delay_notification(
        self, 
        trip: Trip, 
        change: Dict[str, Any], 
        now_utc: datetime
    ) -> bool:
        """
        Determine if a DELAYED notification should be sent based on cooldown and content.
        
        Rules:
        1. 15-minute cooldown between DELAYED notifications
        2. Don't send if new ETA is same as last notified ETA
        3. Prioritize concrete times over TBD
        """
        try:
            new_eta = change.get("new_value", "")
            final_eta = self._get_prioritized_eta(new_eta, trip.origin_iata)
            
            # Check last DELAYED notification within 15 minutes
            recent_delay_logs = await self.db_client.execute_query(
                """
                SELECT sent_at, template_name, twilio_message_sid 
                FROM notifications_log 
                WHERE trip_id = %s AND notification_type = 'DELAYED' 
                AND delivery_status = 'SENT'
                AND sent_at > %s
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (str(trip.id), now_utc - timedelta(minutes=15))
            )
            
            if recent_delay_logs.data:
                last_sent_at = datetime.fromisoformat(recent_delay_logs.data[0]["sent_at"])
                cooldown_remaining = 900 - (now_utc - last_sent_at).total_seconds()  # 15 min = 900 sec
                
                logger.info("delay_notification_cooldown_active", 
                    trip_id=str(trip.id),
                    cooldown_remaining_seconds=int(cooldown_remaining),
                    last_sent_at=last_sent_at.isoformat()
                )
                return False
            
            # Check if this ETA was already sent recently (even outside cooldown)
            recent_eta_logs = await self.db_client.execute_query(
                """
                SELECT id FROM notifications_log 
                WHERE trip_id = %s AND notification_type = 'DELAYED' 
                AND delivery_status = 'SENT'
                AND sent_at > %s
                AND template_name LIKE %s
                LIMIT 1
                """,
                (str(trip.id), now_utc - timedelta(hours=2), f"%{final_eta}%")
            )
            
            if recent_eta_logs.data:
                logger.info("delay_notification_same_eta_already_sent", 
                    trip_id=str(trip.id),
                    eta=final_eta
                )
                return False
            
            logger.info("delay_notification_approved", 
                trip_id=str(trip.id),
                final_eta=final_eta
            )
            return True
            
        except Exception as e:
            logger.error("delay_cooldown_check_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
            # On error, allow sending (better to over-notify than miss critical updates)
            return True
    
    def _get_prioritized_eta(self, new_eta: str, origin_iata: str = None) -> str:
        """
        Prioritize concrete times over TBD/Por confirmar.
        
        Returns the most informative ETA format for notifications.
        """
        if not new_eta or new_eta in ["", "null", "None", "NULL"]:
            return "Por confirmar"
        
        try:
            # If it's an ISO datetime, format it nicely
            if "T" in new_eta and len(new_eta) > 10:
                dt = datetime.fromisoformat(new_eta.replace('Z', '+00:00'))
                # Use our existing human formatting
                from ..utils.timezone_utils import format_departure_time_human
                if origin_iata:
                    return format_departure_time_human(dt, origin_iata)
                else:
                    # Fallback to UTC format if no origin provided
                    return dt.strftime("%d %b %H:%M UTC")
            else:
                # Already formatted or simple string
                return new_eta if new_eta != "null" else "Por confirmar"
        except Exception as e:
            logger.warning("eta_formatting_failed", 
                eta=new_eta, 
                error=str(e)
            )
            return new_eta if new_eta and new_eta != "null" else "Por confirmar"
    
    def _map_notification_type(self, notification_type: str) -> Optional[NotificationType]:
        """Map string notification type to our enum"""
        mapping = {
            "delayed": NotificationType.DELAYED,
            "cancelled": NotificationType.CANCELLED,
            "boarding": NotificationType.BOARDING,
            "gate_change": NotificationType.GATE_CHANGE,
            "landing": NotificationType.LANDING_WELCOME,  # ADDED: Landing support
            # Add more mappings as needed
        }
        return mapping.get(notification_type)
    
    async def poll_landed_flights(self) -> DatabaseResult:
        """
        Check for landed flights and send welcome messages.
        
        Detects flights that have status "LANDED", "ARRIVED", or "COMPLETED"
        and sends welcome notifications if not already sent.
        """
        logger.info("polling_landed_flights")
        
        now_utc = datetime.now(timezone.utc)
        
        try:
            # Get flights that should have landed (departure + 8 hours as rough estimate)
            potential_landing_time = now_utc - timedelta(hours=8)
            trips_to_check = await self.db_client.get_trips_after_departure(potential_landing_time)
            
            landed_count = 0
            error_count = 0
            
            for trip in trips_to_check:
                try:
                    # Check if we already sent landing notification
                    history = await self.db_client.get_notification_history(
                        trip.id, "LANDING_WELCOME"
                    )
                    
                    if any(log.delivery_status == "SENT" for log in history):
                        continue
                    
                    # Get current flight status from AeroAPI
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    current_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if current_status and current_status.status.upper() in ["LANDED", "ARRIVED", "COMPLETED"]:
                        # Save the landed status to history
                        await self._save_flight_status(trip, current_status)
                        
                        # Check quiet hours before sending
                        is_quiet_hours = is_quiet_hours_local(now_utc, trip.destination_iata)
                        
                        if not is_quiet_hours:
                            # Send landing welcome notification
                            logger.info("landing_detected_sending_welcome",
                                trip_id=str(trip.id),
                                flight_number=trip.flight_number,
                                status=current_status.status
                            )
                            
                            # Use proper LANDING_WELCOME template
                            result = await self.send_notification(
                                trip=trip,
                                notification_type=NotificationType.LANDING_WELCOME,
                                extra_data={
                                    "hotel_address": "tu alojamiento reservado"  # Will be enhanced with real data
                                }
                            )
                            
                            if result.success:
                                landed_count += 1
                                logger.info("landing_welcome_sent",
                                    trip_id=str(trip.id),
                                    message_sid=result.data.get("message_sid") if result.data else None
                                )
                            else:
                                logger.error("landing_welcome_failed",
                                    trip_id=str(trip.id),
                                    error=result.error
                                )
                        else:
                            logger.info("landing_notification_deferred_quiet_hours", 
                                trip_id=str(trip.id),
                                destination_iata=trip.destination_iata
                            )
                    
                except Exception as e:
                    logger.error("landing_detection_failed_for_trip", 
                        trip_id=str(trip.id),
                        flight_number=trip.flight_number,
                        error=str(e)
                    )
                    error_count += 1
            
            logger.info("landing_detection_completed", 
                trips_checked=len(trips_to_check),
                landed_notifications_sent=landed_count,
                errors=error_count
            )
            
            return DatabaseResult(
                success=True,
                data={"landed_flights": landed_count, "errors": error_count},
                affected_rows=landed_count
            )
            
        except Exception as e:
            logger.error("landing_detection_failed", error=str(e))
            return DatabaseResult(success=False, error=str(e))
    
    async def send_notification(
        self, 
        trip: Trip, 
        notification_type: NotificationType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Send WhatsApp notification using async Twilio client with retry logic.
        
        Args:
            trip: Trip object with flight details
            notification_type: Type of notification to send
            extra_data: Additional data for template formatting
            
        Returns:
            DatabaseResult with send status
        """
        notification_type_db = notification_type.value.upper()
        
        # ENHANCED: Use dedup_hash if provided for DELAYED notifications
        if extra_data and "dedup_hash" in extra_data:
            idempotency_hash = extra_data["dedup_hash"]
        else:
            # Generate standard idempotency hash
            idempotency_data = {
                "trip_id": str(trip.id),
                "notification_type": notification_type_db,
                "extra_data": {k: v for k, v in (extra_data or {}).items() if k != "dedup_hash"}
            }
            idempotency_hash = hashlib.sha256(
                json.dumps(idempotency_data, sort_keys=True).encode()
            ).hexdigest()[:16]
        
        # Check if notification already sent
        try:
            existing_notification = await self.db_client.execute_query(
                """
                SELECT id FROM notifications_log 
                WHERE trip_id = %s AND notification_type = %s AND idempotency_hash = %s 
                AND delivery_status = 'SENT'
                LIMIT 1
                """,
                (str(trip.id), notification_type_db, idempotency_hash)
            )
            
            if existing_notification.data:
                logger.info("notification_already_sent",
                    trip_id=str(trip.id),
                    notification_type=notification_type,
                    idempotency_hash=idempotency_hash
                )
                return DatabaseResult(success=True, data={"status": "already_sent"})
        except Exception as e:
            logger.warning("idempotency_check_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
            # Continue with send attempt
        
        try:
            # Format message using templates
            message_data = await self.format_message(trip, notification_type, extra_data)
            
            logger.info("sending_whatsapp_notification", 
                trip_id=str(trip.id),
                phone=trip.whatsapp,
                template=message_data["template_name"],
                notification_type=notification_type,
                idempotency_hash=idempotency_hash
            )
            
            # Define send function for retry service
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
            
            # Send with retry logic
            context = {
                "trip_id": str(trip.id),
                "notification_type": notification_type_db,
                "phone": trip.whatsapp
            }
            
            send_result = await self.retry_service.send_with_retry(
                send_func=send_func,
                max_attempts=3,
                context=context
            )
            
            # Log the notification attempt
            await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,
                sent_at=datetime.now(timezone.utc),
                status="SENT" if send_result.success else "FAILED",
                template_name=message_data["template_name"],
                twilio_message_sid=send_result.data.get("message_sid") if send_result.success else None,
                error_message=send_result.error if not send_result.success else None,
                retry_count=0,  # TODO: Track actual retry count
                idempotency_hash=idempotency_hash
            )
            
            if send_result.success:
                logger.info("notification_sent_successfully", 
                    trip_id=str(trip.id),
                    message_sid=send_result.data.get("message_sid"),
                    notification_type=notification_type
                )
            else:
                logger.error("notification_send_failed_final", 
                    trip_id=str(trip.id),
                    error=send_result.error
                )
            
            return send_result
            
        except Exception as e:
            # Log failed attempt
            await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,
                sent_at=datetime.now(timezone.utc),
                status="FAILED",
                template_name=WhatsAppTemplates.get_template_info(notification_type)["name"],
                error_message=str(e),
                idempotency_hash=idempotency_hash
            )
            
            logger.error("notification_send_exception", 
                trip_id=str(trip.id),
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    async def format_message(
        self, 
        trip: Trip, 
        notification_type: NotificationType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Format WhatsApp message using templates.
        
        Args:
            trip: Trip object with flight details
            notification_type: Type of notification
            extra_data: Additional formatting data
            
        Returns:
            Dict with template_sid, template_name and template_variables
        """
        # FIXED: Use human-readable time formatting
        formatted_departure_time = format_departure_time_human(trip.departure_date, trip.origin_iata)
        
        trip_data = {
            "client_name": trip.client_name,
            "flight_number": trip.flight_number,
            "origin_iata": trip.origin_iata,
            "destination_iata": trip.destination_iata,
            "departure_date": trip.departure_date.isoformat(),
            "departure_time": formatted_departure_time,  # Human readable format
            "status": trip.status,
            "metadata": trip.metadata  # Include metadata for hotel info
        }
        
        if extra_data:
            trip_data.update(extra_data)
        
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
    
    def calculate_next_check_time(self, departure_time: datetime, now_utc: datetime) -> datetime:
        """
        Calculate next polling time based on poll optimization rules.
        
        Rules from TC-001:
        - > 24h: +6h
        - 24h-4h: +1h  
        - ≤ 4h: +15min
        - In-flight: +30min
        """
        time_until_departure = departure_time - now_utc
        hours_until = time_until_departure.total_seconds() / 3600
        
        if hours_until > 24:
            return now_utc + timedelta(hours=6)
        elif hours_until > 4:
            return now_utc + timedelta(hours=1)
        elif hours_until > 0:
            return now_utc + timedelta(minutes=15)
        else:
            # In-flight or landed
            return now_utc + timedelta(minutes=30)
    
    async def close(self):
        """Clean up resources."""
        await self.db_client.close()
        logger.info("notifications_agent_closed")

    # TC-003: Free text messaging for ConciergeAgent
    
    async def send_free_text(
        self,
        whatsapp_number: str,
        message: str,
        attachments: Optional[List[str]] = None
    ) -> DatabaseResult:
        """
        Send non-template WhatsApp message using async client with retry.
        
        Args:
            whatsapp_number: Phone number (without whatsapp: prefix)
            message: Free text message to send
            attachments: Optional list of file URLs to attach
            
        Returns:
            DatabaseResult with send status
        """
        try:
            logger.info("sending_free_text_message",
                to_number=whatsapp_number,
                message_length=len(message),
                has_attachments=bool(attachments)
            )
            
            # Define send function for retry service
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
            
            # Send with retry logic
            context = {
                "to_number": whatsapp_number,
                "message_type": "free_text"
            }
            
            send_result = await self.retry_service.send_with_retry(
                send_func=send_func,
                max_attempts=3,
                context=context
            )
            
            # Handle attachments if message sent successfully
            attachments_sent = 0
            if send_result.success and attachments:
                for attachment_url in attachments:
                    try:
                        attachment_result = await self.async_twilio_client.send_media_message(
                            to=f"whatsapp:{whatsapp_number}",
                            messaging_service_sid=self.messaging_service_sid,
                            media_url=attachment_url
                        )
                        
                        if attachment_result.error_code:
                            logger.error("attachment_send_failed",
                                to_number=whatsapp_number,
                                attachment_url=attachment_url,
                                error=f"{attachment_result.error_code}: {attachment_result.error_message}"
                            )
                        else:
                            attachments_sent += 1
                            logger.info("attachment_sent",
                                to_number=whatsapp_number,
                                attachment_url=attachment_url,
                                message_sid=attachment_result.sid
                            )
                    except Exception as e:
                        logger.error("attachment_send_exception",
                            to_number=whatsapp_number,
                            attachment_url=attachment_url,
                            error=str(e)
                        )
            
            if send_result.success:
                logger.info("free_text_sent_successfully",
                    to_number=whatsapp_number,
                    message_sid=send_result.data.get("message_sid"),
                    attachments_sent=attachments_sent
                )
                
                return DatabaseResult(
                    success=True,
                    data={
                        "message_sid": send_result.data.get("message_sid"),
                        "to": whatsapp_number,
                        "attachments_sent": attachments_sent
                    }
                )
            else:
                logger.error("free_text_send_failed",
                    to_number=whatsapp_number,
                    error=send_result.error
                )
                return send_result
            
        except Exception as e:
            logger.error("free_text_send_exception",
                to_number=whatsapp_number,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            )

    def _consolidate_ping_pong_changes(self, changes: List[Dict[str, Any]], trip: Trip) -> List[Dict[str, Any]]:
        """
        Consolidate ping-pong changes within the same polling cycle.
        
        Examples:
        - estimated_out: 02:30 → NULL → 02:30 = No notification (back to original)
        - estimated_out: 02:30 → 03:15 → NULL → 03:15 = Send only final: 02:30 → 03:15
        - gate: A1 → B2 → A1 = No notification (back to original)
        """
        if not changes:
            return changes
        
        logger.info("consolidating_ping_pong_changes", 
            trip_id=str(trip.id),
            original_changes_count=len(changes),
            changes=[f"{c['type']}:{c.get('old_value')}→{c.get('new_value')}" for c in changes]
        )
        
        # Group changes by type
        changes_by_type = {}
        for change in changes:
            change_type = change["type"]
            if change_type not in changes_by_type:
                changes_by_type[change_type] = []
            changes_by_type[change_type].append(change)
        
        consolidated = []
        
        for change_type, type_changes in changes_by_type.items():
            if len(type_changes) == 1:
                # Single change, keep it
                consolidated.append(type_changes[0])
            else:
                # Multiple changes of same type - consolidate
                first_change = type_changes[0]
                last_change = type_changes[-1]
                
                # Check if we're back to the original value (ping-pong)
                if first_change["old_value"] == last_change["new_value"]:
                    logger.info("ping_pong_detected_suppressed", 
                        trip_id=str(trip.id),
                        change_type=change_type,
                        original_value=first_change["old_value"],
                        changes_suppressed=len(type_changes)
                    )
                    # Back to original - suppress all notifications
                    continue
                else:
                    # Net change - send consolidated notification
                    consolidated_change = {
                        "type": change_type,
                        "old_value": first_change["old_value"],
                        "new_value": last_change["new_value"],
                        "notification_type": last_change["notification_type"],
                        "consolidation_count": len(type_changes)
                    }
                    consolidated.append(consolidated_change)
                    
                    logger.info("changes_consolidated", 
                        trip_id=str(trip.id),
                        change_type=change_type,
                        original_count=len(type_changes),
                        final_change=f"{first_change['old_value']}→{last_change['new_value']}"
                    )
        
        logger.info("consolidation_completed", 
            trip_id=str(trip.id),
            original_changes=len(changes),
            consolidated_changes=len(consolidated),
            suppressed_ping_pongs=len(changes) - len(consolidated)
        )
        
        return consolidated 