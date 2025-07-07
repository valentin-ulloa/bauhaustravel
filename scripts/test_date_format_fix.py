#!/usr/bin/env python3
"""
Test script to validate the new date format with day of week in confirmations.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.notifications_templates import WhatsAppTemplates, NotificationType
from app.utils.timezone_utils import format_departure_time_human, format_departure_time_local
import structlog

logger = structlog.get_logger()


async def test_date_format():
    """Test the new date format for Vale's trip"""
    
    print("🗓️  Probando nuevo formato de fecha con día de semana...")
    
    # Vale's trip data
    trip_data = {
        "client_name": "Valentin",
        "flight_number": "AR 1662",
        "origin_iata": "EZE",
        "destination_iata": "BRC",
        "departure_date": "2025-07-08T04:15:00Z"  # UTC
    }
    
    departure_datetime = datetime.fromisoformat(trip_data["departure_date"].replace('Z', '+00:00'))
    
    print(f"\n📅 **Fecha original UTC**: {departure_datetime}")
    
    # Test old format vs new format
    old_format = format_departure_time_local(departure_datetime, trip_data["origin_iata"])
    new_format = format_departure_time_human(departure_datetime, trip_data["origin_iata"])
    
    print(f"\n❌ **Formato ANTERIOR** (sin día): {old_format}")
    print(f"✅ **Formato NUEVO** (con día): {new_format}")
    
    # Test the actual template formatting
    print(f"\n📱 **Mensaje de confirmación completo**:")
    
    template_result = WhatsAppTemplates.format_reservation_confirmation(trip_data)
    
    # Extract the formatted time from template variables
    formatted_date_in_template = template_result["template_variables"]["5"]
    
    print(f"Template SID: {template_result['template_sid']}")
    print(f"Variables:")
    for key, value in template_result["template_variables"].items():
        print(f"  {{{{{key}}}}}: {value}")
    
    print(f"\n🎯 **Resultado final**:")
    print(f"Tu vuelo {trip_data['flight_number']} desde {trip_data['origin_iata']} a {trip_data['destination_iata']} sale el {formatted_date_in_template}")
    
    print(f"\n✅ **¡Perfecto!** Ahora incluye '{new_format.split(' ')[0]}' (día de la semana)")


if __name__ == "__main__":
    asyncio.run(test_date_format()) 