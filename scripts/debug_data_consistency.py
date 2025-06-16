#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from uuid import UUID

async def debug_data():
    client = SupabaseDBClient()
    trip_id = UUID('be42c25e-9e60-4a36-9f9d-c202f25d5881')
    
    print("🔍 Debugging data consistency...")
    
    orig = await client.get_complete_trip_context(trip_id)
    opt = await client.get_complete_trip_context_optimized(trip_id)
    
    print('Original keys:', sorted(orig.trip.keys()))
    print('Optimized keys:', sorted(opt.trip.keys()))
    print()
    
    # Find differences
    orig_set = set(orig.trip.keys())
    opt_set = set(opt.trip.keys())
    
    only_in_orig = orig_set - opt_set
    only_in_opt = opt_set - orig_set
    
    print('Only in original:', only_in_orig if only_in_orig else 'None')
    print('Only in optimized:', only_in_opt if only_in_opt else 'None')
    print()
    
    # Compare values for common keys
    common_keys = orig_set & opt_set
    different_values = []
    
    for key in common_keys:
        if str(orig.trip[key]) != str(opt.trip[key]):
            different_values.append(key)
            print(f"Different value for '{key}':")
            print(f"  Original: {orig.trip[key]}")
            print(f"  Optimized: {opt.trip[key]}")
    
    if not different_values:
        print("✅ All common values are identical")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(debug_data()) 