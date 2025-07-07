#!/usr/bin/env python3
"""
Test script for validating the NotificationsAgent fixes in production.

This script tests the exact scenarios that caused false delayed notifications:
1. Status "Scheduled" → Should NOT trigger delayed notification
2. NULL → estimated_out → Should NOT trigger delayed notification  
3. Only real delays should trigger notifications

Usage:
    python scripts/test_notifications_fixes.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.aeroapi_client import AeroAPIClient, FlightStatus
from app.agents.notifications_agent import NotificationsAgent
from app.models.database import Trip
import structlog

# Configure logging
logger = structlog.get_logger()


async def test_scheduled_status_scenario():
    """Test Case 1: Scheduled status should NOT trigger delayed notification"""
    print("\n=== TEST 1: Scheduled Status Scenario ===")
    
    client = AeroAPIClient()
    
    # Previous status (from database, likely minimal info)
    previous = FlightStatus(
        ident="AR1234",
        status="Unknown",  # Or None in some cases
        estimated_out=None
    )
    
    # Current status from AeroAPI (what caused the false alarm)
    current = FlightStatus(
        ident="AR1234", 
        status="Scheduled",
        estimated_out="2024-07-08T02:30:00Z"
    )
    
    changes = client.detect_flight_changes(current, previous)
    
    print(f"Previous: status={previous.status}, estimated_out={previous.estimated_out}")
    print(f"Current:  status={current.status}, estimated_out={current.estimated_out}")
    print(f"Changes detected: {len(changes)}")
    
    for change in changes:
        print(f"  - {change['type']}: {change['old_value']} → {change['new_value']} (notification: {change.get('notification_type')})")
    
    # Validation
    delayed_changes = [c for c in changes if c.get('notification_type') == 'delayed']
    
    if len(delayed_changes) == 0:
        print("✅ PASS: No false delayed notifications triggered")
        return True
    else:
        print("❌ FAIL: False delayed notification would be sent!")
        return False


async def test_initial_estimated_out_scenario():
    """Test Case 2: Initial estimated_out assignment should NOT trigger delay"""
    print("\n=== TEST 2: Initial estimated_out Assignment ===")
    
    client = AeroAPIClient()
    
    # Previous: Flight exists in DB but no estimated_out yet
    previous = FlightStatus(
        ident="AR1234",
        status="Scheduled",
        estimated_out=None  # This is key - no time set yet
    )
    
    # Current: AeroAPI provides estimated_out for first time
    current = FlightStatus(
        ident="AR1234",
        status="Scheduled", 
        estimated_out="2024-07-08T02:30:00Z"
    )
    
    changes = client.detect_flight_changes(current, previous)
    
    print(f"Previous: status={previous.status}, estimated_out={previous.estimated_out}")
    print(f"Current:  status={current.status}, estimated_out={current.estimated_out}")
    print(f"Changes detected: {len(changes)}")
    
    for change in changes:
        print(f"  - {change['type']}: {change['old_value']} → {change['new_value']} (notification: {change.get('notification_type')})")
    
    # Validation
    delayed_changes = [c for c in changes if c.get('notification_type') == 'delayed']
    
    if len(delayed_changes) == 0:
        print("✅ PASS: Initial estimated_out assignment does not trigger delay")
        return True
    else:
        print("❌ FAIL: Initial estimated_out triggered false delay notification!")
        return False


async def test_real_delay_scenario():
    """Test Case 3: Real delays should STILL trigger notifications"""
    print("\n=== TEST 3: Real Delay Detection ===")
    
    client = AeroAPIClient()
    
    # Previous: Flight was on time
    previous = FlightStatus(
        ident="AR1234",
        status="Scheduled",
        estimated_out="2024-07-08T02:30:00Z"
    )
    
    # Current: Flight is actually delayed
    current = FlightStatus(
        ident="AR1234",
        status="Delayed",  # Status changed to Delayed
        estimated_out="2024-07-08T03:15:00Z"  # 45 minutes later
    )
    
    changes = client.detect_flight_changes(current, previous)
    
    print(f"Previous: status={previous.status}, estimated_out={previous.estimated_out}")
    print(f"Current:  status={current.status}, estimated_out={current.estimated_out}")
    print(f"Changes detected: {len(changes)}")
    
    for change in changes:
        print(f"  - {change['type']}: {change['old_value']} → {change['new_value']} (notification: {change.get('notification_type')})")
    
    # Validation
    delayed_changes = [c for c in changes if c.get('notification_type') == 'delayed']
    
    if len(delayed_changes) > 0:
        print("✅ PASS: Real delays correctly trigger notifications")
        return True
    else:
        print("❌ FAIL: Real delay was not detected!")
        return False


async def test_significant_delay_without_status():
    """Test Case 4: Significant time delays should trigger even without status change"""
    print("\n=== TEST 4: Significant Delay Without Status Change ===")
    
    client = AeroAPIClient()
    
    # Previous: Flight scheduled for 02:30
    previous = FlightStatus(
        ident="AR1234",
        status="Scheduled",
        estimated_out="2024-07-08T02:30:00Z"
    )
    
    # Current: Time moved significantly but status not updated yet
    current = FlightStatus(
        ident="AR1234", 
        status="Scheduled",  # Status not changed yet
        estimated_out="2024-07-08T03:00:00Z"  # 30 minutes later - significant
    )
    
    changes = client.detect_flight_changes(current, previous)
    
    print(f"Previous: status={previous.status}, estimated_out={previous.estimated_out}")
    print(f"Current:  status={current.status}, estimated_out={current.estimated_out}")
    print(f"Changes detected: {len(changes)}")
    
    for change in changes:
        print(f"  - {change['type']}: {change['old_value']} → {change['new_value']} (notification: {change.get('notification_type')})")
    
    # Validation
    delayed_changes = [c for c in changes if c.get('notification_type') == 'delayed']
    
    if len(delayed_changes) > 0:
        print("✅ PASS: Significant delays trigger notifications even without status change")
        return True
    else:
        print("❌ FAIL: Significant delay was not detected!")
        return False


async def test_moderate_delay_waits_confirmation():
    """Test Case 5: Moderate delays should wait for status confirmation"""
    print("\n=== TEST 5: Moderate Delay Waits for Confirmation ===")
    
    client = AeroAPIClient()
    
    # Previous: Flight scheduled for 02:30
    previous = FlightStatus(
        ident="AR1234",
        status="Scheduled",
        estimated_out="2024-07-08T02:30:00Z"
    )
    
    # Current: Time moved moderately (10 minutes) but status not changed
    current = FlightStatus(
        ident="AR1234",
        status="Scheduled",  # Status not changed yet
        estimated_out="2024-07-08T02:40:00Z"  # 10 minutes later - moderate
    )
    
    changes = client.detect_flight_changes(current, previous)
    
    print(f"Previous: status={previous.status}, estimated_out={previous.estimated_out}")
    print(f"Current:  status={current.status}, estimated_out={current.estimated_out}")
    print(f"Changes detected: {len(changes)}")
    
    for change in changes:
        print(f"  - {change['type']}: {change['old_value']} → {change['new_value']} (notification: {change.get('notification_type')})")
    
    # Validation - moderate delays should NOT trigger without status confirmation
    delayed_changes = [c for c in changes if c.get('notification_type') == 'delayed']
    
    if len(delayed_changes) == 0:
        print("✅ PASS: Moderate delays wait for status confirmation")
        return True
    else:
        print("❌ FAIL: Moderate delay triggered premature notification!")
        return False


async def test_normal_statuses():
    """Test Case 6: Normal flight statuses should not trigger notifications"""
    print("\n=== TEST 6: Normal Status Mapping ===")
    
    client = AeroAPIClient()
    
    normal_statuses = ["Scheduled", "On Time", "Taxiing", "Pushback", "Unknown"]
    alertable_statuses = ["Delayed", "Cancelled", "Boarding"]
    
    print("Testing normal statuses (should NOT trigger notifications):")
    all_passed = True
    
    for status in normal_statuses:
        result = client._map_status_to_notification(status)
        expected = "no_notification"
        
        if result == expected:
            print(f"  ✅ {status} → {result}")
        else:
            print(f"  ❌ {status} → {result} (expected {expected})")
            all_passed = False
    
    print("\nTesting alertable statuses (SHOULD trigger notifications):")
    
    for status in alertable_statuses:
        result = client._map_status_to_notification(status)
        expected = status.lower()
        
        if result == expected:
            print(f"  ✅ {status} → {result}")
        else:
            print(f"  ❌ {status} → {result} (expected {expected})")
            all_passed = False
    
    return all_passed


async def main():
    """Run all test scenarios"""
    print("🧪 Testing NotificationsAgent Fixes")
    print("==================================")
    
    test_results = []
    
    # Run all test scenarios
    test_results.append(await test_scheduled_status_scenario())
    test_results.append(await test_initial_estimated_out_scenario())
    test_results.append(await test_real_delay_scenario())
    test_results.append(await test_significant_delay_without_status())
    test_results.append(await test_moderate_delay_waits_confirmation())
    test_results.append(await test_normal_statuses())
    
    # Summary
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"\n🎯 SUMMARY")
    print(f"=========")
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! The fix is working correctly.")
        print("\n✅ Production deployment should resolve the false delayed notifications.")
        return True
    else:
        print("❌ SOME TESTS FAILED! Review the fix before deployment.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 