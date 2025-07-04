#!/usr/bin/env python3
"""
Timezone Validation Script for Bauhaus Travel
Tests timezone accuracy for quiet hours and flight notifications
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import structlog

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.models.database import Trip

logger = structlog.get_logger()

# Airport timezone mapping (simplified for testing)
AIRPORT_TIMEZONES = {
    'GRU': 'America/Sao_Paulo',      # São Paulo UTC-3
    'EZE': 'America/Argentina/Buenos_Aires',  # Buenos Aires UTC-3
    'MIA': 'America/New_York',       # Miami UTC-5 (EST)
    'JFK': 'America/New_York',       # New York UTC-5 (EST)  
    'MEX': 'America/Mexico_City',    # Mexico City UTC-6
    'LAX': 'America/Los_Angeles',    # Los Angeles UTC-8 (PST)
    'MAD': 'Europe/Madrid',          # Madrid UTC+1
    'LHR': 'Europe/London',          # London UTC+0
    'CDG': 'Europe/Paris',           # Paris UTC+1
    'DXB': 'Asia/Dubai',             # Dubai UTC+4
    'NRT': 'Asia/Tokyo',             # Tokyo UTC+9
    'SCL': 'America/Santiago',       # Santiago UTC-3
    'PTY': 'America/Panama',         # Panama UTC-5
    'BOG': 'America/Bogota',         # Bogotá UTC-5
    'LIM': 'America/Lima',           # Lima UTC-5
}

class TimezoneValidator:
    """Test timezone handling across different scenarios"""
    
    def __init__(self):
        self.db_client = SupabaseDBClient()
        self.notifications_agent = NotificationsAgent()
        
    async def run_timezone_tests(self):
        """Run comprehensive timezone validation tests"""
        
        print("\n🕐 **TIMEZONE VALIDATION TESTS**")
        print("="*50)
        
        # Test 1: Current quiet hours logic (UTC vs Local)
        await self._test_quiet_hours_accuracy()
        
        # Test 2: Test different timezone scenarios
        await self._test_timezone_scenarios()
        
        # Test 3: Validate existing trips timezone handling
        await self._test_existing_trips_timezones()
        
        # Test 4: Cross-timezone notification timing
        await self._test_cross_timezone_notifications()
        
        print("\n✅ **TIMEZONE TESTS COMPLETED**")
        
    async def _test_quiet_hours_accuracy(self):
        """Test current quiet hours logic vs correct local time"""
        print("\n🌙 **TEST 1: QUIET HOURS ACCURACY**")
        
        now_utc = datetime.now(timezone.utc)
        current_hour_utc = now_utc.hour
        
        print(f"Current UTC time: {now_utc.strftime('%H:%M')} (hour: {current_hour_utc})")
        print(f"Current UTC quiet hours: {'YES' if (current_hour_utc < 9 or current_hour_utc >= 20) else 'NO'}")
        
        # Test different origin airports
        test_airports = ['GRU', 'MIA', 'MEX', 'MAD', 'DXB', 'NRT']
        
        for airport in test_airports:
            if airport in AIRPORT_TIMEZONES:
                tz = ZoneInfo(AIRPORT_TIMEZONES[airport])
                local_time = now_utc.astimezone(tz)
                local_hour = local_time.hour
                
                is_quiet_local = local_hour < 9 or local_hour >= 20
                is_quiet_utc = current_hour_utc < 9 or current_hour_utc >= 20
                
                mismatch = "⚠️  MISMATCH!" if is_quiet_local != is_quiet_utc else "✅ OK"
                
                print(f"  {airport}: {local_time.strftime('%H:%M')} (local) | Quiet: {is_quiet_local} | UTC Quiet: {is_quiet_utc} | {mismatch}")
    
    async def _test_timezone_scenarios(self):
        """Test specific problematic timezone scenarios"""
        print("\n🌍 **TEST 2: TIMEZONE SCENARIOS**")
        
        scenarios = [
            {
                "name": "Buenos Aires morning (should allow notifications)",
                "airport": "EZE",
                "test_hour_local": 10,  # 10 AM local
                "expected_quiet": False
            },
            {
                "name": "Mexico late night (should be quiet)",
                "airport": "MEX", 
                "test_hour_local": 22,  # 10 PM local
                "expected_quiet": True
            },
            {
                "name": "Dubai afternoon (should allow notifications)",
                "airport": "DXB",
                "test_hour_local": 15,  # 3 PM local
                "expected_quiet": False
            },
            {
                "name": "Tokyo early morning (should be quiet)",
                "airport": "NRT",
                "test_hour_local": 6,  # 6 AM local
                "expected_quiet": True
            }
        ]
        
        for scenario in scenarios:
            airport = scenario["airport"]
            if airport not in AIRPORT_TIMEZONES:
                continue
                
            tz = ZoneInfo(AIRPORT_TIMEZONES[airport])
            
            # Create a test time at the specific local hour
            now_local = datetime.now(tz)
            test_local = now_local.replace(hour=scenario["test_hour_local"], minute=0)
            test_utc = test_local.astimezone(timezone.utc)
            
            # Current logic (UTC-based)
            utc_hour = test_utc.hour
            is_quiet_utc_logic = utc_hour < 9 or utc_hour >= 20
            
            # Correct logic (local time)
            local_hour = test_local.hour
            is_quiet_correct = local_hour < 9 or local_hour >= 20
            
            mismatch = "⚠️  PROBLEM!" if is_quiet_utc_logic != scenario["expected_quiet"] else "✅ Correct"
            
            print(f"  {scenario['name']}:")
            print(f"    Local: {test_local.strftime('%H:%M %Z')} | UTC: {test_utc.strftime('%H:%M UTC')}")
            print(f"    Expected quiet: {scenario['expected_quiet']} | UTC logic: {is_quiet_utc_logic} | {mismatch}")
    
    async def _test_existing_trips_timezones(self):
        """Test timezone handling for existing trips in database"""
        print("\n✈️  **TEST 3: EXISTING TRIPS TIMEZONES**")
        
        try:
            # Get some existing trips
            now_utc = datetime.now(timezone.utc)
            future_time = now_utc + timedelta(days=30)
            
            trips = await self.db_client.get_trips_to_poll(future_time)
            
            if not trips:
                print("  No trips found for testing")
                return
                
            print(f"  Found {len(trips)} trips to analyze")
            
            for i, trip in enumerate(trips[:5]):  # Test first 5 trips
                origin = trip.origin_iata
                departure_utc = trip.departure_date
                
                if origin in AIRPORT_TIMEZONES:
                    tz = ZoneInfo(AIRPORT_TIMEZONES[origin])
                    departure_local = departure_utc.astimezone(tz)
                    
                    print(f"  Trip {i+1} ({trip.flight_number}): {origin}")
                    print(f"    Departure UTC: {departure_utc.strftime('%Y-%m-%d %H:%M UTC')}")
                    print(f"    Departure Local: {departure_local.strftime('%Y-%m-%d %H:%M %Z')}")
                    
                    # Check 24h reminder timing
                    reminder_time_utc = departure_utc - timedelta(hours=24)
                    reminder_time_local = reminder_time_utc.astimezone(tz)
                    
                    reminder_hour_local = reminder_time_local.hour
                    is_quiet = reminder_hour_local < 9 or reminder_hour_local >= 20
                    
                    print(f"    24h reminder time (local): {reminder_time_local.strftime('%H:%M %Z')}")
                    print(f"    Would be quiet hours: {'YES ⚠️' if is_quiet else 'NO ✅'}")
                
        except Exception as e:
            print(f"  Error testing existing trips: {e}")
    
    async def _test_cross_timezone_notifications(self):
        """Test notification timing across different timezones"""
        print("\n🌐 **TEST 4: CROSS-TIMEZONE NOTIFICATION TIMING**")
        
        # Simulate agency with Mexico client
        mexico_scenario = {
            "agency_location": "Buenos Aires (UTC-3)",
            "client_location": "Mexico City (UTC-6)", 
            "flight_origin": "MEX",
            "notification_type": "24h reminder"
        }
        
        print(f"  Scenario: {mexico_scenario['agency_location']} agency serving {mexico_scenario['client_location']} client")
        
        # Mexico client flying from Mexico City at 2 PM local
        mex_tz = ZoneInfo('America/Mexico_City')
        test_departure_local = datetime.now(mex_tz).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
        test_departure_utc = test_departure_local.astimezone(timezone.utc)
        
        # 24h reminder time
        reminder_utc = test_departure_utc - timedelta(hours=24)
        reminder_local_mex = reminder_utc.astimezone(mex_tz)
        
        print(f"  Flight departure: {test_departure_local.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  24h reminder time (Mexico local): {reminder_local_mex.strftime('%Y-%m-%d %H:%M %Z')}")
        
        # Current system (UTC-based quiet hours)
        utc_hour = reminder_utc.hour
        is_quiet_utc = utc_hour < 9 or utc_hour >= 20
        
        # Correct system (Mexico local quiet hours)
        mex_hour = reminder_local_mex.hour
        is_quiet_correct = mex_hour < 9 or mex_hour >= 20
        
        print(f"  Current system (UTC): {'Would NOT send ❌' if is_quiet_utc else 'Would send ✅'}")
        print(f"  Correct system (Local): {'Should NOT send ✅' if is_quiet_correct else 'Should send ✅'}")
        
        if is_quiet_utc != is_quiet_correct:
            print("  ⚠️  **TIMEZONE MISMATCH DETECTED!**")
            
    async def close(self):
        """Clean up resources"""
        await self.db_client.close()
        await self.notifications_agent.close()

async def main():
    """Run timezone validation tests"""
    
    validator = TimezoneValidator()
    
    try:
        await validator.run_timezone_tests()
        
    except Exception as e:
        print(f"❌ Timezone validation failed: {e}")
        
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main()) 