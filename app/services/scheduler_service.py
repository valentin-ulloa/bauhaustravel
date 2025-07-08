"""
APScheduler Service for Bauhaus Travel - Automated Flight Monitoring
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

logger = structlog.get_logger()


class SchedulerService:
    """
    Manages automated scheduling for flight monitoring and notifications.
    
    Handles:
    - 24h reminders (daily check at 9 AM)
    - Flight status polling (every 15 minutes)
    - Boarding notifications (40 minutes before estimated departure)
    - Immediate notifications for last-minute trips
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.notifications_agent = NotificationsAgent()
        self.db_client = SupabaseDBClient()
        self.is_running = False
        
        logger.info("scheduler_service_initialized")
    
    async def start(self):
        """Start the scheduler with all jobs"""
        if self.is_running:
            logger.warning("scheduler_already_running")
            return
        
        try:
            # Job 1: 24h reminders (daily at 9 AM UTC)
            self.scheduler.add_job(
                self._process_24h_reminders,
                CronTrigger(hour=9, minute=0),  # 9:00 AM UTC daily
                id='24h_reminders',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 2: INTELLIGENT flight status polling (every 5 minutes, checks next_check_at)
            self.scheduler.add_job(
                self._process_intelligent_flight_polling,
                IntervalTrigger(minutes=5),  # Check every 5 minutes but only poll when needed
                id='intelligent_flight_polling',
                max_instances=1,
                replace_existing=True
            )
            
            # Job 3: Boarding notifications check (every 5 minutes for precision)
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
            
            logger.info("scheduler_started", 
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
        Schedule immediate notifications for trips created within 24h of departure.
        
        Args:
            trip: Trip object for immediate processing
        """
        try:
            now_utc = datetime.now(timezone.utc)
            time_to_departure = trip.departure_date - now_utc
            
            # If departure is within 24 hours, schedule immediate reminder
            if time_to_departure <= timedelta(hours=24):
                
                # Send 24h reminder immediately (for last-minute trips)
                job_id = f"immediate_reminder_{trip.id}"
                self.scheduler.add_job(
                    self._send_immediate_reminder,
                    DateTrigger(run_date=now_utc + timedelta(minutes=1)),  # 1 minute delay
                    args=[str(trip.id)],  # Convert UUID to string
                    id=job_id,
                    replace_existing=True
                )
                
                logger.info("immediate_reminder_scheduled", 
                    trip_id=str(trip.id),
                    time_to_departure=str(time_to_departure)
                )
            
            # Schedule boarding notification (40 minutes before estimated departure)
            boarding_time = trip.departure_date - timedelta(minutes=40)
            if boarding_time > now_utc:
                job_id = f"boarding_{trip.id}"
                self.scheduler.add_job(
                    self._send_boarding_notification,
                    DateTrigger(run_date=boarding_time),
                    args=[str(trip.id)],  # Convert UUID to string
                    id=job_id,
                    replace_existing=True
                )
                
                logger.info("boarding_notification_scheduled",
                    trip_id=str(trip.id),
                    boarding_time=boarding_time.isoformat()
                )
            
            # Schedule intelligent itinerary generation
            await self.schedule_itinerary_generation(trip, now_utc, time_to_departure)
                
        except Exception as e:
            logger.error("immediate_scheduling_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
    
    async def schedule_itinerary_generation(self, trip: Trip, now_utc: datetime, time_to_departure: timedelta):
        """
        Schedule intelligent itinerary generation based on time until departure.
        
        Timing strategy:
        - > 30 days: 2 hours after confirmation
        - 7-30 days: 1 hour after confirmation  
        - < 7 days: 30 minutes after confirmation
        - < 24h: Immediately (5 minutes after confirmation)
        
        Args:
            trip: Trip object
            now_utc: Current UTC time
            time_to_departure: Time remaining until departure
        """
        try:
            # Determine delay based on time to departure (using total hours for accuracy)
            total_hours = time_to_departure.total_seconds() / 3600
            
            if total_hours > 30 * 24:  # > 30 days
                delay_minutes = 120  # 2 hours
            elif total_hours >= 7 * 24:  # 7-30 days
                delay_minutes = 60   # 1 hour
            elif total_hours >= 24:  # 1-7 days
                delay_minutes = 30   # 30 minutes
            else:  # < 24 hours
                delay_minutes = 5    # 5 minutes for last-minute trips
            
            # Schedule itinerary generation
            itinerary_time = now_utc + timedelta(minutes=delay_minutes)
            job_id = f"itinerary_{trip.id}"
            
            self.scheduler.add_job(
                self._generate_itinerary,
                DateTrigger(run_date=itinerary_time),
                args=[str(trip.id)],
                id=job_id,
                replace_existing=True
            )
            
            logger.info("itinerary_generation_scheduled",
                trip_id=str(trip.id),
                delay_minutes=delay_minutes,
                generation_time=itinerary_time.isoformat(),
                hours_to_departure=round(total_hours, 2),
                timing_category=f"{'< 24h' if total_hours < 24 else f'{int(total_hours/24)} days'}"
            )
                
        except Exception as e:
            logger.error("itinerary_scheduling_failed", 
                trip_id=str(trip.id), 
                error=str(e)
            )
    
    async def _process_24h_reminders(self):
        """Process 24h flight reminders (daily job)"""
        try:
            logger.info("processing_24h_reminders")
            result = await self.notifications_agent.run("24h_reminder")
            
            if result.success:
                logger.info("24h_reminders_completed", data=result.data)
            else:
                logger.error("24h_reminders_failed", error=result.error)
                
        except Exception as e:
            logger.error("24h_reminders_exception", error=str(e))
    
    async def _process_intelligent_flight_polling(self):
        """
        INTELLIGENT flight status polling - only polls when next_check_at indicates it's time.
        
        This replaces the old every-15-minutes polling to reduce AeroAPI costs.
        Logic:
        1. Check trips where next_check_at <= now
        2. Poll only those flights
        3. Update next_check_at based on flight status:
           - Pre-departure: next_check_at = departure_time - 2h  
           - Departed: next_check_at = estimated_landing_time
           - Landed: Remove from polling
        """
        try:
            now_utc = datetime.now(timezone.utc)
            
            logger.info("intelligent_polling_check", 
                current_time=now_utc.isoformat()
            )
            
            # Get trips that need polling (next_check_at <= now)
            trips_to_poll = await self.db_client.get_trips_to_poll(now_utc)
            
            if not trips_to_poll:
                logger.info("intelligent_polling_no_trips_ready")
                return
            
            logger.info("intelligent_polling_processing_trips", 
                trips_count=len(trips_to_poll),
                trip_ids=[str(trip.id) for trip in trips_to_poll]
            )
            
            # Process each trip with intelligent next_check_at logic
            processed_count = 0
            for trip in trips_to_poll:
                try:
                    # Run status change check for this specific trip
                    result = await self.notifications_agent.check_single_trip_status(trip)
                    
                    if result.success:
                        processed_count += 1
                        
                        # INTELLIGENT NEXT_CHECK_AT LOGIC
                        await self._update_intelligent_next_check(trip, now_utc)
                        
                        logger.info("intelligent_polling_trip_processed", 
                            trip_id=str(trip.id),
                            flight_number=trip.flight_number
                        )
                    else:
                        logger.warning("intelligent_polling_trip_failed", 
                            trip_id=str(trip.id),
                            error=result.error
                        )
                        
                        # On error, retry in 30 minutes
                        next_check = now_utc + timedelta(minutes=30)
                        await self.db_client.update_next_check_at(trip.id, next_check)
                        
                except Exception as trip_error:
                    logger.error("intelligent_polling_trip_exception", 
                        trip_id=str(trip.id),
                        error=str(trip_error)
                    )
                    
                    # On exception, retry in 1 hour
                    next_check = now_utc + timedelta(hours=1)
                    await self.db_client.update_next_check_at(trip.id, next_check)
            
            logger.info("intelligent_polling_completed", 
                processed_count=processed_count,
                total_trips=len(trips_to_poll)
            )
                
        except Exception as e:
            logger.error("intelligent_polling_exception", error=str(e))
    
    async def _update_intelligent_next_check(self, trip: Trip, now_utc: datetime):
        """
        Update next_check_at based on intelligent flight status logic.
        
        Logic:
        - Pre-departure (>2h): next_check_at = departure_time - 2h
        - Pre-departure (<2h): next_check_at = departure_time - 30min  
        - Departed: next_check_at = estimated_landing_time
        - Landed: next_check_at = None (remove from polling)
        """
        try:
            time_to_departure = trip.departure_date - now_utc
            hours_to_departure = time_to_departure.total_seconds() / 3600
            
            # Get current flight status to determine state
            from ..services.aeroapi_client import AeroAPIClient
            aeroapi_client = AeroAPIClient()
            flight_date_str = trip.departure_date.strftime("%Y-%m-%d")
            current_status = await aeroapi_client.get_flight_status(trip.flight_number, flight_date_str)
            
            if current_status:
                status_lower = current_status.status.lower()
                
                # Case 1: Flight has departed
                if any(keyword in status_lower for keyword in ['departed', 'airborne', 'en route', 'cruising']):
                    if trip.estimated_arrival:
                        # Set next check to estimated landing time
                        next_check = trip.estimated_arrival
                        logger.info("intelligent_next_check_departed_to_landing", 
                            trip_id=str(trip.id),
                            next_check=next_check.isoformat(),
                            current_status=current_status.status
                        )
                    else:
                        # No estimated arrival, check in 2 hours
                        next_check = now_utc + timedelta(hours=2)
                        logger.warning("intelligent_next_check_departed_no_eta", 
                            trip_id=str(trip.id),
                            next_check=next_check.isoformat()
                        )
                
                # Case 2: Flight has landed  
                elif any(keyword in status_lower for keyword in ['arrived', 'landed']):
                    # Remove from polling (set far future date)
                    next_check = now_utc + timedelta(days=365)
                    logger.info("intelligent_next_check_landed_removed", 
                        trip_id=str(trip.id),
                        current_status=current_status.status
                    )
                
                # Case 3: Pre-departure logic
                else:
                    if hours_to_departure > 2:
                        # Check 2 hours before departure
                        next_check = trip.departure_date - timedelta(hours=2)
                    elif hours_to_departure > 0.5:
                        # Check 30 minutes before departure
                        next_check = trip.departure_date - timedelta(minutes=30)
                    else:
                        # Departure imminent, check in 15 minutes
                        next_check = now_utc + timedelta(minutes=15)
                    
                    logger.info("intelligent_next_check_pre_departure", 
                        trip_id=str(trip.id),
                        hours_to_departure=round(hours_to_departure, 2),
                        next_check=next_check.isoformat(),
                        current_status=current_status.status
                    )
            else:
                # No flight status available, default logic
                if hours_to_departure > 2:
                    next_check = trip.departure_date - timedelta(hours=2)
                else:
                    next_check = now_utc + timedelta(hours=1)
                
                logger.warning("intelligent_next_check_no_status", 
                    trip_id=str(trip.id),
                    next_check=next_check.isoformat()
                )
            
            # Update next_check_at in database
            await self.db_client.update_next_check_at(trip.id, next_check)
            
        except Exception as e:
            logger.error("intelligent_next_check_update_failed", 
                trip_id=str(trip.id),
                error=str(e)
            )
            # Fallback: check in 1 hour
            fallback_check = now_utc + timedelta(hours=1)
            await self.db_client.update_next_check_at(trip.id, fallback_check)
    
    async def _process_boarding_notifications(self):
        """Check for boarding notifications needed in next 5 minutes"""
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Get trips with departure in next 35-45 minutes (boarding window)
            start_window = now_utc + timedelta(minutes=35)
            end_window = now_utc + timedelta(minutes=45)
            
            # Query trips in boarding window
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
                    continue  # Already sent
                
                # Send boarding notification
                result = await self.notifications_agent.send_single_notification(
                    trip.id, 
                    NotificationType.BOARDING
                )
                
                if result.success:
                    logger.info("boarding_notification_sent", 
                        trip_id=str(trip.id)
                    )
                
        except Exception as e:
            logger.error("boarding_notifications_exception", error=str(e))
    
    async def _process_landing_detection(self):
        """Process landing detection and welcome messages"""
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
        """Send immediate 24h reminder for last-minute trips"""
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
        """Send boarding notification 40 minutes before departure"""
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
        """Generate itinerary for scheduled trip"""
        try:
            # Import ItineraryAgent here to avoid circular imports
            from ..agents.itinerary_agent import ItineraryAgent
            
            logger.info("scheduled_itinerary_generation_started", trip_id=trip_id)
            
            # Initialize itinerary agent
            itinerary_agent = ItineraryAgent()
            
            # Generate itinerary
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
            
            # Close resources
            await itinerary_agent.close()
                
        except Exception as e:
            logger.error("scheduled_itinerary_generation_exception", 
                trip_id=trip_id, 
                error=str(e)
            )
    
    def get_job_status(self) -> dict:
        """Get current status of all scheduled jobs"""
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
            "jobs": jobs
        } 