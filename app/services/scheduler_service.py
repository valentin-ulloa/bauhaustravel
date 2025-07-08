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
            # Job 1: 24h reminders (daily at 9 AM UTC)
            self.scheduler.add_job(
                self._process_24h_reminders,
                CronTrigger(hour=9, minute=0),
                id='24h_reminders',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 2: UNIFIED intelligent polling (every 5 minutes)
            self.scheduler.add_job(
                self._process_unified_flight_polling,
                IntervalTrigger(minutes=5),
                id='unified_flight_polling',
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
            
            # Schedule boarding notification (40 minutes before departure)
            boarding_time = trip.departure_date - timedelta(minutes=40)
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
    
    async def _process_24h_reminders(self):
        """Process 24h flight reminders using unified agent."""
        try:
            logger.info("processing_24h_reminders")
            result = await self.notifications_agent.run("24h_reminder")
            
            if result.success:
                logger.info("24h_reminders_completed", data=result.data)
            else:
                logger.error("24h_reminders_failed", error=result.error)
                
        except Exception as e:
            logger.error("24h_reminders_exception", error=str(e))
    
    async def _process_unified_flight_polling(self):
        """
        UNIFIED flight polling using calculate_unified_next_check().
        
        ELIMINATES duplication with NotificationsAgent.
        """
        try:
            now_utc = datetime.now(timezone.utc)
            
            logger.info("unified_polling_check", current_time=now_utc.isoformat())
            
            # Get trips that need polling
            trips_to_poll = await self.db_client.get_trips_to_poll(now_utc)
            
            if not trips_to_poll:
                logger.info("unified_polling_no_trips_ready")
                return
            
            logger.info("unified_polling_processing_trips", 
                trips_count=len(trips_to_poll)
            )
            
            processed_count = 0
            for trip in trips_to_poll:
                try:
                    # Use unified agent check
                    result = await self.notifications_agent.check_single_trip_status(trip)
                    
                    if result.success:
                        processed_count += 1
                        
                        # UNIFIED next_check_at calculation
                        next_check = calculate_unified_next_check(
                            departure_time=trip.departure_date,
                            now_utc=now_utc,
                            current_status=result.data.get("current_status", "UNKNOWN")
                        )
                        
                        if next_check:
                            await self.db_client.update_next_check_at(trip.id, next_check)
                        
                        logger.info("unified_polling_trip_processed", 
                            trip_id=str(trip.id),
                            next_check=next_check.isoformat() if next_check else "no_more_polling"
                        )
                    else:
                        logger.warning("unified_polling_trip_failed", 
                            trip_id=str(trip.id),
                            error=result.error
                        )
                        
                        # On error, use unified calculation with fallback
                        next_check = calculate_unified_next_check(
                            trip.departure_date, now_utc, "ERROR"
                        )
                        if next_check:
                            await self.db_client.update_next_check_at(trip.id, next_check)
                        
                except Exception as trip_error:
                    logger.error("unified_polling_trip_exception", 
                        trip_id=str(trip.id),
                        error=str(trip_error)
                    )
                    
                    # On exception, use unified calculation
                    next_check = calculate_unified_next_check(
                        trip.departure_date, now_utc, "EXCEPTION"
                    )
                    if next_check:
                        await self.db_client.update_next_check_at(trip.id, next_check)
            
            logger.info("unified_polling_completed", 
                processed_count=processed_count,
                total_trips=len(trips_to_poll)
            )
                
        except Exception as e:
            logger.error("unified_polling_exception", error=str(e))
    
    async def _process_boarding_notifications(self):
        """SIMPLIFIED boarding notifications check."""
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Get trips with departure in next 35-45 minutes
            start_window = now_utc + timedelta(minutes=35)
            end_window = now_utc + timedelta(minutes=45)
            
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