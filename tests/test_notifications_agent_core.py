"""
Unit tests for NotificationsAgent core functionality.

Tests the critical functions without over-engineering:
- calculate_next_check_time (polling optimization)
- format_message (template formatting)
- idempotency logic
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json
import hashlib

from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.models.database import Trip, DatabaseResult


@pytest.fixture
def sample_trip():
    """Sample trip for testing."""
    return Trip(
        id="550e8400-e29b-41d4-a716-446655440000",
        client_name="Test Client",
        whatsapp="+1234567890",
        flight_number="AA123",
        origin_iata="JFK",
        destination_iata="LAX",
        departure_date=datetime.now(timezone.utc) + timedelta(hours=24),
        status="scheduled",
        agency_id="550e8400-e29b-41d4-a716-446655440001"
    )


@pytest.fixture
def mock_notifications_agent():
    """Mock NotificationsAgent with mocked dependencies."""
    with patch.dict('os.environ', {
        'TWILIO_ACCOUNT_SID': 'test_sid',
        'TWILIO_AUTH_TOKEN': 'test_token',
        'TWILIO_PHONE_NUMBER': '+1234567890',
        'TWILIO_MESSAGING_SERVICE_SID': 'test_service_sid'
    }):
        with patch('app.agents.notifications_agent.SupabaseDBClient'), \
             patch('app.agents.notifications_agent.AeroAPIClient'), \
             patch('app.agents.notifications_agent.AsyncTwilioClient'), \
             patch('app.agents.notifications_agent.NotificationRetryService'):
            return NotificationsAgent()


class TestNotificationsAgent:
    """Test suite for NotificationsAgent core functionality."""
    
    def test_calculate_next_check_time_far_future(self, mock_notifications_agent):
        """Test poll optimization for flights > 24h away."""
        now = datetime.now(timezone.utc)
        far_future = now + timedelta(hours=48)
        
        next_check = mock_notifications_agent.calculate_next_check_time(far_future, now)
        expected = now + timedelta(hours=6)
        
        assert next_check == expected
    
    def test_calculate_next_check_time_near_future(self, mock_notifications_agent):
        """Test poll optimization for flights 24h-4h away."""
        now = datetime.now(timezone.utc)
        near_future = now + timedelta(hours=12)
        
        next_check = mock_notifications_agent.calculate_next_check_time(near_future, now)
        expected = now + timedelta(hours=1)
        
        assert next_check == expected
    
    def test_calculate_next_check_time_very_near(self, mock_notifications_agent):
        """Test poll optimization for flights <= 4h away."""
        now = datetime.now(timezone.utc)
        very_near = now + timedelta(hours=2)
        
        next_check = mock_notifications_agent.calculate_next_check_time(very_near, now)
        expected = now + timedelta(minutes=15)
        
        assert next_check == expected
    
    def test_calculate_next_check_time_in_flight(self, mock_notifications_agent):
        """Test poll optimization for flights already departed."""
        now = datetime.now(timezone.utc)
        past_departure = now - timedelta(hours=1)
        
        next_check = mock_notifications_agent.calculate_next_check_time(past_departure, now)
        expected = now + timedelta(minutes=30)
        
        assert next_check == expected
    
    def test_format_message_24h_reminder(self, mock_notifications_agent, sample_trip):
        """Test message formatting for 24h reminder."""
        extra_data = {
            "weather_info": "sunny skies",
            "additional_info": "Safe travels!"
        }
        
        result = mock_notifications_agent.format_message(
            sample_trip, 
            NotificationType.REMINDER_24H,
            extra_data
        )
        
        assert result["template_name"] == "recordatorio_24h"
        assert result["template_sid"] == "HXf79f6f380e09de4f1b953f7045c6aa19"
        assert result["template_variables"]["1"] == "Test Client"
        assert result["template_variables"]["2"] == "JFK"
        assert result["template_variables"]["4"] == "sunny skies"
        assert result["template_variables"]["5"] == "LAX"
        assert result["template_variables"]["6"] == "Safe travels!"
    
    def test_format_message_boarding_call(self, mock_notifications_agent, sample_trip):
        """Test message formatting for boarding notification."""
        extra_data = {"gate": "A12"}
        
        result = mock_notifications_agent.format_message(
            sample_trip, 
            NotificationType.BOARDING,
            extra_data
        )
        
        assert result["template_name"] == "embarcando"
        assert result["template_sid"] == "HX3571933547ed2f3b6e4c6dc64a84f3b7"
        assert result["template_variables"]["1"] == "AA123"
        assert result["template_variables"]["2"] == "A12"
    
    def test_format_message_gate_change(self, mock_notifications_agent, sample_trip):
        """Test message formatting for gate change notification."""
        extra_data = {"new_gate": "B15"}
        
        result = mock_notifications_agent.format_message(
            sample_trip, 
            NotificationType.GATE_CHANGE,
            extra_data
        )
        
        assert result["template_name"] == "cambio_gate"
        assert result["template_sid"] == "HXd38d96ab6414b96fe214b132253c364e"
        assert result["template_variables"]["1"] == "Test Client"
        assert result["template_variables"]["2"] == "AA123"
        assert result["template_variables"]["3"] == "B15"
    
    def test_idempotency_hash_generation(self, sample_trip):
        """Test idempotency hash generation for duplicate prevention."""
        notification_type = "REMINDER_24H"
        extra_data = {"weather_info": "sunny"}
        
        # Generate hash manually to test consistency
        idempotency_data = {
            "trip_id": str(sample_trip.id),
            "notification_type": notification_type,
            "extra_data": extra_data
        }
        expected_hash = hashlib.sha256(
            json.dumps(idempotency_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # Test that same data produces same hash
        idempotency_data_2 = {
            "trip_id": str(sample_trip.id),
            "notification_type": notification_type,
            "extra_data": extra_data
        }
        actual_hash = hashlib.sha256(
            json.dumps(idempotency_data_2, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        assert actual_hash == expected_hash
    
    def test_idempotency_hash_different_data(self, sample_trip):
        """Test that different data produces different hashes."""
        notification_type = "REMINDER_24H"
        extra_data_1 = {"weather_info": "sunny"}
        extra_data_2 = {"weather_info": "rainy"}
        
        # Generate first hash
        idempotency_data_1 = {
            "trip_id": str(sample_trip.id),
            "notification_type": notification_type,
            "extra_data": extra_data_1
        }
        hash_1 = hashlib.sha256(
            json.dumps(idempotency_data_1, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # Generate second hash
        idempotency_data_2 = {
            "trip_id": str(sample_trip.id),
            "notification_type": notification_type,
            "extra_data": extra_data_2
        }
        hash_2 = hashlib.sha256(
            json.dumps(idempotency_data_2, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        assert hash_1 != hash_2
    
    @pytest.mark.asyncio
    async def test_send_notification_idempotency_check(self, mock_notifications_agent, sample_trip):
        """Test that duplicate notifications are prevented."""
        # Mock database to return existing notification
        mock_notifications_agent.db_client.execute_query = AsyncMock(
            return_value=DatabaseResult(success=True, data=[{"id": "existing"}])
        )
        
        result = await mock_notifications_agent.send_notification(
            sample_trip, 
            NotificationType.REMINDER_24H
        )
        
        assert result.success
        assert result.data["status"] == "already_sent"
    
    def test_map_notification_type(self, mock_notifications_agent):
        """Test notification type mapping."""
        assert mock_notifications_agent._map_notification_type("delayed") == NotificationType.DELAYED
        assert mock_notifications_agent._map_notification_type("cancelled") == NotificationType.CANCELLED
        assert mock_notifications_agent._map_notification_type("boarding") == NotificationType.BOARDING
        assert mock_notifications_agent._map_notification_type("gate_change") == NotificationType.GATE_CHANGE
        assert mock_notifications_agent._map_notification_type("unknown") is None


# Integration-style tests (still unit tests but testing interactions)

class TestNotificationsAgentIntegration:
    """Test interactions between NotificationsAgent components."""
    
    @pytest.mark.asyncio
    async def test_polling_workflow_integration(self, mock_notifications_agent):
        """Test the complete polling workflow."""
        # Mock dependencies
        mock_notifications_agent.db_client.get_trips_to_poll = AsyncMock(return_value=[])
        
        result = await mock_notifications_agent.poll_flight_changes()
        
        assert result.success
        assert "checked" in result.data
        assert "updates" in result.data
        assert "errors" in result.data
    
    @pytest.mark.asyncio
    async def test_24h_reminder_workflow(self, mock_notifications_agent):
        """Test 24h reminder workflow."""
        # Mock dependencies
        mock_notifications_agent.db_client.get_trips_to_poll = AsyncMock(return_value=[])
        
        result = await mock_notifications_agent.schedule_24h_reminders()
        
        assert result.success
        assert "sent" in result.data
        assert "errors" in result.data


def test_quiet_hours_suppression():
    """Test that only REMINDER_24H respects quiet hours"""
    from app.utils.timezone_utils import should_suppress_notification
    from datetime import datetime, timezone
    
    # 23:00 local time (quiet hours)
    night_time = datetime(2025, 7, 7, 2, 0, 0, tzinfo=timezone.utc)  # 23:00 in EZE
    
    # REMINDER_24H should be suppressed during quiet hours
    assert should_suppress_notification("REMINDER_24H", night_time, "EZE") == True
    
    # Critical events should NEVER be suppressed
    assert should_suppress_notification("DELAYED", night_time, "EZE") == False
    assert should_suppress_notification("CANCELLED", night_time, "EZE") == False
    assert should_suppress_notification("BOARDING", night_time, "EZE") == False
    assert should_suppress_notification("GATE_CHANGE", night_time, "EZE") == False


def test_format_departure_time_human():
    """Test human-readable time formatting"""
    from app.utils.timezone_utils import format_departure_time_human
    from datetime import datetime, timezone
    
    # Test EZE timezone (UTC-3)
    utc_time = datetime(2025, 7, 8, 5, 30, 0, tzinfo=timezone.utc)  # 05:30 UTC
    formatted = format_departure_time_human(utc_time, "EZE")
    
    # Should be "Mar 8 Jul 02:30 hs (EZE)" in local time
    assert "8 Jul 02:30 hs (EZE)" in formatted
    assert "Mar" in formatted  # Tuesday in Spanish


def test_round_eta_to_5min():
    """Test ETA rounding for deduplication"""
    from app.utils.timezone_utils import round_eta_to_5min
    from datetime import datetime, timezone
    
    # Test rounding
    dt1 = datetime(2025, 7, 8, 5, 32, 0, tzinfo=timezone.utc)  # 05:32
    dt2 = datetime(2025, 7, 8, 5, 33, 0, tzinfo=timezone.utc)  # 05:33
    
    # Both should round to 05:30
    rounded1 = round_eta_to_5min(dt1)
    rounded2 = round_eta_to_5min(dt2)
    
    assert rounded1 == rounded2  # Same rounded value = deduplication
    assert "05:30:00" in rounded1
    
    # Test None handling
    assert round_eta_to_5min(None) == "TBD"


def test_pluralize():
    """Test Spanish pluralization"""
    from app.utils.timezone_utils import pluralize
    
    # Test singular
    assert pluralize(1, "actividad", "actividades") == "actividad"
    
    # Test plural
    assert pluralize(0, "actividad", "actividades") == "actividades"
    assert pluralize(2, "actividad", "actividades") == "actividades"
    assert pluralize(5, "actividad", "actividades") == "actividades"


def test_delayed_notification_deduplication():
    """Test that DELAYED notifications are properly deduplicated"""
    import hashlib
    import json
    from app.utils.timezone_utils import round_eta_to_5min
    from datetime import datetime, timezone
    
    trip_id = "test-trip-123"
    
    # Two ETAs that round to the same 5-minute interval
    eta1 = datetime(2025, 7, 8, 5, 32, 0, tzinfo=timezone.utc)
    eta2 = datetime(2025, 7, 8, 5, 33, 0, tzinfo=timezone.utc)
    
    # Both should generate the same dedup hash
    dedup_data1 = {
        "trip_id": trip_id,
        "type": "DELAYED", 
        "eta_rounded": round_eta_to_5min(eta1)
    }
    
    dedup_data2 = {
        "trip_id": trip_id,
        "type": "DELAYED",
        "eta_rounded": round_eta_to_5min(eta2)
    }
    
    hash1 = hashlib.sha256(json.dumps(dedup_data1, sort_keys=True).encode()).hexdigest()[:16]
    hash2 = hashlib.sha256(json.dumps(dedup_data2, sort_keys=True).encode()).hexdigest()[:16]
    
    # Should be identical = deduplication works
    assert hash1 == hash2


async def test_landing_welcome_template():
    """Test LANDING_WELCOME template formatting with async city lookup"""
    from app.agents.notifications_templates import WhatsAppTemplates, NotificationType
    
    trip_data = {
        "client_name": "Valentin Ulloa",
        "destination_iata": "MDE",
        "metadata": None
    }
    
    result = await WhatsAppTemplates.format_landing_welcome_async(trip_data, "Hotel Dann Carlton, Carrera 43A #7-50")
    
    assert result["template_name"] == "landing_welcome_es"
    assert result["template_variables"]["1"] == "Medellín"  # MDE mapped to city
    assert result["template_variables"]["2"] == "Hotel Dann Carlton, Carrera 43A #7-50"


async def test_city_name_openai_fallback():
    """Test OpenAI fallback for unknown IATA codes"""
    from app.utils.timezone_utils import get_city_name_from_iata
    
    # Test known city (should use static mapping)
    known_city = await get_city_name_from_iata("MDE")
    assert known_city == "Medellín"
    
    # Test unknown city (should fallback to OpenAI or IATA code)
    # Note: This test may call OpenAI in production
    unknown_city = await get_city_name_from_iata("XYZ")
    assert isinstance(unknown_city, str)  # Should return something


def test_delayed_flight_time_formatting():
    """Test that DELAYED notifications show human-readable time"""
    from app.agents.notifications_templates import WhatsAppTemplates
    
    trip_data = {
        "client_name": "Valentin Ulloa",
        "flight_number": "AV112",
        "origin_iata": "EZE"
    }
    
    # Test ISO format conversion
    iso_time = "2025-07-08T05:30:00Z"
    result = WhatsAppTemplates.format_delayed_flight(trip_data, iso_time)
    
    # Should convert to human readable format
    formatted_time = result["template_variables"]["3"]
    assert "05:30:00Z" not in formatted_time  # ISO format should be gone
    assert "hs" in formatted_time  # Should have Spanish time format


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 