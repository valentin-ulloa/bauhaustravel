"""Tests for SupabaseDBClient."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from app.db.supabase_client import SupabaseDBClient


class TestSupabaseDBClient:
    """Test cases for SupabaseDBClient."""
    
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-key"
    })
    def test_client_initialization(self):
        """Test client initializes with proper environment variables."""
        client = SupabaseDBClient()
        assert client.base_url == "https://test.supabase.co"
        assert client.service_key == "test-key"
        assert client.rest_url == "https://test.supabase.co/rest/v1"
    
    def test_client_initialization_missing_env(self):
        """Test client raises error when environment variables are missing."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"):
                SupabaseDBClient()
    
    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-key"
    })
    @pytest.mark.asyncio
    async def test_get_trips_to_poll_success(self):
        """Test successful trips query."""
        client = SupabaseDBClient()
        
        # Mock the HTTP client
        mock_response = AsyncMock()
        mock_response.json.return_value = [
            {
                "id": str(uuid4()),
                "client_name": "Test Client",
                "whatsapp": "+1234567890",
                "flight_number": "AA123",
                "origin_iata": "JFK",
                "destination_iata": "LAX",
                "departure_date": "2024-01-01T10:00:00Z",
                "status": "SCHEDULED",
                "metadata": {},
                "inserted_at": "2024-01-01T08:00:00Z",
                "next_check_at": "2024-01-01T09:00:00Z",
                "client_description": "Test trip"
            }
        ]
        mock_response.raise_for_status = AsyncMock()
        
        with patch.object(client._client, 'get', return_value=mock_response):
            now_utc = datetime.now(timezone.utc)
            trips = await client.get_trips_to_poll(now_utc)
            
            assert len(trips) == 1
            assert trips[0].client_name == "Test Client"
            assert trips[0].flight_number == "AA123"
        
        await client.close()


# Integration test placeholder (requires actual Supabase connection)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_supabase_integration():
    """
    Integration test - requires actual Supabase credentials.
    Run with: pytest -m integration
    """
    # This test would require real environment variables
    # and would test against actual Supabase instance
    pass 