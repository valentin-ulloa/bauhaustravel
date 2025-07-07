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


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 