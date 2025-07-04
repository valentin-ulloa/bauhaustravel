#!/usr/bin/env python3
"""
Landing Detection Validation Script for Bauhaus Travel
Tests landing detection logic and implementation gaps
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
import structlog

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.services.aeroapi_client import AeroAPIClient, FlightStatus
from app.models.database import Trip

logger = structlog.get_logger()

class LandingDetectionValidator:
    """Test landing detection functionality and gaps"""
    
    def __init__(self):
        self.db_client = SupabaseDBClient()
        self.notifications_agent = NotificationsAgent()
        self.aeroapi_client = AeroAPIClient()
        
    async def run_landing_tests(self):
        """Run comprehensive landing detection validation"""
        
        print("\n🛬 **LANDING DETECTION VALIDATION TESTS**")
        print("="*50)
        
        # Test 1: Check current implementation
        await self._test_current_implementation()
        
        # Test 2: Test AeroAPI landing detection capability
        await self._test_aeroapi_landing_capability()
        
        # Test 3: Analyze historical flights for landing patterns
        await self._analyze_historical_landings()
        
        # Test 4: Test notification flow for landed flights
        await self._test_landing_notification_flow()
        
        # Test 5: Performance and timing analysis
        await self._test_landing_timing_requirements()
        
        print("\n✅ **LANDING DETECTION TESTS COMPLETED**")
        
    async def _test_current_implementation(self):
        """Test the current landing detection implementation"""
        print("\n🔍 **TEST 1: CURRENT IMPLEMENTATION**")
        
        try:
            # Test the current poll_landed_flights method
            result = await self.notifications_agent.poll_landed_flights()
            
            print(f"  Current implementation result:")
            print(f"    Success: {result.success}")
            print(f"    Data: {result.data}")
            print(f"    Error: {result.error}")
            print(f"    Affected rows: {result.affected_rows}")
            
            if result.data and result.data.get("landed_flights") == 0:
                print("  ⚠️  **CURRENT IMPLEMENTATION IS PLACEHOLDER**")
                print("     - Returns success but no actual landing detection")
                print("     - No real logic implemented")
                
        except Exception as e:
            print(f"  ❌ Current implementation failed: {e}")
    
    async def _test_aeroapi_landing_capability(self):
        """Test AeroAPI's capability to detect landings"""
        print("\n🌐 **TEST 2: AEROAPI LANDING CAPABILITY**")
        
        try:
            # Test with some recent flights that likely have landed
            test_flights = [
                {"flight": "AA100", "date": (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")},
                {"flight": "DL200", "date": (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%d")},
                {"flight": "UA300", "date": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")},
            ]
            
            print("  Testing AeroAPI status detection for recently departed flights:")
            
            for test_flight in test_flights:
                try:
                    status = await self.aeroapi_client.get_flight_status(
                        test_flight["flight"], 
                        test_flight["date"]
                    )
                    
                    if status:
                        print(f"    {test_flight['flight']} ({test_flight['date']}):")
                        print(f"      Status: {status.status}")
                        print(f"      Progress: {status.progress_percent}%")
                        print(f"      Estimated Out: {status.estimated_out}")
                        print(f"      Actual Out: {status.actual_out}")
                        print(f"      Estimated In: {status.estimated_in}")
                        print(f"      Actual In: {status.actual_in}")
                        
                        # Check if this indicates a landing
                        is_landed = self._analyze_landing_status(status)
                        print(f"      Landing detected: {'✅ YES' if is_landed else '❌ NO'}")
                        
                    else:
                        print(f"    {test_flight['flight']}: No data available")
                        
                except Exception as e:
                    print(f"    {test_flight['flight']}: Error - {e}")
                    
        except Exception as e:
            print(f"  ❌ AeroAPI testing failed: {e}")
    
    def _analyze_landing_status(self, status: FlightStatus) -> bool:
        """Analyze if a flight status indicates landing"""
        
        # Check for explicit landed status
        if status.status and "arrived" in status.status.lower():
            return True
            
        if status.status and "landed" in status.status.lower():
            return True
        
        # Check for 100% progress (likely completed)
        if status.progress_percent and status.progress_percent >= 100:
            return True
            
        # Check if actual_in is populated (actual arrival time)
        if status.actual_in:
            try:
                actual_in_time = datetime.fromisoformat(status.actual_in.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                # If actual arrival was more than 30 minutes ago, likely landed
                if (now - actual_in_time).total_seconds() > 1800:  # 30 minutes
                    return True
            except:
                pass
                
        return False
    
    async def _analyze_historical_landings(self):
        """Analyze historical trips for landing detection patterns"""
        print("\n📊 **TEST 3: HISTORICAL LANDING ANALYSIS**")
        
        try:
            # Get trips from last 7 days that should have landed
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=7)
            
            # Get all trips in this time range
            all_trips = await self.db_client.get_trips_to_poll(end_time)
            
            # Filter for trips that have departed (should be landed or in-flight)
            historical_trips = [
                trip for trip in all_trips 
                if trip.departure_date < end_time and trip.departure_date > start_time
            ]
            
            print(f"  Found {len(historical_trips)} trips from last 7 days")
            
            if not historical_trips:
                print("  No historical trips to analyze")
                return
                
            landed_count = 0
            in_flight_count = 0
            unknown_count = 0
            
            for trip in historical_trips[:10]:  # Analyze first 10
                try:
                    # Calculate if this flight should have landed
                    time_since_departure = end_time - trip.departure_date
                    
                    # Assume average flight duration is 4 hours (conservative)
                    expected_duration = timedelta(hours=4)
                    
                    if time_since_departure > expected_duration + timedelta(hours=2):
                        # Should definitely be landed
                        
                        # Try to get current status
                        departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
                        status = await self.aeroapi_client.get_flight_status(
                            trip.flight_number, 
                            departure_date_str
                        )
                        
                        if status:
                            is_landed = self._analyze_landing_status(status)
                            if is_landed:
                                landed_count += 1
                                print(f"    ✅ {trip.flight_number}: LANDED")
                            else:
                                in_flight_count += 1
                                print(f"    ✈️  {trip.flight_number}: IN-FLIGHT (Status: {status.status})")
                        else:
                            unknown_count += 1
                            print(f"    ❓ {trip.flight_number}: UNKNOWN (No AeroAPI data)")
                            
                except Exception as e:
                    unknown_count += 1
                    print(f"    ❌ {trip.flight_number}: ERROR - {e}")
            
            print(f"\n  Summary of analyzed flights:")
            print(f"    Landed: {landed_count}")
            print(f"    In-flight: {in_flight_count}")
            print(f"    Unknown: {unknown_count}")
            
            if landed_count == 0:
                print("  ⚠️  **NO LANDINGS DETECTED** - Implementation needed!")
                
        except Exception as e:
            print(f"  ❌ Historical analysis failed: {e}")
    
    async def _test_landing_notification_flow(self):
        """Test the notification flow for landed flights"""
        print("\n💬 **TEST 4: LANDING NOTIFICATION FLOW**")
        
        # Check if we have landing notification templates
        from app.agents.notifications_templates import NotificationType, WhatsAppTemplates
        
        # Check if landing/welcome template exists
        landing_templates = []
        for notification_type in NotificationType:
            if "land" in notification_type.value.lower() or "welcome" in notification_type.value.lower():
                landing_templates.append(notification_type)
        
        print(f"  Available landing notification templates: {len(landing_templates)}")
        
        if not landing_templates:
            print("  ⚠️  **NO LANDING NOTIFICATION TEMPLATES**")
            print("     - Need to create welcome/landing templates in Twilio")
            print("     - Need to add LANDING/WELCOME NotificationType")
            print("     - Need to implement format_landing_welcome() method")
        else:
            for template in landing_templates:
                print(f"    ✅ {template}")
        
        # Test notification sending simulation
        print("\n  Testing notification sending simulation:")
        try:
            # Get a test trip
            now_utc = datetime.now(timezone.utc)
            future_time = now_utc + timedelta(days=30)
            trips = await self.db_client.get_trips_to_poll(future_time)
            
            if trips:
                test_trip = trips[0]
                print(f"    Test trip: {test_trip.flight_number} ({test_trip.client_name})")
                
                # Check what would happen if we sent a landing notification
                print(f"    WhatsApp: {test_trip.whatsapp}")
                print(f"    Would need: Landing welcome template + notification logic")
                
                # Check notification history to avoid duplicates
                # Note: This will fail because LANDING doesn't exist yet
                try:
                    history = await self.db_client.get_notification_history(
                        test_trip.id, "LANDING"
                    )
                    print(f"    Previous landing notifications: {len(history)}")
                except Exception as e:
                    print(f"    ⚠️  Can't check landing notification history: {e}")
                    
            else:
                print("    No test trips available")
                
        except Exception as e:
            print(f"    ❌ Notification flow test failed: {e}")
    
    async def _test_landing_timing_requirements(self):
        """Test timing requirements for landing detection"""
        print("\n⏰ **TEST 5: LANDING TIMING REQUIREMENTS**")
        
        print("  Current scheduler configuration:")
        print("    Landing detection frequency: Every 30 minutes")
        print("    AeroAPI cache duration: 5 minutes")
        
        # Calculate detection delay scenarios
        scenarios = [
            {"flight_duration": "1 hour", "max_delay": 30},
            {"flight_duration": "4 hours", "max_delay": 30}, 
            {"flight_duration": "8 hours", "max_delay": 30},
            {"flight_duration": "12 hours", "max_delay": 30}
        ]
        
        print("\n  Landing detection delay scenarios:")
        for scenario in scenarios:
            print(f"    {scenario['flight_duration']} flight: Up to {scenario['max_delay']} min delay")
        
        print("\n  Recommendations for improvement:")
        print("    ✅ Current 30-minute frequency is reasonable")
        print("    ⚠️  Need to implement actual landing detection logic")
        print("    ⚠️  Need to create landing notification templates")
        print("    ⚠️  Need to track landing notification history")
        
    async def close(self):
        """Clean up resources"""
        await self.db_client.close()
        await self.notifications_agent.close()

async def main():
    """Run landing detection validation tests"""
    
    validator = LandingDetectionValidator()
    
    try:
        await validator.run_landing_tests()
        
    except Exception as e:
        print(f"❌ Landing detection validation failed: {e}")
        
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main()) 