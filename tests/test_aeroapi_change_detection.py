"""
Test cases for AeroAPI change detection and status mapping fixes.

Validates that the NotificationsAgent correctly handles:
1. Status mapping (Scheduled should NOT trigger delayed notifications)
2. Departure time changes (NULL->Time should NOT trigger delayed notifications)
3. Real delay detection (only actual delays trigger notifications)
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.services.aeroapi_client import AeroAPIClient, FlightStatus


class TestStatusMapping:
    """Test the _map_status_to_notification method fixes"""
    
    def setup_method(self):
        self.client = AeroAPIClient()
    
    def test_scheduled_status_no_notification(self):
        """CRITICAL: Scheduled status should NOT trigger delayed notification"""
        result = self.client._map_status_to_notification("Scheduled")
        assert result == "no_notification", "Scheduled flights should not trigger notifications"
    
    def test_on_time_status_no_notification(self):
        """On Time status should NOT trigger notification"""
        result = self.client._map_status_to_notification("On Time")
        assert result == "no_notification"
    
    def test_taxiing_status_no_notification(self):
        """Taxiing status should NOT trigger notification"""
        result = self.client._map_status_to_notification("Taxiing")
        assert result == "no_notification"
    
    def test_unknown_status_no_notification(self):
        """Unknown status should NOT trigger notification"""
        result = self.client._map_status_to_notification("Unknown")
        assert result == "no_notification"
    
    def test_delayed_status_triggers_notification(self):
        """Delayed status SHOULD trigger delayed notification"""
        result = self.client._map_status_to_notification("Delayed")
        assert result == "delayed"
    
    def test_cancelled_status_triggers_notification(self):
        """Cancelled status SHOULD trigger cancelled notification"""
        result = self.client._map_status_to_notification("Cancelled")
        assert result == "cancelled"
    
    def test_boarding_status_triggers_notification(self):
        """Boarding status SHOULD trigger boarding notification"""
        result = self.client._map_status_to_notification("Boarding")
        assert result == "boarding"
    
    def test_case_insensitive_mapping(self):
        """Status mapping should be case insensitive"""
        assert self.client._map_status_to_notification("SCHEDULED") == "no_notification"
        assert self.client._map_status_to_notification("delayed") == "delayed"
        assert self.client._map_status_to_notification("CaNcElLeD") == "cancelled"
    
    def test_unknown_weird_status_logs_warning(self):
        """Unknown weird status should log warning but not trigger notification"""
        result = self.client._map_status_to_notification("WeirdUnknownStatus123")
        assert result == "no_notification"


class TestDelayDetection:
    """Test the _is_actual_delay method logic"""
    
    def setup_method(self):
        self.client = AeroAPIClient()
        self.base_time = datetime(2024, 7, 8, 2, 30, 0, tzinfo=timezone.utc)
    
    def test_null_to_time_not_delay(self):
        """NULL -> Time is initial scheduling, NOT a delay"""
        is_delay = self.client._is_actual_delay(
            previous_estimated=None,
            current_estimated="2024-07-08T02:30:00Z",
            current_status="Scheduled"
        )
        assert not is_delay, "Initial scheduling should not be considered a delay"
    
    def test_early_departure_not_delay(self):
        """Earlier time is early departure, NOT a delay"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="2024-07-08T02:30:00Z",
            current_estimated="2024-07-08T02:15:00Z",  # 15 minutes earlier
            current_status="Scheduled"
        )
        assert not is_delay, "Early departure should not be considered a delay"
    
    def test_minimal_change_not_delay(self):
        """Small time changes (< 5 minutes) should NOT trigger delay"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="2024-07-08T02:30:00Z",
            current_estimated="2024-07-08T02:33:00Z",  # 3 minutes later
            current_status="Scheduled"
        )
        assert not is_delay, "Minimal time changes should not trigger delays"
    
    def test_confirmed_delay_by_status(self):
        """Delay confirmed by status should trigger notification"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="2024-07-08T02:30:00Z",
            current_estimated="2024-07-08T02:45:00Z",  # 15 minutes later
            current_status="Delayed"
        )
        assert is_delay, "Status-confirmed delays should trigger notification"
    
    def test_significant_delay_without_status_change(self):
        """Significant delay (>= 15 minutes) should trigger even without status change"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="2024-07-08T02:30:00Z",
            current_estimated="2024-07-08T02:50:00Z",  # 20 minutes later
            current_status="Scheduled"  # Status not updated yet
        )
        assert is_delay, "Significant delays should trigger even without status confirmation"
    
    def test_moderate_delay_waits_for_confirmation(self):
        """Moderate delay (5-15 min) without status confirmation should wait"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="2024-07-08T02:30:00Z",
            current_estimated="2024-07-08T02:40:00Z",  # 10 minutes later
            current_status="Scheduled"  # No delay status yet
        )
        assert not is_delay, "Moderate delays should wait for status confirmation"
    
    def test_invalid_time_format_no_delay(self):
        """Invalid time format should not trigger delay (conservative approach)"""
        is_delay = self.client._is_actual_delay(
            previous_estimated="invalid-time",
            current_estimated="2024-07-08T02:30:00Z",
            current_status="Scheduled"
        )
        assert not is_delay, "Invalid time formats should not trigger delays"


class TestChangeDetection:
    """Test the detect_flight_changes method with fixes"""
    
    def setup_method(self):
        self.client = AeroAPIClient()
    
    def test_scheduled_status_change_no_notification(self):
        """Status change TO Scheduled should NOT create notification event"""
        previous = FlightStatus(ident="AA123", status="Unknown")
        current = FlightStatus(ident="AA123", status="Scheduled")
        
        changes = self.client.detect_flight_changes(current, previous)
        
        assert len(changes) == 0, "Status change to Scheduled should not create notification"
    
    def test_scheduled_to_delayed_creates_notification(self):
        """Status change FROM Scheduled TO Delayed should create notification"""
        previous = FlightStatus(ident="AA123", status="Scheduled")
        current = FlightStatus(ident="AA123", status="Delayed")
        
        changes = self.client.detect_flight_changes(current, previous)
        
        assert len(changes) == 1
        assert changes[0]["type"] == "status_change"
        assert changes[0]["notification_type"] == "delayed"
    
    def test_initial_estimated_out_no_delay_notification(self):
        """Initial estimated_out assignment should NOT create delay notification"""
        previous = FlightStatus(ident="AA123", status="Scheduled", estimated_out=None)
        current = FlightStatus(ident="AA123", status="Scheduled", estimated_out="2024-07-08T02:30:00Z")
        
        changes = self.client.detect_flight_changes(current, previous)
        
        # Should not have any departure_time_change events
        departure_changes = [c for c in changes if c["type"] == "departure_time_change"]
        assert len(departure_changes) == 0, "Initial estimated_out should not trigger delay"
    
    def test_real_delay_creates_notification(self):
        """Real delay (confirmed by status or significant time change) should create notification"""
        previous = FlightStatus(ident="AA123", status="Scheduled", estimated_out="2024-07-08T02:30:00Z")
        current = FlightStatus(ident="AA123", status="Delayed", estimated_out="2024-07-08T02:45:00Z")
        
        changes = self.client.detect_flight_changes(current, previous)
        
        # Should have both status change and departure time change
        status_changes = [c for c in changes if c["type"] == "status_change"]
        departure_changes = [c for c in changes if c["type"] == "departure_time_change"]
        
        assert len(status_changes) == 1
        assert len(departure_changes) == 1
        assert status_changes[0]["notification_type"] == "delayed"
        assert departure_changes[0]["notification_type"] == "delayed"
    
    def test_gate_change_creates_notification(self):
        """Gate changes should still create notifications"""
        previous = FlightStatus(ident="AA123", status="Scheduled", gate_origin="A1")
        current = FlightStatus(ident="AA123", status="Scheduled", gate_origin="B2")
        
        changes = self.client.detect_flight_changes(current, previous)
        
        assert len(changes) == 1
        assert changes[0]["type"] == "gate_change"
        assert changes[0]["notification_type"] == "gate_change"


class TestProductionScenarios:
    """Test real-world scenarios that caused the production issue"""
    
    def setup_method(self):
        self.client = AeroAPIClient()
    
    def test_vale_production_scenario(self):
        """
        Test the exact scenario Vale experienced:
        1. Trip created with departure_date but no estimated_out in DB
        2. AeroAPI returns flight with estimated_out = "Scheduled"
        3. This should NOT trigger a delayed notification
        """
        # Simulate what's likely in DB for a new trip (no previous flight status)
        previous = None
        
        # Simulate AeroAPI response 
        current = FlightStatus(
            ident="AR1234", 
            status="Scheduled",
            estimated_out="2024-07-08T02:30:00Z"
        )
        
        changes = self.client.detect_flight_changes(current, previous)
        
        # With no previous status, should not detect any changes
        assert len(changes) == 0, "No previous status should not trigger any changes"
    
    def test_database_vs_aeroapi_initial_comparison(self):
        """
        Test when we compare DB trip data vs first AeroAPI call
        """
        # Simulate trip data from database (status="Scheduled", no estimated_out)
        previous = FlightStatus(
            ident="AR1234",
            status="Scheduled", 
            estimated_out=None  # Not set in DB yet
        )
        
        # Simulate first AeroAPI response
        current = FlightStatus(
            ident="AR1234",
            status="Scheduled",
            estimated_out="2024-07-08T02:30:00Z"
        )
        
        changes = self.client.detect_flight_changes(current, previous)
        
        # Should NOT create delay notification for initial time assignment
        delay_changes = [c for c in changes if c.get("notification_type") == "delayed"]
        assert len(delay_changes) == 0, "Initial estimated_out assignment should not trigger delay"
    
    def test_ping_pong_scenario_prevention(self):
        """
        Test that ping-pong scenarios are properly handled
        """
        # Previous: estimated_out = "02:30"
        previous = FlightStatus(
            ident="AR1234",
            status="Scheduled",
            estimated_out="2024-07-08T02:30:00Z"
        )
        
        # Current: estimated_out changes to "Scheduled" (weird AeroAPI response)
        current = FlightStatus(
            ident="AR1234", 
            status="Scheduled",
            estimated_out="Scheduled"  # This is weird but could happen
        )
        
        changes = self.client.detect_flight_changes(current, previous)
        
        # Should not trigger delay because it's not a proper time format
        delay_changes = [c for c in changes if c.get("notification_type") == "delayed"]
        assert len(delay_changes) == 0, "Invalid estimated_out format should not trigger delay"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"]) 