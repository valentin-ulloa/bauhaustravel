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
                    # CREATIVE SKIP CHECK: Auto-detected problematic flights
                    trip_metadata = getattr(trip, 'metadata', {}) or {}
                    if trip_metadata.get('skip_polling', False):
                        logger.info("skipping_problematic_flight", 
                            trip_id=str(trip.id),
                            flight_number=trip.flight_number,
                            reason="auto_detected_aeroapi_failure",
                            api_failures=trip_metadata.get('api_failures', 0)
                        )
                        success_count += 1  # Count as processed
                        continue
                    
                    # Get current status with INTELLIGENT CACHING
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    current_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if not current_status:
                        # AUTO-DETECTION: Increment failure count for problematic flights
                        trip_metadata = getattr(trip, 'metadata', {}) or {}
                        failure_count = trip_metadata.get('api_failures', 0) + 1
                        trip_metadata['api_failures'] = failure_count
                        trip_metadata['last_failure'] = now_utc.isoformat()
                        
                        # Auto-skip after 3 failures
                        if failure_count >= 3:
                            trip_metadata['skip_polling'] = True
                            trip_metadata['reason'] = "auto_detected_aeroapi_failure"
                            logger.warning("auto_marking_flight_for_skip", 
                                trip_id=str(trip.id),
                                flight_number=trip.flight_number,
                                failure_count=failure_count
                            )
                        
                        await self.db_client.update_trip_status(trip.id, {"metadata": trip_metadata})
                        
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
                    
                    # INTELLIGENT arrival calculation using cascading fallback logic
                    from app.utils.flight_schedule_utils import calculate_intelligent_arrival_time
                    
                    estimated_arrival = calculate_intelligent_arrival_time(
                        departure_time=departure_time,
                        current_status=current_status,
                        trip_metadata=trip.metadata
                    )
                    
                    # Fallback to database if intelligent calculation fails
                    if not estimated_arrival and hasattr(trip, 'estimated_arrival') and trip.estimated_arrival:
                        estimated_arrival = trip.estimated_arrival
                        logger.debug("using_database_estimated_arrival_ultimate_fallback", 
                            trip_id=str(trip.id),
                            estimated_arrival=estimated_arrival.isoformat()
                        )
                    
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
        """Save flight status with OPTIMIZED database updates and COMPLETE raw data preservation."""
        try:
            flight_date = trip.departure_date.strftime("%Y-%m-%d")
            
            # ENHANCED: Create raw_data with COMPLETE AeroAPI response preservation
            raw_data = {
                # Structured fields for quick access
                "ident": status.ident,
                "status": status.status,
                "estimated_out": status.estimated_out,
                "estimated_in": status.estimated_in,
                "actual_out": status.actual_out,
                "actual_in": status.actual_in,
                "gate_origin": status.gate_origin,
                "gate_destination": status.gate_destination,
                "departure_delay": status.departure_delay,
                "arrival_delay": status.arrival_delay,
                "cancelled": status.cancelled,
                "diverted": status.diverted,
                "origin_iata": status.origin_iata,
                "destination_iata": status.destination_iata,
                "aircraft_type": status.aircraft_type,
                "progress_percent": status.progress_percent,
                # Extended fields for complete data preservation
                "scheduled_out": status.scheduled_out,
                "scheduled_in": status.scheduled_in,
                "scheduled_block_time_minutes": status.scheduled_block_time_minutes,
                "filed_ete": status.filed_ete,
                # COMPLETE AeroAPI response (the FULL JSON!)
                "complete_aeroapi_response": getattr(status, 'raw_aeroapi_response', None),
                # Metadata for traceability
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "source": "notifications_agent_optimized"
            }
            
            # Save to history with COMPLETE raw data
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
                raw_data=raw_data,  # ← COMPLETE DATA STORED HERE
                source="unified_polling"
            )
            
            # Update trip with comprehensive data (structured fields for quick access)
            await self.db_client.update_trip_comprehensive(trip.id, status, update_metadata=True)
            
            logger.info("flight_status_saved_with_complete_data", 
                trip_id=str(trip.id),
                raw_data_fields=len(raw_data),
                structured_metadata_updated=True
            )
            
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
            # ROBUST time parsing to avoid "Por confirmar" issues
            new_time = change["new_value"]
            formatted_time = "Por confirmar"
            
            if new_time:
                # Try multiple parsing strategies
                parsed_dt = None
                
                # Strategy 1: Standard ISO format with Z
                try:
                    if new_time.endswith('Z'):
                        parsed_dt = datetime.fromisoformat(new_time.replace('Z', '+00:00'))
                    elif '+' in new_time or new_time.count('-') >= 3:  # Has timezone
                        parsed_dt = datetime.fromisoformat(new_time)
                    elif 'T' in new_time:  # ISO format without timezone
                        parsed_dt = datetime.fromisoformat(new_time).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
                
                # Strategy 2: Try parsing as timestamp if ISO failed
                if not parsed_dt and new_time.isdigit():
                    try:
                        parsed_dt = datetime.fromtimestamp(int(new_time), timezone.utc)
                    except (ValueError, OSError):
                        pass
                
                # If we successfully parsed, format it properly
                if parsed_dt:
                    try:
                        formatted_time = format_departure_time_human(parsed_dt, trip.origin_iata)
                        logger.info("successful_time_parsing", 
                            trip_id=str(trip.id),
                            raw_time=new_time,
                            formatted_time=formatted_time
                        )
                    except Exception as e:
                        logger.warning("time_formatting_failed", 
                            trip_id=str(trip.id),
                            raw_time=new_time,
                            error=str(e)
                        )
                else:
                    logger.warning("time_parsing_failed_all_strategies", 
                        trip_id=str(trip.id),
                        raw_time=new_time,
                        fallback="Por confirmar"
                    )
            
            extra_data["new_departure_time"] = formatted_time
                
        elif notification_type == "boarding":
            # CRITICAL FIX: Always fetch fresh gate data before boarding notification
            gate_info = None
            
            # 1. Check if trip.gate already has value
            trip_gate = getattr(trip, 'gate', None)
            if trip_gate and trip_gate.strip():
                gate_info = trip_gate
                logger.info("using_existing_gate_from_db", 
                    trip_id=str(trip.id), 
                    gate=gate_info
                )
            else:
                # 2. No gate in DB - fetch fresh from AeroAPI
                logger.info("fetching_fresh_gate_from_aeroapi", 
                    trip_id=str(trip.id),
                    reason="trip.gate is empty"
                )
                
                try:
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    fresh_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if fresh_status:
                        # CRITICAL FIX: Always update trip comprehensively with fresh AeroAPI data
                        update_result = await self.db_client.update_trip_comprehensive(
                            trip.id, 
                            fresh_status,
                            update_metadata=True
                        )
                        
                        if fresh_status.gate_origin:
                            gate_info = fresh_status.gate_origin
                            logger.info("updated_gate_from_aeroapi", 
                                trip_id=str(trip.id),
                                new_gate=gate_info,
                                flight_number=trip.flight_number
                            )
                        
                        if update_result.success:
                            logger.info("trip_metadata_updated_during_boarding", 
                                trip_id=str(trip.id),
                                flight_number=trip.flight_number
                            )
                    else:
                        logger.warning("no_gate_available_from_aeroapi", 
                            trip_id=str(trip.id),
                            flight_number=trip.flight_number
                        )
                        
                except Exception as e:
                    logger.error("aeroapi_fetch_failed_for_boarding", 
                        trip_id=str(trip.id),
                        error=str(e)
                    )
            
            # 4. Final fallback if no gate available anywhere
            if not gate_info:
                gate_info = "Ver pantallas del aeropuerto"
                logger.warning("using_fallback_gate_message", 
                    trip_id=str(trip.id),
                    flight_number=trip.flight_number,
                    reason="no gate available from DB or AeroAPI - airline has not assigned gate yet"
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
        
        # ENHANCED idempotency hash - includes content to prevent duplicates with different content
        current_time = datetime.now(timezone.utc)
        
        # Include extra_data content for true uniqueness
        content_hash = ""
        if extra_data:
            # Sort and hash the actual content to detect changes
            content_hash = hashlib.sha256(
                json.dumps(extra_data, sort_keys=True).encode()
            ).hexdigest()[:8]
        
        idempotency_data = {
            "trip_id": str(trip.id),
            "notification_type": notification_type_db,
            "date": current_time.strftime("%Y-%m-%d"),
            "hour": current_time.strftime("%H"),  # Hour-level uniqueness
            "content_hash": content_hash  # Content-based uniqueness
        }
        idempotency_hash = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # Check if notification already sent (enhanced with cooldown)
        try:
            # Check for exact duplicate (same idempotency hash)
            duplicate_check = await self.db_client.execute_query(
                """
                SELECT id FROM notifications_log 
                WHERE trip_id = %s AND notification_type = %s AND idempotency_hash = %s 
                AND delivery_status = 'SENT'
                LIMIT 1
                """,
                (str(trip.id), notification_type_db, idempotency_hash)
            )
            
            if duplicate_check.data:
                return DatabaseResult(success=True, data={"status": "already_sent_exact_duplicate"})
            
            # COOLDOWN CHECK: Prevent notifications of same type within 5 minutes
            cooldown_check = await self.db_client.execute_query(
                """
                SELECT id FROM notifications_log 
                WHERE trip_id = %s AND notification_type = %s 
                AND delivery_status = 'SENT'
                AND sent_at > %s
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (str(trip.id), notification_type_db, (current_time - timedelta(minutes=5)).isoformat())
            )
            
            if cooldown_check.data:
                logger.warning("notification_blocked_by_cooldown", 
                    trip_id=str(trip.id),
                    notification_type=notification_type_db,
                    cooldown_minutes=5
                )
                return DatabaseResult(success=True, data={"status": "blocked_by_cooldown"})
                
        except Exception as e:
            logger.warning("idempotency_check_failed", error=str(e))
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
            gate = extra_data.get("gate", "Ver pantallas del aeropuerto") if extra_data else "Ver pantallas del aeropuerto"
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
        """
        Send a single notification for a specific trip.
        
        CRITICAL FIX: For boarding notifications, ALWAYS verify AeroAPI first
        to ensure we have the latest gate information before sending.
        """
        try:
            trip_result = await self.db_client.get_trip_by_id(trip_id)
            if not trip_result.success or not trip_result.data:
                return DatabaseResult(success=False, error=f"Trip {trip_id} not found")
            
            trip = Trip(**trip_result.data)
            
            # CRITICAL FIX: For boarding notifications, fetch fresh data from AeroAPI first
            if notification_type == NotificationType.BOARDING:
                logger.info("boarding_notification_triggered_aeroapi_check", 
                    trip_id=str(trip.id),
                    flight_number=trip.flight_number
                )
                
                enhanced_extra_data = await self._prepare_boarding_notification_data(trip, extra_data)
                return await self.send_notification(trip, notification_type, enhanced_extra_data)
            else:
                return await self.send_notification(trip, notification_type, extra_data)
            
        except Exception as e:
            return DatabaseResult(success=False, error=str(e))
    
    async def _prepare_boarding_notification_data(
        self, 
        trip: Trip, 
        existing_extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Prepare boarding notification data with COMPLETE gate verification logic.
        
        BUSINESS LOGIC (as specified by user):
        1. Check if trip.gate field has value
        2. If empty, check metadata for gate information  
        3. If neither has gate info, fetch fresh from AeroAPI and update
        4. Only use "Ver pantallas del aeropuerto" if gate still empty after AeroAPI
        """
        extra_data = existing_extra_data.copy() if existing_extra_data else {}
        gate_info = None
        
        # STEP 1: Check if trip.gate field has value
        trip_gate = getattr(trip, 'gate', None)
        if trip_gate and trip_gate.strip():
            gate_info = trip_gate
            logger.info("using_gate_from_trip_field", 
                trip_id=str(trip.id), 
                gate=gate_info,
                source="trip.gate_field"
            )
        else:
            # STEP 2: trip.gate is empty - check metadata for gate information
            logger.info("trip_gate_field_empty_checking_metadata", 
                trip_id=str(trip.id),
                flight_number=trip.flight_number
            )
            
            metadata = getattr(trip, 'metadata', {}) or {}
            
            # Check various metadata fields where gate info might be stored
            metadata_gate_fields = [
                'gate_origin', 'gate', 'departure_gate', 
                'terminal_gate', 'boarding_gate'
            ]
            
            for field in metadata_gate_fields:
                if metadata.get(field) and str(metadata[field]).strip():
                    gate_info = str(metadata[field]).strip()
                    logger.info("using_gate_from_metadata", 
                        trip_id=str(trip.id),
                        gate=gate_info,
                        source=f"metadata.{field}"
                    )
                    break
            
            # STEP 3: Neither trip.gate nor metadata has gate info - fetch from AeroAPI
            if not gate_info:
                logger.info("no_gate_in_db_or_metadata_fetching_aeroapi", 
                    trip_id=str(trip.id),
                    flight_number=trip.flight_number,
                    reason="Both trip.gate and metadata empty, checking AeroAPI"
                )
                
                try:
                    departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                    fresh_status = await self.aeroapi_client.get_flight_status(
                        trip.flight_number, 
                        departure_date_str
                    )
                    
                    if fresh_status:
                        # Update trip comprehensively with fresh AeroAPI data
                        update_result = await self.db_client.update_trip_comprehensive(
                            trip.id, 
                            fresh_status,
                            update_metadata=True
                        )
                        
                        if fresh_status.gate_origin:
                            gate_info = fresh_status.gate_origin
                            logger.info("gate_found_and_updated_from_aeroapi", 
                                trip_id=str(trip.id),
                                new_gate=gate_info,
                                flight_number=trip.flight_number,
                                success="AVOIDED generic message through AeroAPI"
                            )
                        else:
                            logger.info("aeroapi_called_but_no_gate_assigned", 
                                trip_id=str(trip.id),
                                flight_number=trip.flight_number,
                                aeroapi_status=fresh_status.status,
                                message="Airline has not assigned gate yet"
                            )
                        
                        if update_result.success:
                            logger.info("trip_updated_with_fresh_aeroapi_data", 
                                trip_id=str(trip.id),
                                flight_number=trip.flight_number
                            )
                    else:
                        logger.warning("aeroapi_returned_no_flight_data", 
                            trip_id=str(trip.id),
                            flight_number=trip.flight_number,
                            departure_date=departure_date_str
                        )
                        
                except Exception as e:
                    logger.error("aeroapi_fetch_failed_during_boarding_prep", 
                        trip_id=str(trip.id),
                        flight_number=trip.flight_number,
                        error=str(e)
                    )
        
        # STEP 4: Final fallback only if gate still empty after all checks
        if not gate_info:
            gate_info = "Ver pantallas del aeropuerto"
            logger.warning("using_fallback_message_after_complete_verification", 
                trip_id=str(trip.id),
                flight_number=trip.flight_number,
                reason="No gate found in: trip.gate, metadata, or AeroAPI - airline has not assigned gate"
            )
        
        extra_data["gate"] = gate_info
        
        # Log the complete verification path for debugging
        logger.info("boarding_gate_verification_completed", 
            trip_id=str(trip.id),
            final_gate=gate_info,
            is_specific_gate=gate_info != "Ver pantallas del aeropuerto"
        )
        
        return extra_data
    
    # REMOVED: check_single_trip_status() method to eliminate race condition
    # All polling now goes through poll_flight_changes() for single entry point
    
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