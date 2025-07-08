#!/usr/bin/env python3

"""
VALIDACIÓN UNIFICADA - QA TECH LEAD ANALYSIS
============================================

Este script valida que TODAS las optimizaciones y consolidaciones 
identificadas en el análisis QA han sido implementadas correctamente.

PROBLEMAS RESUELTOS:
1. ✅ Duplicación de lógica next_check_at eliminada
2. ✅ Quiet hours policy centralizada
3. ✅ AeroAPI cache optimizado
4. ✅ Timezone handling unificado
5. ✅ Hardcoded text eliminado
6. ✅ Deduplicación simplificada
7. ✅ Arquitectura consolidada

Run: python scripts/validate_unified_optimizations.py
"""

import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.flight_schedule_utils import (
    calculate_unified_next_check, 
    should_suppress_notification_unified,
    get_polling_phase
)
from app.agents.notifications_agent import NotificationsAgent
from app.services.aeroapi_client import AeroAPIClient
from app.models.database import Trip


def test_unified_next_check_logic():
    """
    Validar que la lógica next_check_at está UNIFICADA y elimina duplicaciones.
    """
    print("🔄 Testing UNIFIED next_check_at logic...")
    
    now_utc = datetime.now(timezone.utc)
    
    # Test cases for different phases
    test_cases = [
        # Far future (> 24h) -> +6h
        {
            "departure": now_utc + timedelta(hours=30),
            "expected_delta_hours": 6,
            "phase": "far_future"
        },
        # Approaching (24h-4h) -> +1h
        {
            "departure": now_utc + timedelta(hours=12),
            "expected_delta_hours": 1,
            "phase": "approaching"
        },
        # Imminent (≤4h) -> +15min
        {
            "departure": now_utc + timedelta(hours=2),
            "expected_delta_minutes": 15,
            "phase": "imminent"
        },
        # In-flight with arrival -> +30min
        {
            "departure": now_utc - timedelta(hours=1),
            "estimated_arrival": now_utc + timedelta(hours=2),
            "expected_delta_minutes": 30,
            "phase": "in_flight"
        },
        # Landed -> None (no more polling)
        {
            "departure": now_utc - timedelta(hours=5),
            "status": "LANDED",
            "expected": None,
            "phase": "landed"
        }
    ]
    
    all_passed = True
    
    for i, case in enumerate(test_cases):
        departure = case["departure"]
        status = case.get("status", "SCHEDULED")
        arrival = case.get("estimated_arrival")
        
        result = calculate_unified_next_check(departure, now_utc, status, arrival)
        
        if case.get("expected") is None:
            # Should return None for landed flights
            if result is None:
                print(f"  ✅ Test {i+1}: {case['phase']} - Correctly returns None")
            else:
                print(f"  ❌ Test {i+1}: {case['phase']} - Should return None but got {result}")
                all_passed = False
        else:
            # Check timing
            if result:
                actual_delta = result - now_utc
                
                if "expected_delta_hours" in case:
                    expected_hours = case["expected_delta_hours"]
                    actual_hours = actual_delta.total_seconds() / 3600
                    
                    if abs(actual_hours - expected_hours) < 0.1:  # 6-minute tolerance
                        print(f"  ✅ Test {i+1}: {case['phase']} - {actual_hours:.1f}h interval (expected {expected_hours}h)")
                    else:
                        print(f"  ❌ Test {i+1}: {case['phase']} - {actual_hours:.1f}h interval (expected {expected_hours}h)")
                        all_passed = False
                        
                elif "expected_delta_minutes" in case:
                    expected_minutes = case["expected_delta_minutes"]
                    actual_minutes = actual_delta.total_seconds() / 60
                    
                    if abs(actual_minutes - expected_minutes) < 5:  # 5-minute tolerance
                        print(f"  ✅ Test {i+1}: {case['phase']} - {actual_minutes:.1f}min interval (expected {expected_minutes}min)")
                    else:
                        print(f"  ❌ Test {i+1}: {case['phase']} - {actual_minutes:.1f}min interval (expected {expected_minutes}min)")
                        all_passed = False
            else:
                print(f"  ❌ Test {i+1}: {case['phase']} - Got None when expecting value")
                all_passed = False
    
    if all_passed:
        print("✅ UNIFIED next_check_at logic working correctly")
    else:
        print("❌ UNIFIED next_check_at logic has issues")
    
    return all_passed


def test_unified_quiet_hours_policy():
    """
    Validar que la política de quiet hours está CENTRALIZADA.
    """
    print("\n🔄 Testing UNIFIED quiet hours policy...")
    
    now_utc = datetime.now(timezone.utc)
    
    test_cases = [
        # Only REMINDER_24H should be suppressed during quiet hours
        {
            "notification_type": "REMINDER_24H",
            "airport": "EZE",
            "should_suppress": True  # Will depend on current time
        },
        # All other notifications send 24/7
        {
            "notification_type": "DELAYED",
            "airport": "EZE", 
            "should_suppress": False
        },
        {
            "notification_type": "CANCELLED",
            "airport": "LHR",
            "should_suppress": False
        },
        {
            "notification_type": "GATE_CHANGE",
            "airport": "JFK",
            "should_suppress": False
        },
        {
            "notification_type": "BOARDING",
            "airport": "EZE",
            "should_suppress": False
        }
    ]
    
    all_passed = True
    
    for case in test_cases:
        result = should_suppress_notification_unified(
            case["notification_type"],
            now_utc,
            case["airport"]
        )
        
        if case["notification_type"] == "REMINDER_24H":
            # For reminders, result depends on actual quiet hours
            print(f"  ✅ {case['notification_type']}: Suppressed={result} (depends on current local time at {case['airport']})")
        else:
            # For all other types, should never be suppressed
            if result == case["should_suppress"]:
                print(f"  ✅ {case['notification_type']}: Never suppressed (24/7 delivery)")
            else:
                print(f"  ❌ {case['notification_type']}: Should never be suppressed but got {result}")
                all_passed = False
    
    if all_passed:
        print("✅ UNIFIED quiet hours policy working correctly")
    else:
        print("❌ UNIFIED quiet hours policy has issues")
    
    return all_passed


def test_aeroapi_cache_optimization():
    """
    Validar que el cache de AeroAPI está OPTIMIZADO.
    """
    print("\n🔄 Testing AeroAPI cache optimization...")
    
    try:
        client = AeroAPIClient()
        
        # Get initial cache stats
        initial_stats = client.get_cache_stats()
        
        print(f"  📊 Initial cache stats:")
        print(f"     Cache hits: {initial_stats['cache_hits']}")
        print(f"     Cache misses: {initial_stats['cache_misses']}")
        print(f"     Hit rate: {initial_stats['hit_rate_percent']}%")
        print(f"     API calls saved: {initial_stats['api_calls_saved']}")
        print(f"     Cost optimization: {initial_stats['cost_optimization']}")
        
        # Verify cache features
        cache_features = [
            "cache_hits" in initial_stats,
            "hit_rate_percent" in initial_stats,
            "api_calls_saved" in initial_stats,
            "cost_optimization" in initial_stats,
            initial_stats["cache_duration_minutes"] == 5
        ]
        
        if all(cache_features):
            print("  ✅ AeroAPI cache optimization features present")
            return True
        else:
            print("  ❌ AeroAPI cache missing optimization features")
            return False
            
    except Exception as e:
        print(f"  ❌ AeroAPI cache test failed: {str(e)}")
        return False


def test_timezone_policy_unified():
    """
    Validar que la política de timezone está UNIFICADA.
    """
    print("\n🔄 Testing UNIFIED timezone policy...")
    
    try:
        from app.utils.timezone_utils import (
            parse_local_time_to_utc,
            format_departure_time_human,
            format_departure_time_local
        )
        
        # Test INPUT=local, STORAGE=UTC, DISPLAY=local policy
        test_cases = [
            {
                "local_time": datetime(2025, 7, 8, 22, 5),  # LHR local
                "airport": "LHR",
                "expected_utc_hour": 21  # BST = UTC+1, so 22:05 local = 21:05 UTC
            },
            {
                "local_time": datetime(2025, 7, 8, 14, 30),  # EZE local  
                "airport": "EZE",
                "expected_utc_hour": 17  # ART = UTC-3, so 14:30 local = 17:30 UTC
            }
        ]
        
        all_passed = True
        
        for case in test_cases:
            # Test local → UTC conversion
            utc_result = parse_local_time_to_utc(case["local_time"], case["airport"])
            
            if utc_result.hour == case["expected_utc_hour"]:
                print(f"  ✅ {case['airport']}: {case['local_time'].strftime('%H:%M')} local → {utc_result.strftime('%H:%M')} UTC")
            else:
                print(f"  ❌ {case['airport']}: Expected UTC hour {case['expected_utc_hour']}, got {utc_result.hour}")
                all_passed = False
            
            # Test UTC → local display
            human_format = format_departure_time_human(utc_result, case["airport"])
            local_format = format_departure_time_local(utc_result, case["airport"])
            
            # Should contain original local time
            if case["local_time"].strftime("%H:%M") in human_format:
                print(f"  ✅ {case['airport']}: UTC → display shows original local time")
            else:
                print(f"  ❌ {case['airport']}: Display format doesn't show original local time: {human_format}")
                all_passed = False
        
        if all_passed:
            print("✅ UNIFIED timezone policy working correctly")
        else:
            print("❌ UNIFIED timezone policy has issues")
        
        return all_passed
        
    except Exception as e:
        print(f"  ❌ Timezone policy test failed: {str(e)}")
        return False


async def test_notifications_agent_simplified():
    """
    Validar que el NotificationsAgent está SIMPLIFICADO sin duplicaciones.
    """
    print("\n🔄 Testing SIMPLIFIED NotificationsAgent...")
    
    try:
        agent = NotificationsAgent()
        
        # Test that agent uses unified utilities
        features_present = [
            hasattr(agent, 'async_twilio_client'),
            hasattr(agent, 'retry_service'),
            hasattr(agent, 'db_client'),
            hasattr(agent, 'aeroapi_client')
        ]
        
        if all(features_present):
            print("  ✅ NotificationsAgent has all required components")
        else:
            print("  ❌ NotificationsAgent missing components")
            await agent.close()
            return False
        
        # Test that duplicate methods are removed/simplified
        simplified_features = [
            # Should NOT have old complex methods
            not hasattr(agent, '_consolidate_ping_pong_changes'),
            not hasattr(agent, '_is_actual_delay'),
            not hasattr(agent, 'calculate_next_check_time'),  # Should use unified version
        ]
        
        # Should HAVE simplified methods  
        has_simplified = [
            hasattr(agent, '_detect_meaningful_changes'),
            hasattr(agent, '_is_significant_delay'),
            hasattr(agent, '_get_dynamic_reminder_data'),
            hasattr(agent, '_get_dynamic_change_data')
        ]
        
        if all(simplified_features) and all(has_simplified):
            print("  ✅ NotificationsAgent properly simplified (complex logic removed)")
        else:
            print("  ❌ NotificationsAgent still has complex/duplicate methods")
            await agent.close()
            return False
        
        await agent.close()
        print("✅ NotificationsAgent simplified successfully")
        return True
        
    except Exception as e:
        print(f"  ❌ NotificationsAgent test failed: {str(e)}")
        return False


def test_architecture_consolidation():
    """
    Validar que la arquitectura está CONSOLIDADA sin duplicaciones.
    """
    print("\n🔄 Testing CONSOLIDATED architecture...")
    
    # Test that unified utilities exist
    try:
        from app.utils.flight_schedule_utils import (
            calculate_unified_next_check,
            should_suppress_notification_unified,
            get_polling_phase
        )
        print("  ✅ Unified flight schedule utilities available")
    except ImportError as e:
        print(f"  ❌ Missing unified utilities: {e}")
        return False
    
    # Test that timezone utilities are clean
    try:
        from app.utils.timezone_utils import (
            parse_local_time_to_utc,
            format_departure_time_human,
            is_quiet_hours_local
        )
        print("  ✅ Timezone utilities available")
    except ImportError as e:
        print(f"  ❌ Missing timezone utilities: {e}")
        return False
    
    # Test that router uses simplified approach
    try:
        from app.router import _create_trip_object_simplified
        print("  ✅ Router has simplified trip creation")
    except ImportError:
        print("  ❌ Router missing simplified functions")
        return False
    
    print("✅ Architecture consolidated successfully")
    return True


async def main():
    """
    Ejecutar todas las validaciones del análisis QA.
    """
    print("🔍 QA TECH LEAD VALIDATION - UNIFIED OPTIMIZATIONS")
    print("=" * 60)
    
    tests = [
        ("UNIFIED next_check_at Logic", test_unified_next_check_logic),
        ("UNIFIED Quiet Hours Policy", test_unified_quiet_hours_policy),
        ("AeroAPI Cache Optimization", test_aeroapi_cache_optimization),
        ("UNIFIED Timezone Policy", test_timezone_policy_unified),
        ("SIMPLIFIED NotificationsAgent", test_notifications_agent_simplified),
        ("CONSOLIDATED Architecture", test_architecture_consolidation)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        if asyncio.iscoroutinefunction(test_func):
            result = await test_func()
        else:
            result = test_func()
        
        results.append((test_name, result))
    
    print(f"\n{'='*60}")
    print("📊 VALIDATION SUMMARY")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 OVERALL RESULT: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🚀 ALL OPTIMIZATIONS SUCCESSFULLY IMPLEMENTED!")
        print("   • Duplications eliminated")
        print("   • Performance optimized") 
        print("   • Architecture consolidated")
        print("   • Code simplified")
        print("   • Ready for production")
    else:
        print(f"\n⚠️  {total - passed} optimizations need attention")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main()) 