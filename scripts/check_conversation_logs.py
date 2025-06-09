#!/usr/bin/env python3
"""Script to check conversation logs and system health after bot testing."""

import os
import asyncio
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import SupabaseDBClient
from app.models.database import Trip

async def main():
    """Check conversation logs and system health."""
    print("🔍 Checking conversation logs and system health...\n")
    
    db_client = SupabaseDBClient()
    
    try:
        # 1. Check recent conversations
        print("📱 RECENT CONVERSATIONS:")
        print("-" * 50)
        
        # Get recent trips to check conversations
        now = datetime.now(timezone.utc)
        
        # Check conversations from last 24 hours
        conversations_query = f"""
        SELECT 
            c.created_at,
            c.sender,
            c.message,
            c.intent,
            t.client_name,
            t.whatsapp,
            t.flight_number
        FROM conversations c
        JOIN trips t ON c.trip_id = t.id
        WHERE c.created_at >= '{(now - timedelta(days=1)).isoformat()}'
        ORDER BY c.created_at DESC
        LIMIT 20
        """
        
        # Since we don't have direct SQL access, let's check via REST API
        response = await db_client._client.get(
            f"{db_client.rest_url}/conversations",
            params={
                "select": "*,trips(client_name,whatsapp,flight_number)",
                "created_at": f"gte.{(now - timedelta(days=1)).isoformat()}",
                "order": "created_at.desc",
                "limit": "20"
            }
        )
        
        if response.status_code == 200:
            conversations = response.json()
            
            for conv in conversations:
                time_str = conv['created_at'][:19].replace('T', ' ')
                sender_emoji = "👤" if conv['sender'] == 'user' else "🤖"
                message_preview = conv['message'][:80] + "..." if len(conv['message']) > 80 else conv['message']
                
                trip_info = conv.get('trips', {})
                client_name = trip_info.get('client_name', 'Unknown') if trip_info else 'Unknown'
                
                print(f"{sender_emoji} {time_str} | {client_name}")
                print(f"   {message_preview}")
                print()
        else:
            print(f"❌ Error fetching conversations: {response.status_code}")
        
        # 2. Check notification logs
        print("\n📲 RECENT NOTIFICATIONS:")
        print("-" * 50)
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/notifications_log",
            params={
                "select": "*,trips(client_name,flight_number)",
                "sent_at": f"gte.{(now - timedelta(days=1)).isoformat()}",
                "order": "sent_at.desc",
                "limit": "10"
            }
        )
        
        if response.status_code == 200:
            notifications = response.json()
            
            for notif in notifications:
                time_str = notif['sent_at'][:19].replace('T', ' ')
                status_emoji = "✅" if notif['delivery_status'] == 'SENT' else "❌"
                
                trip_info = notif.get('trips', {})
                client_name = trip_info.get('client_name', 'Unknown') if trip_info else 'Unknown'
                
                print(f"{status_emoji} {time_str} | {notif['notification_type']} | {client_name}")
                if notif.get('error_message'):
                    print(f"   Error: {notif['error_message']}")
                print()
        else:
            print(f"❌ Error fetching notifications: {response.status_code}")
        
        # 3. Check system stats
        print("\n📊 SYSTEM STATS:")
        print("-" * 50)
        
        # Count conversations today
        conv_response = await db_client._client.get(
            f"{db_client.rest_url}/conversations",
            params={
                "created_at": f"gte.{now.strftime('%Y-%m-%d')}T00:00:00",
                "select": "id"
            }
        )
        
        conv_count = len(conv_response.json()) if conv_response.status_code == 200 else 0
        print(f"💬 Conversations today: {conv_count}")
        
        # Count notifications today
        notif_response = await db_client._client.get(
            f"{db_client.rest_url}/notifications_log",
            params={
                "sent_at": f"gte.{now.strftime('%Y-%m-%d')}T00:00:00",
                "select": "id"
            }
        )
        
        notif_count = len(notif_response.json()) if notif_response.status_code == 200 else 0
        print(f"📱 Notifications today: {notif_count}")
        
        # Count total trips
        trips_response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={"select": "id"}
        )
        
        trips_count = len(trips_response.json()) if trips_response.status_code == 200 else 0
        print(f"✈️ Total trips: {trips_count}")
        
        print(f"\n🎉 System is operational! Last check: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
    except Exception as e:
        print(f"❌ Error checking system: {str(e)}")
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(main()) 