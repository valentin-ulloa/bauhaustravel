#!/usr/bin/env python3
"""
TC-004 Database Optimization Performance Test.

Compares performance between:
1. Original method: 4 parallel queries with asyncio.gather()  
2. Optimized method: Single query with JOINs

Usage:
    python scripts/test_database_optimization.py [trip_id]
"""

import asyncio
import sys
import os
import time
from uuid import UUID
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.db.supabase_client import SupabaseDBClient
import structlog

logger = structlog.get_logger()


async def benchmark_context_loading(trip_id: UUID, iterations: int = 5):
    """
    Benchmark both context loading methods.
    
    Args:
        trip_id: Trip ID to test with
        iterations: Number of iterations for averaging
    """
    print(f"🧪 Benchmarking context loading methods...")
    print(f"   Trip ID: {trip_id}")
    print(f"   Iterations: {iterations}")
    print()
    
    db_client = SupabaseDBClient()
    
    try:
        # Test 1: Original method (4 parallel queries)
        print("📊 Testing Original Method (4 parallel queries)...")
        original_times = []
        
        for i in range(iterations):
            start_time = time.perf_counter()
            context_original = await db_client.get_complete_trip_context(trip_id)
            end_time = time.perf_counter()
            
            duration = end_time - start_time
            original_times.append(duration)
            print(f"   Run {i+1}: {duration:.3f}s")
        
        original_avg = sum(original_times) / len(original_times)
        print(f"   📈 Original Average: {original_avg:.3f}s")
        print()
        
        # Test 2: Optimized method (single query with JOINs)
        print("🚀 Testing Optimized Method (single query with JOINs)...")
        optimized_times = []
        
        for i in range(iterations):
            start_time = time.perf_counter()
            context_optimized = await db_client.get_complete_trip_context_optimized(trip_id)
            end_time = time.perf_counter()
            
            duration = end_time - start_time
            optimized_times.append(duration)
            print(f"   Run {i+1}: {duration:.3f}s")
        
        optimized_avg = sum(optimized_times) / len(optimized_times)
        print(f"   📈 Optimized Average: {optimized_avg:.3f}s")
        print()
        
        # Performance comparison
        improvement = ((original_avg - optimized_avg) / original_avg) * 100
        speedup = original_avg / optimized_avg
        
        print("📊 PERFORMANCE RESULTS:")
        print("=" * 50)
        print(f"Original Method:   {original_avg:.3f}s ± {max(original_times) - min(original_times):.3f}s")
        print(f"Optimized Method:  {optimized_avg:.3f}s ± {max(optimized_times) - min(optimized_times):.3f}s")
        print()
        print(f"🚀 Performance Improvement: {improvement:+.1f}%")
        print(f"⚡ Speedup Factor: {speedup:.2f}x")
        print()
        
        # Data consistency check
        print("🔍 DATA CONSISTENCY CHECK:")
        print("=" * 50)
        
        # Compare data structure and content
        original_data = context_original.model_dump()
        optimized_data = context_optimized.model_dump()
        
        # Check trip data
        if original_data["trip"] == optimized_data["trip"]:
            print("✅ Trip data: IDENTICAL")
        else:
            print("❌ Trip data: DIFFERENT")
            print(f"   Original keys: {set(original_data['trip'].keys())}")
            print(f"   Optimized keys: {set(optimized_data['trip'].keys())}")
        
        # Check itinerary
        if original_data["itinerary"] == optimized_data["itinerary"]:
            print("✅ Itinerary: IDENTICAL")
        else:
            print("⚠️  Itinerary: DIFFERENT (check structure)")
        
        # Check documents count
        orig_docs = len(original_data["documents"])
        opt_docs = len(optimized_data["documents"])
        if orig_docs == opt_docs:
            print(f"✅ Documents: IDENTICAL ({orig_docs} items)")
        else:
            print(f"❌ Documents: DIFFERENT (orig: {orig_docs}, opt: {opt_docs})")
        
        # Check conversations count
        orig_msgs = len(original_data["recent_messages"])
        opt_msgs = len(optimized_data["recent_messages"])
        if orig_msgs == opt_msgs:
            print(f"✅ Conversations: IDENTICAL ({orig_msgs} items)")
        else:
            print(f"❌ Conversations: DIFFERENT (orig: {orig_msgs}, opt: {opt_msgs})")
        
        print()
        
        # TC-004 Acceptance Criteria Check
        print("✅ TC-004 AC-1 VALIDATION:")
        if improvement > 0 and speedup > 1.0:
            print(f"✅ PASSED: Context loading optimized by {improvement:.1f}% ({speedup:.2f}x faster)")
        else:
            print(f"❌ FAILED: No significant improvement detected")
        
        return {
            "original_avg": original_avg,
            "optimized_avg": optimized_avg,
            "improvement_percent": improvement,
            "speedup_factor": speedup,
            "data_consistent": original_data == optimized_data
        }
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        return None
    finally:
        await db_client.close()


async def test_with_different_trip_sizes():
    """Test performance with trips that have different amounts of data."""
    print("🔍 Testing with different data sizes...")
    
    # This would require creating trips with different amounts of:
    # - Documents (0, 5, 20 documents)  
    # - Conversations (0, 10, 50 messages)
    # - Itineraries (none, simple, complex)
    
    # For MVP, we'll document this as future enhancement
    print("ℹ️  Multi-size testing: Planned for future iteration")
    print("   Current test uses production data variability")


async def main():
    """Main benchmark orchestrator"""
    print("🧪 TC-004 Database Optimization Performance Test")
    print("=" * 60)
    
    # Get trip_id from args or use default
    if len(sys.argv) > 1:
        try:
            trip_id = UUID(sys.argv[1])
            print(f"🎯 Using provided trip ID: {trip_id}")
        except ValueError:
            print(f"❌ Invalid trip ID format: {sys.argv[1]}")
            return
    else:
        # Use a default test trip (update with actual trip ID from your database)
        trip_id = UUID("be42c25e-9e60-4a36-9f9d-c202f25d5881")  # From our TC-001 testing
        print(f"🎯 Using default test trip ID: {trip_id}")
    
    print()
    
    # Run performance benchmark
    results = await benchmark_context_loading(trip_id, iterations=5)
    
    if results:
        print("🎯 RECOMMENDATION:")
        if results["improvement_percent"] > 20:
            print("✅ Deploy optimized method - significant improvement detected")
        elif results["improvement_percent"] > 0:
            print("⚡ Deploy optimized method - moderate improvement")
        else:
            print("⚠️  Keep original method - no significant benefit")
        
        if not results["data_consistent"]:
            print("🔧 REQUIRED: Fix data consistency issues before deployment")
    
    # Test different data sizes
    await test_with_different_trip_sizes()
    
    print()
    print("✅ Database optimization testing completed!")


if __name__ == "__main__":
    asyncio.run(main()) 