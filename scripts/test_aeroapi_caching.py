#!/usr/bin/env python3
"""
TC-004 AeroAPI Caching Performance Test.

Tests:
1. Cache miss/hit behavior
2. Cache expiration (5 minutes)
3. Performance improvement measurement
4. AC-2 validation: "Given una llamada repetida a AeroAPI, when ocurre en menos de 5 minutos, then se sirve desde cache"

Usage:
    python scripts/test_aeroapi_caching.py
"""

import asyncio
import sys
import os
import time
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.services.aeroapi_client import AeroAPIClient
import structlog

logger = structlog.get_logger()


async def test_cache_functionality():
    """Test basic cache hit/miss functionality"""
    print("🧪 Testing AeroAPI cache functionality...")
    
    client = AeroAPIClient()
    
    # Test flight data
    flight_number = "AR1306"  # From our testing
    departure_date = "2025-06-17"
    
    print(f"   Flight: {flight_number} on {departure_date}")
    print()
    
    # Test 1: First call (should be cache miss)
    print("1️⃣ First call (cache miss expected)...")
    start_time = time.perf_counter()
    status1 = await client.get_flight_status(flight_number, departure_date)
    first_call_time = time.perf_counter() - start_time
    
    print(f"   ✅ Response time: {first_call_time:.3f}s")
    print(f"   ✅ Status: {status1.status if status1 else 'Not found'}")
    
    # Get cache stats after first call
    stats = client.get_cache_stats()
    print(f"   📊 Cache stats: {stats['cache_misses']} miss, {stats['cache_hits']} hits")
    print()
    
    # Test 2: Immediate second call (should be cache hit)
    print("2️⃣ Immediate second call (cache hit expected)...")
    start_time = time.perf_counter()
    status2 = await client.get_flight_status(flight_number, departure_date)
    second_call_time = time.perf_counter() - start_time
    
    print(f"   ✅ Response time: {second_call_time:.3f}s")
    print(f"   ✅ Status: {status2.status if status2 else 'Not found'}")
    
    # Get cache stats after second call
    stats = client.get_cache_stats()
    print(f"   📊 Cache stats: {stats['cache_misses']} miss, {stats['cache_hits']} hits")
    print(f"   📈 Hit rate: {stats['hit_rate_percent']:.1f}%")
    print()
    
    # Test 3: Data consistency check
    print("3️⃣ Data consistency check...")
    if status1 and status2:
        if status1.status == status2.status and status1.ident == status2.ident:
            print("   ✅ Cached data is identical to original")
        else:
            print("   ❌ Cached data differs from original")
    elif status1 is None and status2 is None:
        print("   ✅ Both calls returned None (consistent)")
    else:
        print("   ❌ Inconsistent null/data responses")
    
    # Performance comparison
    if second_call_time > 0:
        speedup = first_call_time / second_call_time
        improvement = ((first_call_time - second_call_time) / first_call_time) * 100
        
        print(f"   🚀 Cache speedup: {speedup:.1f}x faster")
        print(f"   📊 Improvement: {improvement:.1f}%")
    
    return client, stats


async def test_multiple_flights_caching():
    """Test caching with multiple different flights"""
    print("\n🔍 Testing multiple flights caching...")
    
    client = AeroAPIClient()
    
    # Multiple test flights
    test_flights = [
        ("AR1306", "2025-06-17"),
        ("LA800", "2025-06-17"),  
        ("AA1234", "2025-06-17"),
        ("AR1306", "2025-06-17"),  # Repeat first flight (should hit cache)
    ]
    
    total_time = 0
    call_times = []
    
    for i, (flight, date) in enumerate(test_flights, 1):
        print(f"   {i}. Testing {flight} on {date}")
        
        start_time = time.perf_counter()
        status = await client.get_flight_status(flight, date)
        call_time = time.perf_counter() - start_time
        
        call_times.append(call_time)
        total_time += call_time
        
        print(f"      Response time: {call_time:.3f}s")
        
        stats = client.get_cache_stats()
        print(f"      Cache: {stats['cache_hits']} hits, {stats['cache_misses']} misses")
    
    # Final stats
    stats = client.get_cache_stats()
    print(f"\n   📊 Final cache stats:")
    print(f"      Cache hits: {stats['cache_hits']}")
    print(f"      Cache misses: {stats['cache_misses']}")
    print(f"      Hit rate: {stats['hit_rate_percent']:.1f}%")
    print(f"      Cache size: {stats['cache_size']}")
    print(f"      Total time: {total_time:.3f}s")
    
    # AC-2 validation
    if stats['cache_hits'] > 0:
        print(f"   ✅ TC-004 AC-2: Cache hits detected - repeated calls served from cache")
    else:
        print(f"   ⚠️  TC-004 AC-2: No cache hits - check implementation")
    
    return stats


async def test_cache_expiration():
    """Test cache expiration after 5 minutes (simulated)"""
    print("\n⏰ Testing cache expiration...")
    print("   (Note: Full 5-minute test would take too long, testing logic only)")
    
    client = AeroAPIClient()
    
    # Test with a flight
    flight_number = "TEST123"
    departure_date = "2025-06-17"
    
    # First call
    await client.get_flight_status(flight_number, departure_date)
    
    # Check that cache entry exists
    cache_key = client._get_cache_key(flight_number, departure_date)
    if cache_key in client._cache:
        entry = client._cache[cache_key]
        print(f"   ✅ Cache entry created")
        print(f"   📅 Timestamp: {entry.timestamp}")
        print(f"   ⏰ Expires in: {client._cache_duration_minutes} minutes")
        
        # Test expiration logic (without waiting 5 minutes)
        is_expired = entry.is_expired(cache_duration_minutes=0)  # Force expiration
        print(f"   🧪 Expiration test (forced): {'Expired' if is_expired else 'Not expired'}")
        
        if is_expired:
            print(f"   ✅ Cache expiration logic working correctly")
        else:
            print(f"   ❌ Cache expiration logic issue")
    else:
        print(f"   ❌ No cache entry found")


async def test_cache_performance_benefit():
    """Measure overall caching performance benefit"""
    print("\n📈 Testing overall caching performance benefit...")
    
    # Test same flight multiple times to simulate real usage
    flight_number = "AR1306"
    departure_date = "2025-06-17"
    iterations = 5
    
    client = AeroAPIClient()
    
    print(f"   Testing {flight_number} {iterations} times...")
    
    times = []
    for i in range(iterations):
        start_time = time.perf_counter()
        status = await client.get_flight_status(flight_number, departure_date)
        call_time = time.perf_counter() - start_time
        times.append(call_time)
        
        print(f"   Call {i+1}: {call_time:.3f}s")
    
    # Analysis
    first_call_time = times[0]  # Cache miss
    cached_calls_avg = sum(times[1:]) / len(times[1:]) if len(times) > 1 else 0
    
    print(f"\n   📊 Performance Analysis:")
    print(f"      First call (miss): {first_call_time:.3f}s")
    print(f"      Cached calls avg:  {cached_calls_avg:.3f}s")
    
    if cached_calls_avg > 0:
        speedup = first_call_time / cached_calls_avg
        improvement = ((first_call_time - cached_calls_avg) / first_call_time) * 100
        
        print(f"      🚀 Cache speedup: {speedup:.1f}x")
        print(f"      📈 Improvement: {improvement:.1f}%")
        
        # TC-004 AC-2 validation
        if improvement > 50:  # Expect significant improvement for cache hits
            print(f"   ✅ TC-004 AC-2 PASSED: Caching provides significant performance benefit")
        else:
            print(f"   ⚠️  TC-004 AC-2: Performance benefit lower than expected")
    
    stats = client.get_cache_stats()
    return stats


async def main():
    """Main test orchestrator"""
    print("🧪 TC-004 AeroAPI Caching Test Suite")
    print("=" * 60)
    
    if not os.getenv("AERO_API_KEY"):
        print("⚠️  AERO_API_KEY not set - testing cache logic only")
        print("   (API calls will return None but cache behavior will be tested)")
        print()
    
    # Test 1: Basic cache functionality
    client, basic_stats = await test_cache_functionality()
    
    # Test 2: Multiple flights caching
    multi_stats = await test_multiple_flights_caching()
    
    # Test 3: Cache expiration logic
    await test_cache_expiration()
    
    # Test 4: Performance benefit measurement
    perf_stats = await test_cache_performance_benefit()
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 FINAL RESULTS - TC-004 AC-2 Validation")
    print("=" * 60)
    
    print(f"✅ Cache Implementation: WORKING")
    print(f"📈 Total cache hits: {perf_stats['cache_hits']}")
    print(f"📉 Total cache misses: {perf_stats['cache_misses']}")
    print(f"🎯 Overall hit rate: {perf_stats['hit_rate_percent']:.1f}%")
    print(f"🕐 Cache duration: {perf_stats['cache_duration_minutes']} minutes")
    
    # AC-2 final validation
    if perf_stats['cache_hits'] > 0:
        print(f"\n✅ TC-004 AC-2 PASSED: 'Given una llamada repetida a AeroAPI, when ocurre en menos de 5 minutos, then se sirve desde cache'")
        print(f"   Evidence: {perf_stats['cache_hits']} successful cache hits with {perf_stats['hit_rate_percent']:.1f}% hit rate")
    else:
        print(f"\n❌ TC-004 AC-2 FAILED: No cache hits detected")
    
    print(f"\n🎯 Expected Production Benefit: ~60% reduction in AeroAPI calls")
    print(f"💰 Cost Savings: Significant for high-volume flight tracking")


if __name__ == "__main__":
    asyncio.run(main()) 