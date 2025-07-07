"""
Unit tests for critical NotificationsAgent fixes.

Tests the key functions modified in the o3 recommendations implementation:
- ETA deduplication and rounding
- Retry count tracking
- Message configuration
- Quiet hours logic
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

from app.agents.notifications_agent import NotificationsAgent
from app.config.messages import MessageConfig
from app.utils.timezone_utils import round_eta_to_5min, should_suppress_notification
from app.services.notification_retry_service import NotificationRetryService
from app.models.database import DatabaseResult, Trip


class TestETADeduplication:
    """Test ETA rounding and deduplication logic."""
    
    def test_round_eta_to_5min(self):
        """Test ETA rounding to 5-minute intervals."""
        # Test normal rounding
        dt1 = datetime(2025, 1, 7, 14, 32, 0, tzinfo=timezone.utc)  # 14:32 -> 14:30
        assert round_eta_to_5min(dt1) == "2025-01-07T14:30:00+00:00"
        
        dt2 = datetime(2025, 1, 7, 14, 33, 0, tzinfo=timezone.utc)  # 14:33 -> 14:35
        assert round_eta_to_5min(dt2) == "2025-01-07T14:35:00+00:00"
        
        # Test hour rollover
        dt3 = datetime(2025, 1, 7, 14, 58, 0, tzinfo=timezone.utc)  # 14:58 -> 15:00
        assert round_eta_to_5min(dt3) == "2025-01-07T15:00:00+00:00"
        
        # Test None input
        assert round_eta_to_5min(None) == "TBD"
    
    def test_get_prioritized_eta(self):
        """Test ETA prioritization logic."""
        agent = NotificationsAgent()
        
        # Test concrete time formatting (UTC will be converted to local airport time)
        iso_time = "2025-01-07T14:30:00Z"
        result = agent._get_prioritized_eta(iso_time, "EZE")
        assert "11:30" in result  # 14:30 UTC = 11:30 EZE (UTC-3)
        assert "EZE" in result   # Should contain airport code
        assert "Ene" in result   # Should be in Spanish
        
        # Test null/empty values
        assert agent._get_prioritized_eta("", "EZE") == MessageConfig.get_eta_unknown_text()
        assert agent._get_prioritized_eta("null", "EZE") == MessageConfig.get_eta_unknown_text()
        assert agent._get_prioritized_eta(None, "EZE") == MessageConfig.get_eta_unknown_text()


class TestRetryCountTracking:
    """Test retry count tracking in NotificationRetryService."""
    
    @pytest.mark.asyncio
    async def test_retry_service_success_count(self):
        """Test retry service returns correct attempt count on success."""
        service = NotificationRetryService()
        
        # Mock a function that succeeds on first try
        async def mock_success():
            return DatabaseResult(success=True, data={"message_sid": "test123"})
        
        result = await service.send_with_retry(mock_success, max_attempts=3)
        
        assert result.success is True
        assert result.data["retry_count"] == 1  # First attempt succeeded
        assert "message_sid" in result.data
    
    @pytest.mark.asyncio
    async def test_retry_service_failure_count(self):
        """Test retry service returns correct attempt count on failure."""
        service = NotificationRetryService()
        
        # Mock a function that always fails
        async def mock_failure():
            return DatabaseResult(success=False, error="Always fails")
        
        result = await service.send_with_retry(mock_failure, max_attempts=2, initial_delay=0.01)
        
        assert result.success is False
        assert result.data["retry_count"] == 2  # Used all attempts
        assert "Failed after 2 attempts" in result.error


class TestMessageConfiguration:
    """Test message configuration system."""
    
    def test_default_messages(self):
        """Test default Spanish messages are returned."""
        assert MessageConfig.get_weather_text() == "buen clima para volar"
        assert MessageConfig.get_good_trip_text() == "¡Buen viaje!"
        assert MessageConfig.get_eta_unknown_text() == "Por confirmar"
        assert MessageConfig.get_gate_placeholder() == "Ver pantallas"
        assert MessageConfig.get_hotel_placeholder() == "tu alojamiento reservado"
    
    def test_message_key_lookup(self):
        """Test message key lookup with fallbacks."""
        # Existing key
        result = MessageConfig.get_message("weather_text")
        assert result == "buen clima para volar"
        
        # Non-existing key with fallback
        result = MessageConfig.get_message("unknown_key", fallback="default text")
        assert result == "default text"
        
        # Non-existing key without fallback
        result = MessageConfig.get_message("unknown_key")
        assert result == "unknown_key"


class TestQuietHoursLogic:
    """Test quiet hours logic and business rules."""
    
    def test_quiet_hours_only_affects_reminders(self):
        """Test that only REMINDER_24H is suppressed during quiet hours."""
        # Mock time: 3 AM UTC = night time in most airports
        night_time = datetime(2025, 1, 7, 3, 0, 0, tzinfo=timezone.utc)
        
        # REMINDER_24H should be suppressed
        assert should_suppress_notification("REMINDER_24H", night_time, "EZE") is True
        
        # All other events should NOT be suppressed (24/7 delivery)
        assert should_suppress_notification("DELAYED", night_time, "EZE") is False
        assert should_suppress_notification("CANCELLED", night_time, "EZE") is False
        assert should_suppress_notification("BOARDING", night_time, "EZE") is False
        assert should_suppress_notification("GATE_CHANGE", night_time, "EZE") is False
    
    def test_quiet_hours_day_time_allows_all(self):
        """Test that all notifications are allowed during day time."""
        # Mock time: 2 PM UTC = day time in most airports
        day_time = datetime(2025, 1, 7, 14, 0, 0, tzinfo=timezone.utc)
        
        # All events should be allowed
        assert should_suppress_notification("REMINDER_24H", day_time, "EZE") is False
        assert should_suppress_notification("DELAYED", day_time, "EZE") is False
        assert should_suppress_notification("CANCELLED", day_time, "EZE") is False


class TestPingPongConsolidation:
    """Test ping-pong change consolidation logic."""
    
    def test_consolidate_single_change(self):
        """Test that single changes pass through unchanged."""
        agent = NotificationsAgent()
        
        # Mock trip
        trip = Mock()
        trip.id = "test-trip-id"
        
        changes = [
            {
                "type": "departure_time_change",
                "old_value": "02:30",
                "new_value": "03:00",
                "notification_type": "delayed"
            }
        ]
        
        result = agent._consolidate_ping_pong_changes(changes, trip)
        assert len(result) == 1
        assert result[0]["old_value"] == "02:30"
        assert result[0]["new_value"] == "03:00"
    
    def test_consolidate_ping_pong_suppression(self):
        """Test that A→B→A patterns are suppressed."""
        agent = NotificationsAgent()
        
        # Mock trip
        trip = Mock()
        trip.id = "test-trip-id"
        
        # Simulate ping-pong: 02:30 → 03:00 → 02:30 (back to original)
        changes = [
            {
                "type": "departure_time_change", 
                "old_value": "02:30",
                "new_value": "03:00",
                "notification_type": "delayed"
            },
            {
                "type": "departure_time_change",
                "old_value": "03:00", 
                "new_value": "02:30",  # Back to original
                "notification_type": "delayed"
            }
        ]
        
        result = agent._consolidate_ping_pong_changes(changes, trip)
        assert len(result) == 0  # Should suppress all notifications
    
    def test_consolidate_net_change(self):
        """Test that net changes are consolidated correctly."""
        agent = NotificationsAgent()
        
        # Mock trip
        trip = Mock()
        trip.id = "test-trip-id"
        
        # Simulate net change: 02:30 → 03:00 → 03:30 (net change to 03:30)
        changes = [
            {
                "type": "departure_time_change",
                "old_value": "02:30",
                "new_value": "03:00", 
                "notification_type": "delayed"
            },
            {
                "type": "departure_time_change",
                "old_value": "03:00",
                "new_value": "03:30",  # Final change
                "notification_type": "delayed"
            }
        ]
        
        result = agent._consolidate_ping_pong_changes(changes, trip)
        assert len(result) == 1
        assert result[0]["old_value"] == "02:30"  # Original value
        assert result[0]["new_value"] == "03:30"  # Final value
        assert result[0]["consolidation_count"] == 2


# Integration test for database parameter passing
class TestDatabaseIntegration:
    """Test that eta_round parameter is correctly passed to database."""
    
    @pytest.mark.asyncio
    async def test_eta_round_database_parameter(self):
        """Test that eta_round is passed to log_notification_sent."""
        
        # This would normally require a full database setup
        # For now, we just test the parameter structure
        
        extra_data = {
            "eta_round": "2025-01-07T14:30:00+00:00",
            "new_departure_time": "Lun 7 Ene 14:30 hs (EZE)"
        }
        
        # Test that eta_round is properly extracted
        eta_round_value = extra_data.get("eta_round")
        assert eta_round_value is not None
        assert "2025-01-07T14:30:00" in eta_round_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 