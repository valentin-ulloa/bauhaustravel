#!/usr/bin/env python3
"""
Simple AR1662 diagnosis and fix script
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID
from app.db.supabase_client import SupabaseDBClient
from app.services.aeroapi_client import AeroAPIClient

async def fix_ar1662():
    """Simple fix for AR1662 with detailed debugging"""
    
    print("🔧 DIAGNÓSTICO Y CORRECCIÓN SIMPLE: AR1662")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    aeroapi_client = AeroAPIClient()
    
    try:
        # 1. Get AR1662 trip
        print("1️⃣ Buscando AR1662...")
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={
                "flight_number": "eq.AR1662",
                "select": "*",
                "order": "departure_date.desc",
                "limit": "1"
            }
        )
        response.raise_for_status()
        trips_data = response.json()
        
        if not trips_data:
            print("❌ No se encontró AR1662")
            return
        
        trip = trips_data[0]
        trip_id = trip["id"]
        
        print(f"✅ Trip encontrado: {trip_id}")
        print(f"   Cliente: {trip['client_name']}")
        print(f"   Estado DB: {trip['status']}")
        print(f"   Gate DB: {trip['gate'] or 'NULL'}")
        print(f"   Departure: {trip['departure_date']}")
        
        # 2. Get fresh data from AeroAPI
        print(f"\n2️⃣ Consultando AeroAPI...")
        
        departure_dt = datetime.fromisoformat(trip['departure_date'].replace('Z', '+00:00'))
        flight_date_str = departure_dt.strftime("%Y-%m-%d")
        
        fresh_status = await aeroapi_client.get_flight_status("AR1662", flight_date_str)
        
        if not fresh_status:
            print("❌ AeroAPI sin datos")
            return
        
        print(f"✅ AeroAPI datos:")
        print(f"   Status: {fresh_status.status}")
        print(f"   Gate: {fresh_status.gate_origin or 'NULL'}")
        print(f"   Estimated out: {fresh_status.estimated_out or 'NULL'}")
        print(f"   Progress: {fresh_status.progress_percent}%")
        
        # 3. Compare and update manually
        print(f"\n3️⃣ Comparando datos...")
        
        needs_update = (
            trip['status'] != fresh_status.status or
            trip['gate'] != fresh_status.gate_origin
        )
        
        if needs_update:
            print("🚨 DATOS INCONSISTENTES - Actualizando...")
            
            # Manual update using direct API call
            update_data = {
                "status": fresh_status.status,
                "gate": fresh_status.gate_origin
            }
            
            # Add estimated_out to departure_date if different
            if fresh_status.estimated_out:
                try:
                    estimated_dt = datetime.fromisoformat(
                        fresh_status.estimated_out.replace('Z', '+00:00')
                    )
                    update_data["departure_date"] = estimated_dt.isoformat()
                    print(f"   📅 Actualizando departure_date: {estimated_dt}")
                except Exception as e:
                    print(f"   ⚠️  Error parsing estimated_out: {e}")
            
            # Add comprehensive metadata
            metadata = {
                "last_aeroapi_sync": datetime.now(timezone.utc).isoformat(),
                "manual_resync": True,
                "flight_data": {
                    "gate_destination": fresh_status.gate_destination,
                    "estimated_in": fresh_status.estimated_in,
                    "actual_out": fresh_status.actual_out,
                    "actual_in": fresh_status.actual_in,
                    "aircraft_type": fresh_status.aircraft_type,
                    "progress_percent": fresh_status.progress_percent,
                    "cancelled": fresh_status.cancelled,
                    "diverted": fresh_status.diverted
                }
            }
            update_data["metadata"] = metadata
            
            # Execute update
            update_response = await db_client._client.patch(
                f"{db_client.rest_url}/trips",
                params={"id": f"eq.{trip_id}"},
                json=update_data
            )
            update_response.raise_for_status()
            
            updated_trip = update_response.json()
            
            if updated_trip:
                print("✅ TRIP ACTUALIZADO EXITOSAMENTE")
                print(f"   Nuevo status: {fresh_status.status}")
                print(f"   Nuevo gate: {fresh_status.gate_origin or 'NULL'}")
                print(f"   Metadata actualizada: ✅")
            else:
                print("❌ Error: respuesta vacía del update")
        else:
            print("✅ Datos ya consistentes")
        
        # 4. Check if next_check_at needs adjustment
        print(f"\n4️⃣ Verificando polling schedule...")
        
        next_check_str = trip['next_check_at']
        if next_check_str:
            # Handle timezone
            if next_check_str.endswith('Z') or '+' in next_check_str:
                next_check = datetime.fromisoformat(next_check_str.replace('Z', '+00:00'))
            else:
                next_check = datetime.fromisoformat(next_check_str).replace(tzinfo=timezone.utc)
            
            now_utc = datetime.now(timezone.utc)
            time_until_check = next_check - now_utc
            
            print(f"   Next check: {next_check}")
            print(f"   Time until: {time_until_check}")
            
            if time_until_check.total_seconds() <= 0:
                print("✅ Debería estar en polling ahora")
            else:
                hours = time_until_check.total_seconds() / 3600
                print(f"⏰ Será polled en {hours:.1f} horas")
        
        print(f"\n🎉 CORRECCIÓN COMPLETADA")
        print(f"   AR1662 ahora tiene datos actualizados en trips table")
        print(f"   El sistema debería mostrar información consistente")
        
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(fix_ar1662()) 