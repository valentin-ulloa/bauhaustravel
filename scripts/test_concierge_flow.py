#!/usr/bin/env python3
"""
Test script for WhatsApp webhook and ConciergeAgent responses.
"""

import requests
import json
from datetime import datetime
import structlog

logger = structlog.get_logger()

# Test configuration
API_BASE_URL = "http://localhost:8000"

def test_concierge_flow(trip_id: str):
    """Test WhatsApp webhook and ConciergeAgent response with unified context."""
    print(f"🧪 Testing ConciergeAgent flow for trip {trip_id}...")

    # Simular payload de WhatsApp webhook
    webhook_data = {
        "To": "whatsapp:+14155238886",  # Twilio sandbox number
        "From": "whatsapp:+5491140383422",
        "Body": "¿Qué tengo para hacer mañana?",
        "MessageSid": "SMXXXXXXXXXXXXXXXXXXXXXXX",
        "NumMedia": "0",
        "Timestamp": datetime.utcnow().isoformat()
    }

    try:
        # Enviar POST al webhook como form-urlencoded
        response = requests.post(
            f"{API_BASE_URL}/webhooks/twilio",
            data=webhook_data,  # form-urlencoded
            timeout=30
        )
        print(f"📊 Status Code: {response.status_code}")
        if response.status_code == 200:
            print("✅ ConciergeAgent responded with valid TwiML.")
            # Verificar que la conversación se guardó
            conv_resp = requests.get(f"{API_BASE_URL}/conversations/{trip_id}")
            if conv_resp.status_code == 200:
                conv_data = conv_resp.json()
                print(f"✅ Conversation log found. Last message: {conv_data[-1]['message']}")
            else:
                print(f"❌ Conversation log not found. Status: {conv_resp.status_code}")
        else:
            print(f"❌ Unexpected status: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error testing ConciergeAgent: {e}")
        logger.error("concierge_flow_test_failed", trip_id=trip_id, error=str(e))

if __name__ == "__main__":
    # Get trip_id from command line or use test value
    import sys
    trip_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not trip_id:
        print("❌ Please provide a trip_id")
        sys.exit(1)
        
    test_concierge_flow(trip_id) 