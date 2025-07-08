#!/usr/bin/env python3
"""
Diagnóstico completo del problema AR1662 y inconsistencias de datos

Analiza:
1. Estado actual en trips vs flight_status_history 
2. Por qué no se enviaron notificaciones
3. Consistencia de datos
4. Polling schedule
"""

import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import SupabaseDBClient
from app.services.aeroapi_client import AeroAPIClient
from app.agents.notifications_agent import NotificationsAgent

async def diagnose_ar1662():
    """Diagnóstico completo del vuelo AR1662 de Vale"""
    
    print("🔍 DIAGNÓSTICO: AR1662 - Por qué no recibí notificaciones")
    print("=" * 70)
    
    db_client = SupabaseDBClient()
    aeroapi_client = AeroAPIClient()
    
    try:
        # 1. Buscar el trip AR1662 de Vale
        print("\n1️⃣ BUSCANDO TRIP AR1662...")
        
        # Query trips table
        trip_query = """
        SELECT id, client_name, flight_number, status, gate, departure_date, 
               next_check_at, metadata, inserted_at 
        FROM trips 
        WHERE flight_number = 'AR1662' 
        AND client_name ILIKE '%vale%'
        ORDER BY inserted_at DESC LIMIT 1
        """
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={
                "flight_number": "eq.AR1662",
                "client_name": "ilike.*Vale*",
                "select": "*",
                "limit": "1",
                "order": "inserted_at.desc"
            }
        )
        response.raise_for_status()
        trips_data = response.json()
        
        if not trips_data:
            print("❌ NO SE ENCONTRÓ AR1662 en trips table")
            return
        
        trip = trips_data[0]
        trip_id = trip["id"]
        
        print(f"✅ TRIP ENCONTRADO: {trip_id}")
        print(f"   Cliente: {trip['client_name']}")
        print(f"   Estado en DB: {trip['status']}")
        print(f"   Gate en DB: {trip['gate'] or 'NULL'}")
        print(f"   Departure: {trip['departure_date']}")
        print(f"   Next check: {trip['next_check_at']}")
        print(f"   Insertado: {trip['inserted_at']}")
        
        # 2. Revisar flight_status_history
        print(f"\n2️⃣ REVISANDO FLIGHT_STATUS_HISTORY para {trip_id}...")
        
        history_response = await db_client._client.get(
            f"{db_client.rest_url}/flight_status_history",
            params={
                "trip_id": f"eq.{trip_id}",
                "select": "*",
                "order": "recorded_at.desc",
                "limit": "10"
            }
        )
        history_response.raise_for_status()
        history_data = history_response.json()
        
        if not history_data:
            print("❌ NO HAY REGISTROS en flight_status_history")
            print("   🐞 PROBLEMA: El sistema nunca guardó estados del vuelo")
        else:
            print(f"✅ {len(history_data)} registros en flight_status_history")
            for i, record in enumerate(history_data[:5]):
                print(f"   {i+1}. {record['recorded_at']}: {record['status']}")
                print(f"      Gate: {record['gate_origin'] or 'NULL'}")
                print(f"      Est_out: {record['estimated_out'] or 'NULL'}")
        
        # 3. Obtener estado ACTUAL de AeroAPI
        print(f"\n3️⃣ CONSULTANDO ESTADO ACTUAL EN AEROAPI...")
        
        departure_date = datetime.fromisoformat(trip['departure_date'].replace('Z', '+00:00'))
        flight_date_str = departure_date.strftime("%Y-%m-%d")
        
        current_status = await aeroapi_client.get_flight_status(
            "AR1662", 
            flight_date_str
        )
        
        if not current_status:
            print("❌ AeroAPI no devolvió datos")
        else:
            print(f"✅ ESTADO ACTUAL EN AEROAPI:")
            print(f"   Status: {current_status.status}")
            print(f"   Gate: {current_status.gate_origin or 'NULL'}")
            print(f"   Est_out: {current_status.estimated_out or 'NULL'}")
            print(f"   Actual_out: {current_status.actual_out or 'NULL'}")
            print(f"   Progress: {current_status.progress_percent}%")
            print(f"   Cancelled: {current_status.cancelled}")
            
            # 4. COMPARAR: DB vs AeroAPI
            print(f"\n4️⃣ COMPARANDO: DATABASE vs AEROAPI")
            
            db_status = trip['status']
            api_status = current_status.status
            db_gate = trip['gate']
            api_gate = current_status.gate_origin
            
            if db_status != api_status:
                print(f"⚠️  STATUS INCONSISTENTE:")
                print(f"   DB: {db_status}")
                print(f"   API: {api_status}")
            else:
                print(f"✅ Status consistente: {db_status}")
            
            if db_gate != api_gate:
                print(f"⚠️  GATE INCONSISTENTE:")
                print(f"   DB: {db_gate or 'NULL'}")
                print(f"   API: {api_gate or 'NULL'}")
            else:
                print(f"✅ Gate consistente: {db_gate}")
        
        # 5. Revisar notifications_log
        print(f"\n5️⃣ REVISANDO NOTIFICACIONES ENVIADAS...")
        
        notif_response = await db_client._client.get(
            f"{db_client.rest_url}/notifications_log",
            params={
                "trip_id": f"eq.{trip_id}",
                "select": "*",
                "order": "sent_at.desc",
                "limit": "20"
            }
        )
        notif_response.raise_for_status()
        notif_data = notif_response.json()
        
        if not notif_data:
            print("❌ NO SE ENVIARON NOTIFICACIONES")
            print("   🐞 PROBLEMA: Sistema no detectó cambios o falló el envío")
        else:
            print(f"✅ {len(notif_data)} notificaciones enviadas:")
            for notif in notif_data:
                status_icon = "✅" if notif['delivery_status'] == 'SENT' else "❌"
                print(f"   {status_icon} {notif['sent_at']}: {notif['notification_type']}")
                print(f"      Template: {notif['template_name']}")
                print(f"      Status: {notif['delivery_status']}")
        
        # 6. Verificar si debería estar en polling
        print(f"\n6️⃣ VERIFICANDO SCHEDULE DE POLLING...")
        
        now_utc = datetime.now(timezone.utc)
        next_check_str = trip['next_check_at']
        
        if next_check_str:
            # Handle both with and without timezone
            if next_check_str.endswith('Z') or '+' in next_check_str:
                next_check = datetime.fromisoformat(next_check_str.replace('Z', '+00:00'))
            else:
                next_check = datetime.fromisoformat(next_check_str).replace(tzinfo=timezone.utc)
            
            time_until_check = next_check - now_utc
            
            print(f"   Próximo check: {next_check}")
            print(f"   Tiempo hasta check: {time_until_check}")
            
            if time_until_check.total_seconds() <= 0:
                print("✅ DEBERÍA estar siendo polled AHORA")
            else:
                print(f"⏰ Será polled en: {time_until_check}")
        else:
            print("❌ next_check_at es NULL - no será polled")
        
        # 7. Simular detección de cambios
        if history_data and current_status:
            print(f"\n7️⃣ SIMULANDO DETECCIÓN DE CAMBIOS...")
            
            latest_history = history_data[0]
            
            # Crear FlightStatus del historial
            from app.services.aeroapi_client import FlightStatus
            previous_status = FlightStatus(
                ident=latest_history["flight_number"],
                status=latest_history["status"],
                gate_origin=latest_history["gate_origin"],
                estimated_out=latest_history["estimated_out"],
                actual_out=latest_history["actual_out"]
            )
            
            # Detectar cambios
            changes = aeroapi_client.detect_flight_changes(current_status, previous_status)
            
            if changes:
                print(f"   🔍 SE DETECTARÍAN {len(changes)} cambios:")
                for change in changes:
                    print(f"      - {change['type']}: {change['old_value']} → {change['new_value']}")
                    print(f"        Notif: {change['notification_type']}")
            else:
                print("   ✅ No se detectarían cambios")
        
        # 8. Análisis final
        print(f"\n8️⃣ DIAGNÓSTICO FINAL")
        print("=" * 50)
        
        if not history_data:
            print("🚨 PROBLEMA PRINCIPAL: flight_status_history vacío")
            print("   → El sistema NUNCA hizo polling del vuelo")
            print("   → next_check_at podría estar mal configurado")
        elif not notif_data:
            print("🚨 PROBLEMA PRINCIPAL: No se enviaron notificaciones")
            print("   → El sistema polled pero no detectó cambios significativos")
            print("   → O falló la lógica de detección de cambios")
        else:
            print("✅ Sistema funcionó parcialmente")
            print("   → Revisar lógica de detección de cambios específicos")
        
        # 9. Recomendaciones
        print(f"\n9️⃣ RECOMENDACIONES DE CORRECCIÓN")
        print("-" * 40)
        print("1. Crear método update_trip_comprehensive()")
        print("2. Agregar sincronización automática trips ← flight_status_history")
        print("3. Modificar polling para actualizar TODA la info en trips")
        print("4. Agregar validación de consistencia de datos")
        print("5. Crear método manual de re-sync desde AeroAPI")
        
        return {
            "trip_id": trip_id,
            "has_history": bool(history_data),
            "has_notifications": bool(notif_data),
            "data_consistent": (
                trip['status'] == (current_status.status if current_status else trip['status']) and
                trip['gate'] == (current_status.gate_origin if current_status else trip['gate'])
            ),
            "should_be_polled": next_check_str and next_check <= now_utc if next_check_str else False
        }
        
    except Exception as e:
        print(f"💥 ERROR EN DIAGNÓSTICO: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(diagnose_ar1662()) 