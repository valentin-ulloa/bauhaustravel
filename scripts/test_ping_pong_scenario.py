#!/usr/bin/env python3
"""
Advanced test script for ping-pong ETA scenario validation.

Test Pattern: 02:30 → null → 02:30 → 03:00 → 03:00
Expected Result: SINGLE notification with 03:00 (final state)

This simulates real AeroAPI behavior where:
1. Flight starts at 02:30
2. API returns null (system glitch)
3. API returns 02:30 (back to original)
4. Flight gets delayed to 03:00
5. API confirms 03:00 (duplicate)

Expected: 1 notification "02:30 → 03:00"
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.agents.notifications_agent import NotificationsAgent
from app.models.database import Trip
import structlog

logger = structlog.get_logger()

async def test_complex_ping_pong_scenario():
    """
    Test the specific scenario reported by Vale:
    02:30 → null → 02:30 → 03:00 → 03:00
    
    Should result in SINGLE notification: "02:30 → 03:00"
    """
    print("🧪 Testing complex ping-pong scenario: 02:30 → null → 02:30 → 03:00 → 03:00")
    
    agent = NotificationsAgent()
    
    # Create test trip
    trip = Trip(
        id=UUID("8a570d1b-f2af-458c-8dbc-3ad58eeb547f"),
        client_name="Vale Ulloa",
        whatsapp="+5491140383422",
        flight_number="AV112",
        origin_iata="EZE",
        destination_iata="MDE",
        departure_date=datetime.now(timezone.utc) + timedelta(hours=2),
        status="scheduled",
        metadata=None,
        inserted_at=datetime.now(timezone.utc),
        next_check_at=None,
        client_description="Test ping-pong scenario",
        agency_id=UUID("00000000-0000-0000-0000-000000000001"),
        gate=None
    )
    
    # Simulate the exact sequence of changes
    changes = [
        {
            "type": "departure_time_change",
            "old_value": "2025-07-08T05:30:00Z",  # 02:30
            "new_value": None,                     # null
            "notification_type": "delayed"
        },
        {
            "type": "departure_time_change", 
            "old_value": None,                     # null
            "new_value": "2025-07-08T05:30:00Z",  # 02:30 (back to original)
            "notification_type": "delayed"
        },
        {
            "type": "departure_time_change",
            "old_value": "2025-07-08T05:30:00Z",  # 02:30
            "new_value": "2025-07-08T06:00:00Z",  # 03:00 (real delay)
            "notification_type": "delayed"
        },
        {
            "type": "departure_time_change",
            "old_value": "2025-07-08T06:00:00Z",  # 03:00
            "new_value": "2025-07-08T06:00:00Z",  # 03:00 (duplicate)
            "notification_type": "delayed"
        }
    ]
    
    print(f"📊 Original changes: {len(changes)}")
    for i, change in enumerate(changes, 1):
        print(f"  {i}. {change['old_value']} → {change['new_value']}")
    
    # Test consolidation
    consolidated = agent._consolidate_ping_pong_changes(changes, trip)
    
    print(f"\n✅ Consolidated changes: {len(consolidated)}")
    for i, change in enumerate(consolidated, 1):
        old_eta = agent._get_prioritized_eta(change['old_value'], "EZE") if change['old_value'] else "null"
        new_eta = agent._get_prioritized_eta(change['new_value'], "EZE") if change['new_value'] else "null"
        print(f"  {i}. {old_eta} → {new_eta}")
    
    # Validate expected result
    assert len(consolidated) == 1, f"Expected 1 consolidated change, got {len(consolidated)}"
    
    final_change = consolidated[0]
    assert final_change["old_value"] == "2025-07-08T05:30:00Z", f"Expected old_value '2025-07-08T05:30:00Z', got {final_change['old_value']}"
    assert final_change["new_value"] == "2025-07-08T06:00:00Z", f"Expected new_value '2025-07-08T06:00:00Z', got {final_change['new_value']}"
    
    # Test ETA formatting
    old_eta_formatted = agent._get_prioritized_eta(final_change["old_value"], "EZE")
    new_eta_formatted = agent._get_prioritized_eta(final_change["new_value"], "EZE") 
    
    print(f"\n📋 Final notification would show:")
    print(f"   Old time: {old_eta_formatted}")
    print(f"   New time: {new_eta_formatted}")
    
    # Validate human-readable format
    assert "02:30" in old_eta_formatted, f"Expected '02:30' in formatted time, got: {old_eta_formatted}"
    assert "03:00" in new_eta_formatted, f"Expected '03:00' in formatted time, got: {new_eta_formatted}"
    
    await agent.close()
    print("\n🎉 Complex ping-pong scenario test PASSED!")
    return True

async def test_simple_ping_pong_suppression():
    """Test that simple A→B→A gets completely suppressed"""
    print("\n🧪 Testing simple ping-pong suppression: 02:30 → null → 02:30")
    
    agent = NotificationsAgent()
    
    trip = Trip(
        id=UUID("8a570d1b-f2af-458c-8dbc-3ad58eeb547f"),
        client_name="Test User",
        whatsapp="+1234567890",
        flight_number="AV112", 
        origin_iata="EZE",
        destination_iata="MDE",
        departure_date=datetime.now(timezone.utc) + timedelta(hours=2),
        status="scheduled",
        metadata=None,
        inserted_at=datetime.now(timezone.utc),
        next_check_at=None,
        client_description="Simple ping-pong test",
        agency_id=UUID("00000000-0000-0000-0000-000000000001"),
        gate=None
    )
    
    # Simple ping-pong: 02:30 → null → 02:30
    changes = [
        {
            "type": "departure_time_change",
            "old_value": "2025-07-08T05:30:00Z",
            "new_value": None,
            "notification_type": "delayed"
        },
        {
            "type": "departure_time_change",
            "old_value": None,
            "new_value": "2025-07-08T05:30:00Z",
            "notification_type": "delayed"
        }
    ]
    
    consolidated = agent._consolidate_ping_pong_changes(changes, trip)
    
    assert len(consolidated) == 0, f"Expected 0 notifications for ping-pong, got {len(consolidated)}"
    print("✅ Simple ping-pong correctly suppressed (0 notifications)")
    
    await agent.close()
    return True

async def test_eta_prioritization_logic():
    """Test ETA prioritization: concrete times over TBD"""
    print("\n🧪 Testing ETA prioritization logic")
    
    agent = NotificationsAgent()
    
    test_cases = [
        # (input, expected_contains)
        ("2025-07-08T05:30:00Z", "02:30"),           # ISO → human readable
        (None, "Por confirmar"),                      # None → fallback
        ("null", "Por confirmar"),                    # null string → fallback
        ("", "Por confirmar"),                        # empty → fallback
        ("already formatted", "already formatted"),   # passthrough
    ]
    
    for input_eta, expected in test_cases:
        result = agent._get_prioritized_eta(input_eta, "EZE")
        assert expected in result, f"Expected '{expected}' in result '{result}' for input '{input_eta}'"
        print(f"  ✅ {input_eta} → {result}")
    
    await agent.close()
    return True

async def test_cooldown_function_exists():
    """Verify cooldown function exists with correct signature"""
    print("\n🧪 Testing cooldown function existence")
    
    agent = NotificationsAgent()
    
    # Verify function exists
    assert hasattr(agent, '_should_send_delay_notification'), "Missing _should_send_delay_notification method"
    
    # Test function signature (should not crash)
    from inspect import signature
    sig = signature(agent._should_send_delay_notification)
    expected_params = ['trip', 'change', 'now_utc']  # 'self' is implicit
    actual_params = list(sig.parameters.keys())
    
    assert actual_params == expected_params, f"Wrong function signature. Expected {expected_params}, got {actual_params}"
    print("  ✅ Cooldown function signature correct")
    
    await agent.close()
    return True

async def main():
    """Run all ping-pong scenario tests"""
    print("🛡️ QA AUDIT: Advanced Ping-Pong Scenario Testing\n")
    
    try:
        # Run all tests
        await test_complex_ping_pong_scenario()
        await test_simple_ping_pong_suppression()
        await test_eta_prioritization_logic()
        await test_cooldown_function_exists()
        
        print("\n🎯 AUDIT RESULT: ALL TESTS PASSED")
        print("✅ Ping-pong consolidation working correctly")
        print("✅ ETA prioritization implemented properly")
        print("✅ Cooldown logic exists and has correct signature")
        print("✅ Complex scenario (02:30 → null → 02:30 → 03:00 → 03:00) produces SINGLE notification")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ AUDIT FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main()) 