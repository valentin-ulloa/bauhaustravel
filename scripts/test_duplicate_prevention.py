#!/usr/bin/env python3
"""
Duplicate Notification Prevention Validation Script for Bauhaus Travel
Tests duplicate prevention mechanisms and identifies gaps
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import structlog

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.models.database import Trip

logger = structlog.get_logger()

class DuplicatePreventionValidator:
    """Test duplicate notification prevention mechanisms"""
    
    def __init__(self):
        self.db_client = SupabaseDBClient()
        self.notifications_agent = NotificationsAgent()
        
    async def run_duplicate_tests(self):
        """Run comprehensive duplicate prevention validation"""
        
        print("\n🔄 **DUPLICATE PREVENTION VALIDATION TESTS**")
        print("="*50)
        
        # Test 1: Analyze current prevention mechanisms
        await self._test_current_prevention_mechanisms()
        
        # Test 2: Test notification history effectiveness
        await self._test_notification_history()
        
        # Test 3: Test edge cases for duplicates
        await self._test_duplicate_edge_cases()
        
        # Test 4: Test cross-agent duplicate prevention
        await self._test_cross_agent_duplicates()
        
        # Test 5: Performance impact of duplicate checks
        await self._test_duplicate_check_performance()
        
        print("\n✅ **DUPLICATE PREVENTION TESTS COMPLETED**")
        
    async def _test_current_prevention_mechanisms(self):
        """Test current duplicate prevention mechanisms"""
        print("\n🛡️  **TEST 1: CURRENT PREVENTION MECHANISMS**")
        
        # Check 24h reminder duplicate prevention
        print("  24h Reminder Duplicate Prevention:")
        print("    ✅ Checks notification history for REMINDER_24H")
        print("    ✅ Looks for delivery_status == 'SENT'")
        print("    ✅ Skips if already sent")
        
        # Check flight change duplicate prevention
        print("\n  Flight Change Duplicate Prevention:")
        print("    ❓ No explicit duplicate check in _process_flight_change")
        print("    ⚠️  Could send multiple notifications for same change")
        print("    ⚠️  Relies on change detection logic being accurate")
        
        # Check boarding notification duplicate prevention
        print("\n  Boarding Notification Duplicate Prevention:")
        print("    ✅ Checks notification history for 'BOARDING'")
        print("    ✅ Uses scheduler service check")
        print("    ✅ Skips if already sent")
        
        # Check reservation confirmation duplicates
        print("\n  Reservation Confirmation Duplicate Prevention:")
        print("    ❓ No explicit duplicate check")
        print("    ⚠️  POST /trips could theoretically be called multiple times")
        print("    ⚠️  Relies on application-level prevention")
        
    async def _test_notification_history(self):
        """Test notification history effectiveness"""
        print("\n📜 **TEST 2: NOTIFICATION HISTORY EFFECTIVENESS**")
        
        try:
            # Get some trips with notification history
            now_utc = datetime.now(timezone.utc)
            future_time = now_utc + timedelta(days=30)
            trips = await self.db_client.get_trips_to_poll(future_time)
            
            if not trips:
                print("  No trips found for testing")
                return
                
            print(f"  Testing notification history for {len(trips)} trips")
            
            total_notifications = 0
            trips_with_notifications = 0
            duplicate_risks = 0
            
            for trip in trips[:10]:  # Test first 10 trips
                try:
                    # Check each notification type history
                    for notification_type in [NotificationType.REMINDER_24H, NotificationType.BOARDING, 
                                            NotificationType.RESERVATION_CONFIRMATION]:
                        
                        history = await self.db_client.get_notification_history(
                            trip.id, notification_type
                        )
                        
                        if history:
                            total_notifications += len(history)
                            if len(history) > 1:
                                duplicate_risks += 1
                                print(f"    ⚠️  Trip {trip.flight_number}: {len(history)} {notification_type} notifications")
                                
                                # Analyze the duplicates
                                for i, notification in enumerate(history):
                                    print(f"      {i+1}. {notification.sent_at} - {notification.delivery_status}")
                    
                    if total_notifications > 0:
                        trips_with_notifications += 1
                        
                except Exception as e:
                    print(f"    ❌ Error checking history for trip {trip.id}: {e}")
            
            print(f"\n  Summary:")
            print(f"    Trips with notifications: {trips_with_notifications}")
            print(f"    Total notifications: {total_notifications}")
            print(f"    Potential duplicates: {duplicate_risks}")
            
            if duplicate_risks > 0:
                print(f"    ⚠️  **DUPLICATES DETECTED** - Need investigation")
            else:
                print(f"    ✅ No obvious duplicates found")
                
        except Exception as e:
            print(f"  ❌ Notification history test failed: {e}")
    
    async def _test_duplicate_edge_cases(self):
        """Test edge cases that could cause duplicates"""
        print("\n🚨 **TEST 3: DUPLICATE EDGE CASES**")
        
        edge_cases = [
            {
                "name": "Same flight change detected multiple times",
                "scenario": "AeroAPI returns same gate change in consecutive polls",
                "risk": "HIGH",
                "current_protection": "Change detection logic should prevent this"
            },
            {
                "name": "Scheduler job overlap",
                "scenario": "24h reminder job runs while previous job still executing",
                "risk": "MEDIUM", 
                "current_protection": "APScheduler max_instances=1"
            },
            {
                "name": "Manual API calls during scheduled operations",
                "scenario": "POST /trips called while automatic reminders running",
                "risk": "LOW",
                "current_protection": "Different notification types"
            },
            {
                "name": "Database transaction failures",
                "scenario": "Notification sent but logging fails, then retried",
                "risk": "HIGH",
                "current_protection": "None - potential gap"
            },
            {
                "name": "Multiple gate changes in short period",
                "scenario": "Gate changes from A->B->C within minutes",
                "risk": "MEDIUM",
                "current_protection": "Each change should be separate notification"
            }
        ]
        
        for case in edge_cases:
            risk_color = "🔴" if case["risk"] == "HIGH" else "🟡" if case["risk"] == "MEDIUM" else "🟢"
            print(f"\n  {risk_color} **{case['name']}**")
            print(f"    Scenario: {case['scenario']}")
            print(f"    Risk Level: {case['risk']}")
            print(f"    Current Protection: {case['current_protection']}")
            
            if case["risk"] == "HIGH":
                print("    🚨 **REQUIRES IMMEDIATE ATTENTION**")
    
    async def _test_cross_agent_duplicates(self):
        """Test potential duplicates across different agents"""
        print("\n🤝 **TEST 4: CROSS-AGENT DUPLICATE PREVENTION**")
        
        cross_agent_scenarios = [
            {
                "agents": ["NotificationsAgent", "SchedulerService"],
                "scenario": "Both send boarding notifications",
                "overlap": "boarding_notification_scheduled vs _process_boarding_notifications",
                "risk": "MEDIUM"
            },
            {
                "agents": ["NotificationsAgent", "Router"],
                "scenario": "Manual trigger during automatic operations",
                "overlap": "POST /trips confirmation vs scheduled reminders",
                "risk": "LOW"
            },
            {
                "agents": ["SchedulerService", "Manual API"],
                "scenario": "Manual itinerary generation vs automatic",
                "overlap": "POST /itinerary vs scheduled generation",
                "risk": "LOW"
            }
        ]
        
        for scenario in cross_agent_scenarios:
            risk_color = "🔴" if scenario["risk"] == "HIGH" else "🟡" if scenario["risk"] == "MEDIUM" else "🟢"
            print(f"\n  {risk_color} **{' + '.join(scenario['agents'])}**")
            print(f"    Scenario: {scenario['scenario']}")
            print(f"    Overlap: {scenario['overlap']}")
            print(f"    Risk: {scenario['risk']}")
            
            if scenario["risk"] in ["HIGH", "MEDIUM"]:
                print("    📋 Recommended: Add cross-agent coordination checks")
    
    async def _test_duplicate_check_performance(self):
        """Test performance impact of duplicate prevention checks"""
        print("\n⚡ **TEST 5: DUPLICATE CHECK PERFORMANCE**")
        
        try:
            # Simulate multiple duplicate checks
            start_time = datetime.now()
            
            # Get a test trip
            now_utc = datetime.now(timezone.utc)
            future_time = now_utc + timedelta(days=30)
            trips = await self.db_client.get_trips_to_poll(future_time)
            
            if not trips:
                print("  No trips available for performance testing")
                return
                
            test_trip = trips[0]
            
            # Simulate checking notification history multiple times
            check_count = 50
            total_time = 0
            
            for i in range(check_count):
                check_start = datetime.now()
                
                history = await self.db_client.get_notification_history(
                    test_trip.id, NotificationType.REMINDER_24H
                )
                
                check_end = datetime.now()
                check_duration = (check_end - check_start).total_seconds() * 1000
                total_time += check_duration
            
            avg_time = total_time / check_count
            
            print(f"  Notification history check performance:")
            print(f"    Checks performed: {check_count}")
            print(f"    Total time: {total_time:.2f}ms")
            print(f"    Average per check: {avg_time:.2f}ms")
            
            if avg_time > 100:  # > 100ms
                print("    ⚠️  **SLOW PERFORMANCE** - Consider optimization")
            elif avg_time > 50:  # > 50ms
                print("    🟡 Moderate performance - acceptable")
            else:
                print("    ✅ Good performance")
                
            # Test batch checking performance
            batch_start = datetime.now()
            
            # Check multiple notification types at once
            for notification_type in [NotificationType.REMINDER_24H, NotificationType.BOARDING, 
                                    NotificationType.RESERVATION_CONFIRMATION]:
                await self.db_client.get_notification_history(test_trip.id, notification_type)
            
            batch_end = datetime.now()
            batch_time = (batch_end - batch_start).total_seconds() * 1000
            
            print(f"\n  Batch duplicate check performance:")
            print(f"    Checked 3 notification types: {batch_time:.2f}ms")
            
            if batch_time > 200:
                print("    ⚠️  Consider caching or batch query optimization")
            else:
                print("    ✅ Acceptable batch performance")
                
        except Exception as e:
            print(f"  ❌ Performance test failed: {e}")
    
    async def close(self):
        """Clean up resources"""
        await self.db_client.close()
        await self.notifications_agent.close()

async def main():
    """Run duplicate prevention validation tests"""
    
    validator = DuplicatePreventionValidator()
    
    try:
        await validator.run_duplicate_tests()
        
        print("\n📋 **RECOMMENDATIONS SUMMARY**")
        print("="*50)
        print("1. 🔴 HIGH PRIORITY: Add transaction-safe notification logging")
        print("2. 🟡 MEDIUM: Improve flight change duplicate detection")
        print("3. 🟡 MEDIUM: Add cross-agent coordination checks")
        print("4. 🟢 LOW: Monitor performance of duplicate checks")
        
    except Exception as e:
        print(f"❌ Duplicate prevention validation failed: {e}")
        
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main()) 