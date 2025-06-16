#!/usr/bin/env python3
"""
Simulate flight changes for testing TC-001 NotificationsAgent.

This script manually modifies trip data in Supabase to simulate:
- Status changes (DELAYED, CANCELLED)
- Gate changes
- Departure time changes

Usage:
    python scripts/simulate_flight_change.py <trip_id> <change_type> [value]
    
Examples:
    python scripts/simulate_flight_change.py abc123 delay 30
    python scripts/simulate_flight_change.py abc123 cancel
    python scripts/simulate_flight_change.py abc123 gate B15
    python scripts/simulate_flight_change.py abc123 reset
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent


async def simulate_delay(trip_id: UUID, delay_minutes: int = 30):
    """Simulate flight delay"""
    print(f"🕒 Simulating {delay_minutes} minute delay for trip {trip_id}...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Get current trip
        result = await db_client.get_trip_by_id(trip_id)
        if not result.success:
            print(f"❌ Trip not found: {trip_id}")
            return False
        
        trip_data = result.data
        
        # Update status and departure time
        departure_str = trip_data["departure_date"]
        if isinstance(departure_str, str):
            # Handle string format
            departure_str = departure_str.replace('Z', '+00:00')
            current_departure = datetime.fromisoformat(departure_str)
        else:
            # Handle datetime object
            current_departure = departure_str
        
        new_departure = current_departure + timedelta(minutes=delay_minutes)
        
        # Update in database
        response = await db_client._client.patch(
            f"{db_client.rest_url}/trips",
            params={"id": f"eq.{trip_id}"},
            json={
                "status": "DELAYED",
                "departure_date": new_departure.isoformat(),
                # Reset next_check_at to trigger immediate polling
                "next_check_at": datetime.now(timezone.utc).isoformat()
            }
        )
        response.raise_for_status()
        
        print(f"✅ Flight delayed by {delay_minutes} minutes")
        print(f"   New departure: {new_departure.isoformat()}")
        print(f"   Status: DELAYED")
        print(f"   next_check_at reset for immediate polling")
        
        return True
        
    except Exception as e:
        print(f"❌ Error simulating delay: {e}")
        return False
    finally:
        await db_client.close()


async def simulate_cancellation(trip_id: UUID):
    """Simulate flight cancellation"""
    print(f"❌ Simulating cancellation for trip {trip_id}...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Update status to cancelled
        response = await db_client._client.patch(
            f"{db_client.rest_url}/trips",
            params={"id": f"eq.{trip_id}"},
            json={
                "status": "CANCELLED",
                # Reset next_check_at to trigger immediate polling
                "next_check_at": datetime.now(timezone.utc).isoformat()
            }
        )
        response.raise_for_status()
        
        print(f"✅ Flight cancelled")
        print(f"   Status: CANCELLED")
        print(f"   next_check_at reset for immediate polling")
        
        return True
        
    except Exception as e:
        print(f"❌ Error simulating cancellation: {e}")
        return False
    finally:
        await db_client.close()


async def simulate_gate_change(trip_id: UUID, new_gate: str):
    """Simulate gate change"""
    print(f"🚪 Simulating gate change to {new_gate} for trip {trip_id}...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Update gate
        response = await db_client._client.patch(
            f"{db_client.rest_url}/trips",
            params={"id": f"eq.{trip_id}"},
            json={
                "gate": new_gate,
                # Reset next_check_at to trigger immediate polling
                "next_check_at": datetime.now(timezone.utc).isoformat()
            }
        )
        response.raise_for_status()
        
        print(f"✅ Gate changed to {new_gate}")
        print(f"   next_check_at reset for immediate polling")
        
        return True
        
    except Exception as e:
        print(f"❌ Error simulating gate change: {e}")
        return False
    finally:
        await db_client.close()


async def reset_trip(trip_id: UUID):
    """Reset trip to original scheduled state"""
    print(f"🔄 Resetting trip {trip_id} to SCHEDULED state...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Get current trip to restore original departure time
        result = await db_client.get_trip_by_id(trip_id)
        if not result.success:
            print(f"❌ Trip not found: {trip_id}")
            return False
        
        trip_data = result.data
        
        # Reset to scheduled state
        response = await db_client._client.patch(
            f"{db_client.rest_url}/trips",
            params={"id": f"eq.{trip_id}"},
            json={
                "status": "SCHEDULED",
                "gate": None,  # Clear gate
                # Keep original departure_date or you could restore from backup
                "next_check_at": datetime.now(timezone.utc).isoformat()
            }
        )
        response.raise_for_status()
        
        print(f"✅ Trip reset to SCHEDULED")
        print(f"   Status: SCHEDULED")
        print(f"   Gate: cleared")
        print(f"   next_check_at reset for immediate polling")
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting trip: {e}")
        return False
    finally:
        await db_client.close()


async def trigger_polling(trip_id: UUID):
    """Trigger immediate polling for the trip"""
    print(f"🔄 Triggering polling for trip {trip_id}...")
    
    notifications_agent = NotificationsAgent()
    
    try:
        # Run polling cycle
        result = await notifications_agent.poll_flight_changes()
        
        if result.success:
            print(f"✅ Polling completed:")
            if result.data:
                data = result.data
                print(f"   - Trips checked: {data.get('checked', 0)}")
                print(f"   - Notifications sent: {data.get('updates', 0)}")
                print(f"   - Errors: {data.get('errors', 0)}")
        else:
            print(f"❌ Polling failed: {result.error}")
            
    except Exception as e:
        print(f"❌ Error triggering polling: {e}")
    finally:
        await notifications_agent.close()


def print_usage():
    """Print usage instructions"""
    print("Usage: python scripts/simulate_flight_change.py <trip_id> <change_type> [value]")
    print()
    print("Change types:")
    print("  delay [minutes]  - Simulate flight delay (default 30 min)")
    print("  cancel          - Simulate flight cancellation")
    print("  gate <gate>     - Simulate gate change (e.g., B15)")
    print("  reset           - Reset trip to SCHEDULED state")
    print("  poll            - Trigger immediate polling")
    print()
    print("Examples:")
    print("  python scripts/simulate_flight_change.py abc123-def456 delay 45")
    print("  python scripts/simulate_flight_change.py abc123-def456 cancel")
    print("  python scripts/simulate_flight_change.py abc123-def456 gate C20")
    print("  python scripts/simulate_flight_change.py abc123-def456 reset")


async def main():
    """Main function"""
    if len(sys.argv) < 3:
        print_usage()
        return
    
    try:
        trip_id = UUID(sys.argv[1])
    except ValueError:
        print(f"❌ Invalid trip ID format: {sys.argv[1]}")
        return
    
    change_type = sys.argv[2].lower()
    
    print(f"🎯 Simulating change for trip: {trip_id}")
    print(f"📝 Change type: {change_type}")
    print()
    
    success = False
    
    if change_type == "delay":
        delay_minutes = 30
        if len(sys.argv) > 3:
            try:
                delay_minutes = int(sys.argv[3])
            except ValueError:
                print(f"❌ Invalid delay minutes: {sys.argv[3]}")
                return
        success = await simulate_delay(trip_id, delay_minutes)
    
    elif change_type == "cancel":
        success = await simulate_cancellation(trip_id)
    
    elif change_type == "gate":
        if len(sys.argv) < 4:
            print(f"❌ Gate change requires gate value (e.g., B15)")
            return
        new_gate = sys.argv[3]
        success = await simulate_gate_change(trip_id, new_gate)
    
    elif change_type == "reset":
        success = await reset_trip(trip_id)
    
    elif change_type == "poll":
        await trigger_polling(trip_id)
        success = True  # polling doesn't return success/failure the same way
    
    else:
        print(f"❌ Unknown change type: {change_type}")
        print_usage()
        return
    
    if success and change_type != "poll":
        print()
        print("🚀 Now run polling to test notifications:")
        print(f"python scripts/simulate_flight_change.py {trip_id} poll")
        print()
        print("Or run the full test:")
        print(f"python scripts/test_notifications_full_flow.py {trip_id}")


if __name__ == "__main__":
    asyncio.run(main()) 