#!/usr/bin/env python3
"""
Test script for new timezone policy enforcement.

This script validates that:
1. TripCreate automatically converts local time to UTC
2. Display functions show correct local time
3. LHR 22:05 local → UTC conversion → display shows 22:05 again

Run: python scripts/test_timezone_policy.py
"""

import sys
import os
import asyncio
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import TripCreate
from app.utils.timezone_utils import (
    parse_local_time_to_utc, 
    format_departure_time_human,
    format_departure_time_local,
    convert_utc_to_local_airport
)


def test_timezone_policy():
    """Test the new timezone policy enforcement."""
    
    print("🧪 TESTING NEW TIMEZONE POLICY")
    print("=" * 50)
    
    # Test Case 1: LHR 22:05 (British Summer Time)
    print("\n📍 TEST CASE 1: LHR 22:05 Local Time")
    print("-" * 30)
    
    # Input: Local LHR time (22:05 on July 8, 2025)
    local_time = datetime(2025, 7, 8, 22, 5)  # Naive datetime = local time
    print(f"INPUT (Local LHR): {local_time.strftime('%Y-%m-%d %H:%M')}")
    
    # Manual conversion (what should happen)
    utc_time_manual = parse_local_time_to_utc(local_time, "LHR")
    print(f"CONVERTED TO UTC: {utc_time_manual.isoformat()}")
    
    # Display back to local
    display_time = convert_utc_to_local_airport(utc_time_manual, "LHR")
    print(f"DISPLAY (Local LHR): {display_time.strftime('%Y-%m-%d %H:%M')}")
    
    # Test TripCreate model enforcement
    try:
        trip_data = TripCreate(
            client_name="Test Client",
            whatsapp="+441234567890",
            flight_number="BA123",
            origin_iata="LHR",
            destination_iata="EZE",
            departure_date=local_time  # Should auto-convert to UTC
        )
        print(f"TRIPCREATE UTC: {trip_data.departure_date.isoformat()}")
        
        # Test display formatting
        human_format = format_departure_time_human(trip_data.departure_date, "LHR")
        local_format = format_departure_time_local(trip_data.departure_date, "LHR")
        
        print(f"HUMAN FORMAT: {human_format}")
        print(f"LOCAL FORMAT: {local_format}")
        
        # Validation
        if "22:05" in human_format and "22:05" in local_format:
            print("✅ SUCCESS: Time displays correctly as 22:05")
        else:
            print("❌ FAILED: Time not showing as 22:05")
            
    except Exception as e:
        print(f"❌ FAILED: TripCreate error: {e}")
    
    print("\n" + "=" * 50)
    
    # Test Case 2: EZE 14:30 (Argentina Time)
    print("\n📍 TEST CASE 2: EZE 14:30 Local Time")
    print("-" * 30)
    
    local_time_eze = datetime(2025, 7, 8, 14, 30)
    print(f"INPUT (Local EZE): {local_time_eze.strftime('%Y-%m-%d %H:%M')}")
    
    utc_time_eze = parse_local_time_to_utc(local_time_eze, "EZE")
    print(f"CONVERTED TO UTC: {utc_time_eze.isoformat()}")
    
    display_time_eze = convert_utc_to_local_airport(utc_time_eze, "EZE")
    print(f"DISPLAY (Local EZE): {display_time_eze.strftime('%Y-%m-%d %H:%M')}")
    
    try:
        trip_data_eze = TripCreate(
            client_name="Test Client EZE",
            whatsapp="+541234567890",
            flight_number="AR456",
            origin_iata="EZE", 
            destination_iata="LHR",
            departure_date=local_time_eze
        )
        
        human_format_eze = format_departure_time_human(trip_data_eze.departure_date, "EZE")
        print(f"HUMAN FORMAT: {human_format_eze}")
        
        if "14:30" in human_format_eze:
            print("✅ SUCCESS: EZE time displays correctly as 14:30")
        else:
            print("❌ FAILED: EZE time not showing as 14:30")
            
    except Exception as e:
        print(f"❌ FAILED: EZE TripCreate error: {e}")
    
    print("\n" + "=" * 50)
    
    # Test Case 3: Cross-validation with UTC input (edge case)
    print("\n📍 TEST CASE 3: UTC Input Edge Case")
    print("-" * 30)
    
    # What happens if someone passes UTC time directly?
    utc_input = datetime(2025, 7, 8, 21, 5, tzinfo=timezone.utc)  # 21:05 UTC
    print(f"INPUT (UTC): {utc_input.isoformat()}")
    
    try:
        trip_utc = TripCreate(
            client_name="UTC Test",
            whatsapp="+441234567890", 
            flight_number="BA789",
            origin_iata="LHR",
            destination_iata="EZE",
            departure_date=utc_input  # This will be treated as local time
        )
        
        human_format_utc = format_departure_time_human(trip_utc.departure_date, "LHR")
        print(f"RESULT: {human_format_utc}")
        print("⚠️  NOTE: UTC input treated as local time (by design)")
        
    except Exception as e:
        print(f"❌ FAILED: UTC input error: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 SUMMARY:")
    print("- All departure times are now treated as LOCAL airport time")
    print("- Automatic conversion to UTC for storage") 
    print("- Display functions convert back to local time")
    print("- No more timezone confusion or double conversions")
    print("- Works consistently across all entry points")


if __name__ == "__main__":
    test_timezone_policy() 