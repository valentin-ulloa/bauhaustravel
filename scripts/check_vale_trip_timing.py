#!/usr/bin/env python3
"""
Script to diagnose Vale's trip polling timing.
Why is it being checked every 15 minutes instead of hourly?
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
import structlog

logger = structlog.get_logger()


async def check_vale_trip_timing():
    """Check Vale's trip timing and polling schedule"""
    
    print("🔍 Diagnosticando timing de polling para el viaje de Vale...")
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Get Vale's trip (should be the most recent one)
        now_utc = datetime.now(timezone.utc)
        
        # Find trip by Vale's WhatsApp
        vale_trip = await db_client.get_latest_trip_by_whatsapp("+5491140383422")
        
        if not vale_trip:
            print("❌ No se encontró el viaje de Vale")
            return
        
        print(f"\n📋 **VIAJE DE VALE ENCONTRADO**:")
        print(f"🆔 Trip ID: {vale_trip.id}")
        print(f"✈️  Vuelo: {vale_trip.flight_number}")
        print(f"🛫 Salida: {vale_trip.departure_date}")
        print(f"⏰ Next Check: {getattr(vale_trip, 'next_check_at', 'NO SET')}")
        
        # Calculate time until departure
        time_until = vale_trip.departure_date - now_utc
        hours_until = time_until.total_seconds() / 3600
        
        print(f"\n📊 **ANÁLISIS DE TIMING**:")
        print(f"⏱️  Tiempo hasta salida: {hours_until:.1f} horas")
        print(f"🎯 Regla aplicable: {'> 24h → 6h' if hours_until > 24 else '24h-4h → 1h' if hours_until > 4 else '≤ 4h → 15min'}")
        
        # Calculate what next_check_at SHOULD be
        expected_next_check = notifications_agent.calculate_next_check_time(vale_trip.departure_date, now_utc)
        current_next_check = getattr(vale_trip, 'next_check_at', None)
        
        print(f"\n🎯 **NEXT CHECK ANALYSIS**:")
        print(f"📅 Actual next_check_at: {current_next_check}")
        print(f"✅ Expected next_check_at: {expected_next_check}")
        
        if current_next_check:
            diff = (current_next_check - now_utc).total_seconds() / 60
            expected_diff = (expected_next_check - now_utc).total_seconds() / 60
            print(f"⏰ Actual check en: {diff:.0f} minutos")
            print(f"⏰ Expected check en: {expected_diff:.0f} minutos")
            
            if abs(diff - expected_diff) > 5:  # 5-minute tolerance
                print(f"🚨 **PROBLEMA**: next_check_at está mal configurado!")
                print(f"   Debería ser cada {expected_diff:.0f}min pero está en {diff:.0f}min")
            else:
                print(f"✅ next_check_at está correctamente configurado")
        
        # Check if trip would be included in current polling
        trips_to_poll = await db_client.get_trips_to_poll(now_utc)
        vale_in_poll = any(str(t.id) == str(vale_trip.id) for t in trips_to_poll)
        
        print(f"\n🔄 **POLLING STATUS**:")
        print(f"📝 Trips en cola para polling: {len(trips_to_poll)}")
        print(f"🎯 Vale incluido en polling actual: {'SÍ' if vale_in_poll else 'NO'}")
        
        if vale_in_poll:
            print(f"⚠️  **EXPLICACIÓN**: El viaje está siendo polleado porque:")
            print(f"   next_check_at ({current_next_check}) <= now ({now_utc})")
        else:
            print(f"✅ **CORRECTO**: El viaje NO está en polling porque:")
            print(f"   next_check_at ({current_next_check}) > now ({now_utc})")
        
        # Show when next polling should happen
        if current_next_check and current_next_check > now_utc:
            minutes_until_next = (current_next_check - now_utc).total_seconds() / 60
            print(f"\n⏭️  **PRÓXIMO POLLING**: En {minutes_until_next:.0f} minutos")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        await db_client.close()
        await notifications_agent.close()


if __name__ == "__main__":
    asyncio.run(check_vale_trip_timing()) 