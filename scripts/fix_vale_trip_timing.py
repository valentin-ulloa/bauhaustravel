#!/usr/bin/env python3
"""
Fix Vale's trip timing by updating next_check_at with proper timezone.
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


async def fix_vale_trip_timing():
    """Fix Vale's trip timing by correcting next_check_at"""
    
    print("🔧 Arreglando timing del viaje de Vale...")
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Get Vale's trip
        now_utc = datetime.now(timezone.utc)
        vale_trip = await db_client.get_latest_trip_by_whatsapp("+5491140383422")
        
        if not vale_trip:
            print("❌ No se encontró el viaje de Vale")
            return
        
        print(f"✅ Viaje encontrado: {vale_trip.flight_number}")
        
        # Calculate time until departure
        time_until = vale_trip.departure_date - now_utc
        hours_until = time_until.total_seconds() / 3600
        
        print(f"⏱️  Tiempo hasta salida: {hours_until:.1f} horas")
        
        # Calculate correct next_check_at
        correct_next_check = notifications_agent.calculate_next_check_time(vale_trip.departure_date, now_utc)
        
        print(f"🎯 Actualizando next_check_at a: {correct_next_check}")
        
        # Update in database
        result = await db_client.update_next_check_at(vale_trip.id, correct_next_check)
        
        if result.success:
            print("✅ **TIMING ARREGLADO EXITOSAMENTE**")
            
            # Calculate when next polling should happen
            minutes_until_next = (correct_next_check - now_utc).total_seconds() / 60
            print(f"⏭️  Próximo polling: En {minutes_until_next:.0f} minutos ({correct_next_check.strftime('%H:%M:%S')})")
            
            # Verify polling status
            trips_to_poll = await db_client.get_trips_to_poll(now_utc)
            vale_in_poll = any(str(t.id) == str(vale_trip.id) for t in trips_to_poll)
            
            if vale_in_poll:
                print("⚠️  ADVERTENCIA: El viaje aún aparece en polling actual")
            else:
                print("✅ CONFIRMADO: El viaje YA NO aparece en polling hasta la próxima hora")
                
        else:
            print(f"❌ Error al actualizar: {result.error}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        await db_client.close()
        await notifications_agent.close()


if __name__ == "__main__":
    asyncio.run(fix_vale_trip_timing()) 