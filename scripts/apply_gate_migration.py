#!/usr/bin/env python3
"""
Apply migration 006: Add gate field to trips table
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def apply_migration():
    """Apply the gate field migration to Supabase"""
    
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not service_key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        return False
    
    # SQL Migration
    migration_sql = """
    -- Migration 006: Add gate field to trips table for flight tracking
    
    -- Add gate field to trips table (only if it doesn't exist)
    DO $$ 
    BEGIN 
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'trips' AND column_name = 'gate') THEN
            ALTER TABLE trips ADD COLUMN gate text;
            RAISE NOTICE 'Added gate column to trips table';
        ELSE
            RAISE NOTICE 'Gate column already exists in trips table';
        END IF;
    END $$;
    
    -- Add index for efficient gate lookups (optional, for performance)
    CREATE INDEX IF NOT EXISTS idx_trips_gate ON trips(gate) WHERE gate IS NOT NULL;
    
    -- Add comment for documentation
    COMMENT ON COLUMN trips.gate IS 'Flight departure gate (e.g., "A12", "B3") - updated from AeroAPI';
    """
    
    try:
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/vnd.pgrst.object+json"
        }
        
        # Use Supabase's raw SQL RPC endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/exec_sql",
                json={"sql": migration_sql},
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                print("✅ Migration 006 applied successfully!")
                print("🔧 Added 'gate' field to trips table")
                return True
            else:
                print(f"❌ Migration failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Applying Migration 006: Add gate field...")
    success = asyncio.run(apply_migration())
    if success:
        print("📝 Migration completed. You can now track flight gates!")
    else:
        print("💥 Migration failed. Check your Supabase connection.") 