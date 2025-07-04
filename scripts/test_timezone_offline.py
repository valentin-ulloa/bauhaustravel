#!/usr/bin/env python3
"""
Quick Timezone Test (Offline) - No Database Required
Tests timezone logic without connecting to Supabase
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

def test_timezone_logic():
    """Test current quiet hours logic vs correct timezone logic"""
    
    print("🕐 **QUICK TIMEZONE VALIDATION**")
    print("="*50)
    
    # Current time
    now_utc = datetime.now(timezone.utc)
    current_hour_utc = now_utc.hour
    
    print(f"Current UTC time: {now_utc.strftime('%H:%M')} (hour: {current_hour_utc})")
    print(f"Current UTC quiet hours: {'YES' if (current_hour_utc < 9 or current_hour_utc >= 20) else 'NO'}")
    
    # Airport timezone mapping
    AIRPORT_TIMEZONES = {
        'GRU': 'America/Sao_Paulo',      # São Paulo UTC-3
        'EZE': 'America/Argentina/Buenos_Aires',  # Buenos Aires UTC-3
        'MIA': 'America/New_York',       # Miami UTC-5 (EST)
        'MEX': 'America/Mexico_City',    # Mexico City UTC-6
        'MAD': 'Europe/Madrid',          # Madrid UTC+1
        'DXB': 'Asia/Dubai',             # Dubai UTC+4
        'NRT': 'Asia/Tokyo',             # Tokyo UTC+9
    }
    
    print("\n🌍 **TIMEZONE COMPARISON:**")
    problems_found = 0
    
    for airport, tz_name in AIRPORT_TIMEZONES.items():
        try:
            tz = ZoneInfo(tz_name)
            local_time = now_utc.astimezone(tz)
            local_hour = local_time.hour
            
            is_quiet_local = local_hour < 9 or local_hour >= 20
            is_quiet_utc = current_hour_utc < 9 or current_hour_utc >= 20
            
            if is_quiet_local != is_quiet_utc:
                problems_found += 1
                print(f"  ⚠️  {airport}: {local_time.strftime('%H:%M %Z')} | Local quiet: {is_quiet_local} | UTC quiet: {is_quiet_utc} | ❌ MISMATCH")
            else:
                print(f"  ✅ {airport}: {local_time.strftime('%H:%M %Z')} | Quiet hours match")
                
        except Exception as e:
            print(f"  ❌ {airport}: Error - {e}")
    
    print(f"\n📊 **RESULTS:**")
    print(f"  Airports tested: {len(AIRPORT_TIMEZONES)}")
    print(f"  Timezone mismatches: {problems_found}")
    
    if problems_found > 0:
        print(f"\n🔴 **CRITICAL ISSUE CONFIRMED**")
        print(f"  {problems_found} airports have incorrect quiet hours!")
        print(f"  Clients in those timezones could get notifications at wrong times")
        print(f"\n📋 **IMMEDIATE FIX NEEDED:**")
        print(f"  1. Modify notifications_agent.py line ~206")  
        print(f"  2. Add timezone conversion based on origin_iata")
        print(f"  3. Use local airport time instead of UTC")
    else:
        print(f"\n✅ **NO TIMEZONE ISSUES FOUND**")
        print(f"  Current UTC-based logic happens to work at this time")
    
    # Test specific problem scenario
    print(f"\n🚨 **CRITICAL SCENARIO TEST:**")
    print(f"Mexico City client (MEX airport):")
    
    mex_tz = ZoneInfo('America/Mexico_City')
    mex_time = now_utc.astimezone(mex_tz)
    
    # Simulate 10 PM Mexico time (should be quiet)
    mex_test_time = mex_time.replace(hour=22, minute=0)  # 10 PM Mexico
    mex_test_utc = mex_test_time.astimezone(timezone.utc)
    
    utc_hour_at_mex_10pm = mex_test_utc.hour
    would_send_utc = not (utc_hour_at_mex_10pm < 9 or utc_hour_at_mex_10pm >= 20)
    should_send_local = False  # 10 PM is quiet hours
    
    print(f"  10 PM Mexico time = {mex_test_utc.strftime('%H:%M UTC')}")
    print(f"  Current system would send: {'YES' if would_send_utc else 'NO'}")
    print(f"  Should send (correct): {'YES' if should_send_local else 'NO'}")
    
    if would_send_utc != should_send_local:
        print(f"  🔴 **BUG CONFIRMED**: Would send notification at 10 PM local time!")
    else:
        print(f"  ✅ This specific case works correctly")

if __name__ == "__main__":
    test_timezone_logic() 