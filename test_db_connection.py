#!/usr/bin/env python3
"""
Quick test script to verify Supabase connection and SupabaseDBClient.
Run this after setting up your .env file and running the migration.
"""

import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_supabase_connection():
    """Test basic Supabase connection and database operations."""
    
    # Import here so environment is loaded first
    from app.db.supabase_client import SupabaseDBClient
    
    print("🔍 Testing Supabase Connection...")
    print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL', 'NOT SET')}")
    print(f"SUPABASE_SERVICE_ROLE_KEY: {'SET' if os.getenv('SUPABASE_SERVICE_ROLE_KEY') else 'NOT SET'}")
    print()
    
    try:
        # Initialize client
        client = SupabaseDBClient()
        print("✅ SupabaseDBClient initialized successfully")
        
        # Test 1: Query trips
        print("🔍 Testing trips query...")
        now_utc = datetime.now(timezone.utc)
        trips = await client.get_trips_to_poll(now_utc)
        print(f"✅ Found {len(trips)} trips to poll")
        
        if trips:
            print(f"📍 Sample trip: {trips[0].client_name} - {trips[0].flight_number}")
        
        # Test 2: Check if we can query notification history (table should exist after migration)
        if trips:
            print("🔍 Testing notification history query...")
            history = await client.get_notification_history(trips[0].id)
            print(f"✅ Found {len(history)} notification records for trip {trips[0].id}")
        
        print("\n🎉 All database tests passed!")
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        print("\n🔧 Common fixes:")
        print("1. Check your .env file has correct SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        print("2. Run the migration SQL in your Supabase dashboard")
        print("3. Ensure your Supabase project is active")
        return False
    
    finally:
        await client.close()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_supabase_connection()) 