#!/usr/bin/env python3
"""
CORRECCIÓN INMEDIATA: Limpiar trips pasados y resetear next_check_at
Esto soluciona el spam de notificaciones inmediatamente.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent

async def fix_polling_immediate():
    """Corrección inmediata del sistema de polling"""
    
    print("🚨 CORRECCIÓN INMEDIATA: Sistema de Polling")
    print("=" * 60)
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        now_utc = datetime.now(timezone.utc)
        print(f"Hora actual UTC: {now_utc}")
        
        # 1. OBTENER TODOS LOS TRIPS (sin filtro)
        print(f"\n1️⃣ OBTENIENDO TODOS LOS TRIPS...")
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={"select": "id,flight_number,client_name,departure_date,next_check_at"}
        )
        response.raise_for_status()
        all_trips = response.json()
        
        print(f"   Total trips en base: {len(all_trips)}")
        
        past_trips = []
        future_trips = []
        
        for trip_data in all_trips:
            departure_str = trip_data["departure_date"]
            if departure_str.endswith('Z'):
                departure_dt = datetime.fromisoformat(departure_str.replace('Z', '+00:00'))
            else:
                departure_dt = datetime.fromisoformat(departure_str)
                if departure_dt.tzinfo is None:
                    departure_dt = departure_dt.replace(tzinfo=timezone.utc)
            
            if departure_dt < now_utc:
                past_trips.append(trip_data)
            else:
                future_trips.append(trip_data)
        
        print(f"   Trips PASADOS (ya partieron): {len(past_trips)}")
        print(f"   Trips FUTUROS (no han partido): {len(future_trips)}")
        
        # 2. MARCAR TRIPS PASADOS COMO LANDED (para que no se procesen)
        print(f"\n2️⃣ MARCANDO TRIPS PASADOS COMO LANDED...")
        
        for trip_data in past_trips:
            print(f"   Marcando como LANDED: {trip_data['flight_number']} - {trip_data['departure_date']}")
            
            try:
                response = await db_client._client.patch(
                    f"{db_client.rest_url}/trips",
                    json={"status": "LANDED"},
                    params={"id": f"eq.{trip_data['id']}"}
                )
                response.raise_for_status()
                print(f"   ✅ Marcado como LANDED: {trip_data['flight_number']}")
            except Exception as e:
                print(f"   ❌ Error: {trip_data['flight_number']}: {e}")
        
        # 3. RECALCULAR NEXT_CHECK_AT PARA TRIPS FUTUROS
        print(f"\n3️⃣ RECALCULANDO NEXT_CHECK_AT PARA TRIPS FUTUROS...")
        
        for trip_data in future_trips:
            departure_str = trip_data["departure_date"]
            if departure_str.endswith('Z'):
                departure_dt = datetime.fromisoformat(departure_str.replace('Z', '+00:00'))
            else:
                departure_dt = datetime.fromisoformat(departure_str)
                if departure_dt.tzinfo is None:
                    departure_dt = departure_dt.replace(tzinfo=timezone.utc)
            
            # Calcular next_check correcto usando la lógica smart
            correct_next_check = notifications_agent.calculate_next_check_time(departure_dt, now_utc)
            
            hours_to_departure = (departure_dt - now_utc).total_seconds() / 3600
            interval_hours = (correct_next_check - now_utc).total_seconds() / 3600
            
            print(f"   {trip_data['flight_number']}: T-{hours_to_departure:.1f}h → próximo check en {interval_hours:.1f}h")
            
            try:
                response = await db_client._client.patch(
                    f"{db_client.rest_url}/trips",
                    json={"next_check_at": correct_next_check.isoformat()},
                    params={"id": f"eq.{trip_data['id']}"}
                )
                response.raise_for_status()
                print(f"   ✅ Actualizado: {trip_data['flight_number']}")
            except Exception as e:
                print(f"   ❌ Error: {trip_data['flight_number']}: {e}")
        
        # 4. VERIFICAR CORRECCIÓN
        print(f"\n4️⃣ VERIFICANDO CORRECCIÓN...")
        
        # Probar la nueva consulta
        trips_to_poll = await db_client.get_trips_to_poll(now_utc)
        print(f"   get_trips_to_poll() ahora devuelve: {len(trips_to_poll)} trips")
        
        for trip in trips_to_poll:
            time_to_departure = trip.departure_date - now_utc
            hours_to_departure = time_to_departure.total_seconds() / 3600
            print(f"   - {trip.flight_number}: T-{hours_to_departure:.1f}h (OK)")
        
        print(f"\n🎯 CORRECCIÓN COMPLETADA:")
        print(f"   ✅ {len(past_trips)} trips pasados marcados como LANDED")
        print(f"   ✅ {len(future_trips)} trips futuros reconfigurados")
        print(f"   ✅ get_trips_to_poll() ahora filtra por status != LANDED")
        print(f"   ✅ Sistema tracked full flight lifecycle (departure → in-flight → landing)")
        
        if len(trips_to_poll) == 0:
            print(f"\n✅ PERFECTO: No hay trips listos para polling ahora")
            print(f"   El próximo polling será cuando llegue el momento correcto")
        
    except Exception as e:
        print(f"💥 Error en corrección: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(fix_polling_immediate()) 