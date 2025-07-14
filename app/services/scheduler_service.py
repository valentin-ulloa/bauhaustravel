"""
APScheduler Service for Bauhaus Travel - Simplified with Unified Utilities
"""

import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from ..agents.notifications_agent import NotificationsAgent
from ..agents.notifications_templates import NotificationType
from ..db.supabase_client import SupabaseDBClient
from ..models.database import Trip
from ..utils.flight_schedule_utils import calculate_unified_next_check

logger = structlog.get_logger()


class SchedulerService:
    """
    SIMPLIFIED scheduler service using unified utilities.
    
    ELIMINATED DUPLICATIONS:
    - Uses calculate_unified_next_check() instead of custom logic
    - Simplified notification scheduling
    - Optimized job management
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.notifications_agent = NotificationsAgent()
        self.db_client = SupabaseDBClient()
        self.is_running = False
        
        logger.info("scheduler_service_initialized", unified_utilities=True)
    
    async def start(self):
        """Start the scheduler with simplified jobs"""
        if self.is_running:
            logger.warning("scheduler_already_running")
            return
        
        try:
            # Job 1: 24h reminders (INTELLIGENT: every hour with local time filtering)
            self.scheduler.add_job(
                self._process_24h_reminders_intelligent,
                IntervalTrigger(hours=1),  # Check every hour, but filter by local time
                id='24h_reminders_intelligent',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 2: INTELLIGENT polling (respects next_check_at times)
            self.scheduler.add_job(
                self._process_intelligent_flight_polling,
                IntervalTrigger(minutes=5),  # ✅ Check DB every 5min but only API call if next_check_at <= now
                id='intelligent_flight_polling',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 3: Boarding notifications (every 5 minutes)
            self.scheduler.add_job(
                self._process_boarding_notifications,
                IntervalTrigger(minutes=5),
                id='boarding_notifications',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 4: Landing detection (every 30 minutes)
            self.scheduler.add_job(
                self._process_landing_detection,
                IntervalTrigger(minutes=30),
                id='landing_detection',
                max_instances=1,
                replace_existing=True
            )
            
            self.scheduler.add_job(
                self._process_deferred_notifications,
                IntervalTrigger(minutes=15),
                id='deferred_notifications',
                max_instances=1,
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info("scheduler_started_unified", 
                jobs_count=len(self.scheduler.get_jobs())
            )
            
        except Exception as e:
            logger.error("scheduler_start_failed", error=str(e))
            raise
    
    async def stop(self):
        """Stop the scheduler gracefully"""
        if not self.is_running:
            return
        
        try:
            self.scheduler.shutdown(wait=True)
            await self.notifications_agent.close()
            await self.db_client.close()
            self.is_running = False
            
            logger.info("scheduler_stopped")
            
        except Exception as e:
            logger.error("scheduler_stop_failed", error=str(e))
    
    async def schedule_immediate_notifications(self, trip: Trip):
        """
        Schedule immediate notifications using SIMPLIFIED logic.
        """
        try:
            now_utc = datetime.now(timezone.utc)
            time_to_departure = trip.departure_date - now_utc
            
            # If departure is within 24 hours, schedule immediate reminder
            if time_to_departure <= timedelta(hours=24):
                job_id = f"immediate_reminder_{trip.id}"
                self.scheduler.add_job(
                    self._send_immediate_reminder,
                    DateTrigger(run_date=now_utc + timedelta(minutes=1)),
                    args=[str(trip.id)],
                    id=job_id,
                    replace_existing=True
                )
                
                logger.info("immediate_reminder_scheduled", trip_id=str(trip.id))
            
            # Schedule boarding notification (35 minutes before departure)
            boarding_time = trip.departure_date - timedelta(minutes=35)
            if boarding_time > now_utc:
                job_id = f"boarding_{trip.id}"
                self.scheduler.add_job(
                    self._send_boarding_notification,
                    DateTrigger(run_date=boarding_time),
                    args=[str(trip.id)],
                    id=job_id,
                    replace_existing=True
                )
                
                logger.info("boarding_notification_scheduled", trip_id=str(trip.id))
            
            # Schedule SIMPLIFIED itinerary generation
            await self._schedule_itinerary_simplified(trip, now_utc, time_to_departure)
                
        except Exception as e:
            logger.error("immediate_scheduling_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
    
    async def _schedule_itinerary_simplified(self, trip: Trip, now_utc: datetime, time_to_departure: timedelta):
        """SIMPLIFIED itinerary scheduling logic."""
        try:
            total_hours = time_to_departure.total_seconds() / 3600
            
            # SIMPLIFIED timing rules
            if total_hours > 30 * 24:      # > 30 days
                delay_minutes = 120
            elif total_hours >= 7 * 24:   # 7-30 days
                delay_minutes = 60
            elif total_hours >= 24:       # 1-7 days
                delay_minutes = 30
            else:                          # < 24 hours
                delay_minutes = 5
            
            itinerary_time = now_utc + timedelta(minutes=delay_minutes)
            job_id = f"itinerary_{trip.id}"
            
            self.scheduler.add_job(
                self._generate_itinerary,
                DateTrigger(run_date=itinerary_time),
                args=[str(trip.id)],
                id=job_id,
                replace_existing=True
            )
            
            logger.info("itinerary_generation_scheduled_simplified",
                trip_id=str(trip.id),
                delay_minutes=delay_minutes
            )
                
        except Exception as e:
            logger.error("itinerary_scheduling_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
    
    async def _process_24h_reminders_intelligent(self):
        """
        Process 24h flight reminders with INTELLIGENT local time filtering.
        
        Only sends reminders when local time at origin airport is 8AM-10PM.
        This prevents notifications at inappropriate local hours globally.
        """
        try:
            now_utc = datetime.now(timezone.utc)
            logger.info("processing_24h_reminders_intelligent", 
                current_utc=now_utc.strftime("%H:%M UTC")
            )
            
            # Get trips that would be in 24h window
            reminder_window_start = now_utc + timedelta(hours=23, minutes=30)
            reminder_window_end = now_utc + timedelta(hours=24, minutes=30)
            
            all_trips = await self.db_client.get_trips_to_poll(reminder_window_end)
            
            candidate_trips = [
                trip for trip in all_trips 
                if reminder_window_start <= trip.departure_date <= reminder_window_end
            ]
            
            valid_trips = []
            skipped_trips = []
            
            # Filter by local time at each trip's origin airport
            for trip in candidate_trips:
                is_valid_local_time = await self._is_valid_local_time_for_reminder(trip, now_utc)
                
                if is_valid_local_time:
                    valid_trips.append(trip)
                else:
                    skipped_trips.append(trip)
            
            logger.info("24h_reminders_intelligent_filtering",
                total_candidates=len(candidate_trips),
                valid_for_sending=len(valid_trips),
                skipped_quiet_hours=len(skipped_trips)
            )
            
            # Process only valid trips using existing agent logic
            if valid_trips:
                # Temporarily override the agent's trip filtering for our pre-filtered list
                result = await self._send_24h_reminders_for_trips(valid_trips)
                
                if result.success:
                    logger.info("24h_reminders_completed_intelligent", 
                        data=result.data,
                        sent_count=result.data.get("sent", 0)
                    )
                else:
                    logger.error("24h_reminders_failed_intelligent", error=result.error)
            else:
                logger.info("24h_reminders_no_valid_trips_intelligent",
                    message="No trips in valid local time window"
                )
                
        except Exception as e:
            logger.error("24h_reminders_intelligent_exception", error=str(e))
    
    async def _is_valid_local_time_for_reminder(self, trip, now_utc: datetime) -> bool:
        """
        Check if current time is valid for sending 24h reminder based on origin airport local time.
        
        Args:
            trip: Trip object with origin_iata
            now_utc: Current UTC time
            
        Returns:
            True if local time at origin is 8 AM - 10 PM, False otherwise
        """
        try:
            from ..utils.timezone_utils import convert_utc_to_local_time
            
            # Convert UTC to local time at origin airport
            local_time = convert_utc_to_local_time(now_utc, trip.origin_iata)
            
            # Valid window: 8 AM - 10 PM local time
            is_valid = 8 <= local_time.hour < 22
            
            logger.debug("local_time_validation",
                trip_id=str(trip.id),
                origin_iata=trip.origin_iata,
                utc_time=now_utc.strftime("%H:%M UTC"),
                local_time=local_time.strftime("%H:%M %Z"),
                local_hour=local_time.hour,
                is_valid=is_valid
            )
            
            return is_valid
            
        except Exception as e:
            logger.warning("local_time_validation_failed",
                trip_id=str(trip.id),
                origin_iata=trip.origin_iata,
                error=str(e),
                fallback="allowing_reminder"
            )
            # Fallback: allow sending if timezone conversion fails
            return True
    
    async def _send_24h_reminders_for_trips(self, trips_list):
        """
        Send 24h reminders for a pre-filtered list of trips.
        
        This bypasses the agent's own filtering since we've already done
        intelligent local time filtering.
        """
        try:
            from ..agents.notifications_templates import NotificationType
            from ..utils.flight_schedule_utils import should_suppress_notification_unified
            
            now_utc = datetime.now(timezone.utc)
            success_count = 0
            
            for trip in trips_list:
                # Check if reminder already sent
                history = await self.db_client.get_notification_history(
                    trip.id, NotificationType.REMINDER_24H.value.upper()
                )
                
                if any(log.delivery_status == "SENT" for log in history):
                    logger.info("24h_reminder_already_sent", trip_id=str(trip.id))
                    continue
                
                # Double-check quiet hours using existing unified logic
                should_suppress = should_suppress_notification_unified(
                    "REMINDER_24H", now_utc, trip.origin_iata
                )
                if should_suppress:
                    logger.info("24h_reminder_suppressed_quiet_hours_fallback", 
                        trip_id=str(trip.id),
                        origin_iata=trip.origin_iata
                    )
                    continue
                
                # Send reminder using notifications agent
                result = await self.notifications_agent.send_notification(
                    trip=trip,
                    notification_type=NotificationType.REMINDER_24H,
                    extra_data=await self.notifications_agent._get_dynamic_reminder_data(trip)
                )
                
                if result.success:
                    success_count += 1
                    logger.info("24h_reminder_sent_intelligent", 
                        trip_id=str(trip.id),
                        flight_number=trip.flight_number
                    )
            
            return type('Result', (), {
                'success': True, 
                'data': {"sent": success_count}
            })()
            
        except Exception as e:
            logger.error("send_24h_reminders_for_trips_failed", error=str(e))
            return type('Result', (), {
                'success': False, 
                'error': str(e)
            })()
    
    async def _process_intelligent_flight_polling(self):
        """
        CONSOLIDATED flight polling - delegates to NotificationsAgent.
        
        FIXES: Eliminates race condition by having single entry point.
        """
        try:
            logger.info("intelligent_polling_delegating_to_notifications_agent")
            
            # SINGLE ENTRY POINT: Use NotificationsAgent.poll_flight_changes()
            result = await self.notifications_agent.poll_flight_changes()
            
            if result.success:
                logger.info("intelligent_polling_completed_via_agent", 
                    data=result.data
                )
            else:
                logger.error("intelligent_polling_failed_via_agent", 
                    error=result.error
                )
                
        except Exception as e:
            logger.error("intelligent_polling_exception", error=str(e))
    
    async def _process_boarding_notifications(self):
        """SIMPLIFIED boarding notifications check."""
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Get trips with departure in next 30-40 minutes (adjusted for 35min scheduling)
            start_window = now_utc + timedelta(minutes=30)
            end_window = now_utc + timedelta(minutes=40)
            
            all_trips = await self.db_client.get_trips_to_poll(end_window)
            boarding_trips = [
                trip for trip in all_trips 
                if start_window <= trip.departure_date <= end_window
            ]
            
            for trip in boarding_trips:
                # Check if boarding notification already sent
                history = await self.db_client.get_notification_history(
                    trip.id, "BOARDING"
                )
                
                if any(log.delivery_status == "SENT" for log in history):
                    continue
                
                # Send boarding notification using unified agent
                result = await self.notifications_agent.send_single_notification(
                    trip.id, 
                    NotificationType.BOARDING
                )
                
                if result.success:
                    logger.info("boarding_notification_sent", trip_id=str(trip.id))
                
        except Exception as e:
            logger.error("boarding_notifications_exception", error=str(e))
    
    async def _process_landing_detection(self):
        """Process landing detection using unified agent."""
        try:
            logger.info("processing_landing_detection")
            result = await self.notifications_agent.run("landing_detected")
            
            if result.success:
                logger.info("landing_detection_completed", data=result.data)
            else:
                logger.error("landing_detection_failed", error=result.error)
                
        except Exception as e:
            logger.error("landing_detection_exception", error=str(e))
    
    async def _process_deferred_notifications(self):
        now_utc = datetime.now(timezone.utc)
        pending = await self.db_client.get_pending_deferred(now_utc)
        for log in pending:
            trip = await self.db_client.get_trip_by_id(log['trip_id'])
            if trip:
                result = await self.notifications_agent.send_notification(trip, log['notification_type'], log.get('extra_data'))
                status = 'SENT' if result.success else 'FAILED'
                await self.db_client.update_notification_status(log['id'], status, result.error)
    
    async def _send_immediate_reminder(self, trip_id: str):
        """Send immediate 24h reminder using unified agent."""
        try:
            result = await self.notifications_agent.send_single_notification(
                trip_id, 
                NotificationType.REMINDER_24H,
                extra_data={"urgent": True}
            )
            
            if result.success:
                logger.info("immediate_reminder_sent", trip_id=trip_id)
            else:
                logger.error("immediate_reminder_failed", 
                    trip_id=trip_id, 
                    error=result.error
                )
                
        except Exception as e:
            logger.error("immediate_reminder_exception", 
                trip_id=trip_id, 
                error=str(e)
            )
    
    async def _send_boarding_notification(self, trip_id: str):
        """Send boarding notification using unified agent."""
        try:
            result = await self.notifications_agent.send_single_notification(
                trip_id,
                NotificationType.BOARDING
            )
            
            if result.success:
                logger.info("boarding_notification_sent", trip_id=trip_id)
            else:
                logger.error("boarding_notification_failed", 
                    trip_id=trip_id, 
                    error=result.error
                )
                
        except Exception as e:
            logger.error("boarding_notification_exception", 
                trip_id=trip_id, 
                error=str(e)
            )
    
    async def _generate_itinerary(self, trip_id: str):
        """Generate itinerary using existing ItineraryAgent."""
        try:
            from ..agents.itinerary_agent import ItineraryAgent
            
            logger.info("scheduled_itinerary_generation_started", trip_id=trip_id)
            
            itinerary_agent = ItineraryAgent()
            result = await itinerary_agent.run(trip_id)
            
            if result.success:
                logger.info("scheduled_itinerary_generated_successfully", 
                    trip_id=trip_id,
                    itinerary_id=result.data.get("itinerary_id")
                )
            else:
                logger.error("scheduled_itinerary_generation_failed", 
                    trip_id=trip_id,
                    error=result.error
                )
            
            await itinerary_agent.close()
                
        except Exception as e:
            logger.error("scheduled_itinerary_generation_exception", 
                trip_id=trip_id, 
                error=str(e)
            )
    
    def get_job_status(self) -> dict:
        """Get current status of all scheduled jobs."""
        if not self.is_running:
            return {"status": "stopped", "jobs": []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name or job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "status": "running",
            "jobs_count": len(jobs),
            "jobs": jobs,
            "unified_architecture": True
        } 