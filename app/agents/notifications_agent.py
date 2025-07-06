"""NotificationsAgent for Bauhaus Travel - handles flight notifications via WhatsApp."""

import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

from ..db.supabase_client import SupabaseDBClient
from ..models.database import Trip, DatabaseResult
from .notifications_templates import NotificationType, WhatsAppTemplates, get_notification_type_for_status
from ..services.aeroapi_client import AeroAPIClient, FlightStatus
from ..utils.timezone_utils import is_quiet_hours_local

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
        
        # Twilio setup
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_phone = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([account_sid, auth_token, self.twilio_phone]):
            raise ValueError("Missing Twilio credentials in environment variables")
        
        self.twilio_client = TwilioClient(account_sid, auth_token)
        service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
        if not service_sid:
            raise ValueError("Missing TWILIO_MESSAGING_SERVICE_SID")
        self.messaging_service_sid = service_sid
        
        logger.info("notifications_agent_initialized", 
            twilio_phone=self.twilio_phone,
            aeroapi_enabled=self.aeroapi_client.api_key is not None
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
        - Only between 09:00-20:00 local time
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
                
                # Check time window using origin airport timezone
                is_quiet_hours = is_quiet_hours_local(now_utc, trip.origin_iata)
                if is_quiet_hours:
                    logger.info("24h_reminder_outside_window", 
                        trip_id=str(trip.id),
                        origin_iata=trip.origin_iata,
                        local_quiet_hours=True
                    )
                    continue
                
                # Send notification
                result = await self.send_notification(
                    trip=trip,
                    notification_type=NotificationType.REMINDER_24H
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
                    
                    # Save current status to database
                    await self._save_flight_status(trip, current_status)
                    
                    # Process each change and send notifications
                    for change in changes:
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
                        changes_detected=len(changes),
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
        """Get the last known flight status from our database"""
        try:
            # You could store previous status in a new table or use trip fields
            # For now, create a basic status from trip data
            return FlightStatus(
                ident=trip.flight_number,
                status=trip.status or "Scheduled",
                gate_origin=getattr(trip, 'gate', None),  # New field we added
                estimated_out=trip.departure_date.isoformat() if trip.departure_date else None
            )
        except Exception as e:
            logger.error("previous_status_retrieval_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
            return None
    
    async def _save_flight_status(self, trip: Trip, status: FlightStatus):
        """Save current flight status to database"""
        try:
            # Update trip with latest status information
            update_data = {
                "status": status.status,
                "gate": status.gate_origin,  # New field we added in migration
                # You could add more fields like estimated_out, etc.
            }
            
            # Update the trip in database
            await self.db_client.update_trip_status(trip.id, update_data)
            
            logger.info("flight_status_saved", 
                trip_id=str(trip.id),
                status=status.status,
                gate=status.gate_origin
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
        """Process a detected flight change and send appropriate notification"""
        try:
            change_type = change["type"]
            notification_type = change["notification_type"]
            
            # Prepare extra data for template formatting
            extra_data = {
                "old_value": change.get("old_value"),
                "new_value": change.get("new_value"),
                "change_type": change_type
            }
            
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
    
    def _map_notification_type(self, notification_type: str) -> Optional[NotificationType]:
        """Map string notification type to our enum"""
        mapping = {
            "delayed": NotificationType.DELAYED,
            "cancelled": NotificationType.CANCELLED,
            "boarding": NotificationType.BOARDING,
            "gate_change": NotificationType.GATE_CHANGE,
            # Add more mappings as needed
        }
        return mapping.get(notification_type)
    
    async def poll_landed_flights(self) -> DatabaseResult:
        """
        Check for landed flights and send welcome messages.
        """
        logger.info("polling_landed_flights")
        
        # TODO: Implement landing detection logic
        # For now, return success placeholder
        
        return DatabaseResult(
            success=True,
            data={"landed_flights": 0},
            affected_rows=0
        )
    
    async def send_notification(
        self, 
        trip: Trip, 
        notification_type: NotificationType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Send WhatsApp notification using Twilio.
        
        Args:
            trip: Trip object with flight details
            notification_type: Type of notification to send
            extra_data: Additional data for template formatting
            
        Returns:
            DatabaseResult with send status
        """
        # Initialize notification_type_db early for exception handling
        notification_type_db = notification_type.value.upper()
        
        try:
            # Format message using templates
            message_data = self.format_message(trip, notification_type, extra_data)
            
            # Send via Twilio
            logger.info("sending_whatsapp_notification", 
                trip_id=str(trip.id),
                phone=trip.whatsapp,
                template=message_data["template_name"],
                notification_type=notification_type
            )
            
            # Log the full payload to Twilio
            logger.info("twilio_message_payload", 
                from_=self.twilio_phone,
                to=f"whatsapp:{trip.whatsapp}",
                template_sid=message_data["template_sid"],
                content_variables=message_data["template_variables"]
            )

            # Extra: print to always see in console
            print("🚀 TEMPLATE SID:", message_data["template_sid"])
            print("🚀 PAYLOAD A TWILIO:", message_data["template_variables"])

            # Send actual WhatsApp message via Twilio
            message = self.twilio_client.messages.create(
                messaging_service_sid=self.messaging_service_sid,                    # MGxxxxxxxx…
                to=f"whatsapp:{trip.whatsapp}",
                content_sid=message_data["template_sid"],                            # HXb7773214…
                content_variables=json.dumps(message_data["template_variables"])     # string JSON
            )
            message_sid = message.sid

            # Log the notification
            log_result = await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,  # CORRECTO
                sent_at=datetime.now(timezone.utc),
                status="SENT",
                template_name=message_data["template_name"],
                twilio_message_sid=message_sid,
                retry_count=0
            )

            if log_result.success:
                logger.info("notification_sent_successfully", 
                    trip_id=str(trip.id),
                    message_sid=message_sid,
                    notification_type=notification_type
                )
                return DatabaseResult(success=True, data={"message_sid": message_sid})
            else:
                logger.error("notification_log_failed", 
                    trip_id=str(trip.id),
                    error=log_result.error
                )
                return DatabaseResult(success=False, error="Failed to log notification")

        except Exception as e:
            # Log failed attempt
            await self.db_client.log_notification_sent(
                trip_id=str(trip.id),
                notification_type=notification_type_db,  # CORRECTO
                sent_at=datetime.now(timezone.utc),
                status="FAILED",
                template_name=WhatsAppTemplates.get_template_info(notification_type)["name"],
                error_message=str(e)
            )
            
            logger.error("notification_send_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    def format_message(
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
        trip_data = {
            "client_name": trip.client_name,
            "flight_number": trip.flight_number,
            "origin_iata": trip.origin_iata,
            "destination_iata": trip.destination_iata,
            "departure_date": trip.departure_date.isoformat(),
            "status": trip.status
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
        Send non-template WhatsApp message for ConciergeAgent responses.
        
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
            
            # Send simple text message via Twilio
            twilio_message = self.twilio_client.messages.create(
                messaging_service_sid=self.messaging_service_sid,
                to=f"whatsapp:{whatsapp_number}",
                body=message
            )
            message_sid = twilio_message.sid
            
            # If attachments, send them separately
            if attachments:
                for attachment_url in attachments:
                    try:
                        attachment_message = self.twilio_client.messages.create(
                            messaging_service_sid=self.messaging_service_sid,
                            to=f"whatsapp:{whatsapp_number}",
                            media_url=[attachment_url]
                        )
                        logger.info("attachment_sent",
                            to_number=whatsapp_number,
                            attachment_url=attachment_url,
                            message_sid=attachment_message.sid
                        )
                    except Exception as e:
                        logger.error("attachment_send_failed",
                            error_code="ATTACHMENT_SEND_ERROR",
                            to_number=whatsapp_number,
                            attachment_url=attachment_url,
                            error=str(e)
                        )
            
            logger.info("free_text_sent_successfully",
                to_number=whatsapp_number,
                message_sid=message_sid,
                attachments_count=len(attachments) if attachments else 0
            )
            
            return DatabaseResult(
                success=True,
                data={
                    "message_sid": message_sid,
                    "to": whatsapp_number,
                    "attachments_sent": len(attachments) if attachments else 0
                }
            )
            
        except Exception as e:
            logger.error("free_text_send_failed",
                error_code="FREE_TEXT_SEND_ERROR",
                to_number=whatsapp_number,
                error=str(e)
            )
            return DatabaseResult(
                success=False,
                error=str(e)
            ) 