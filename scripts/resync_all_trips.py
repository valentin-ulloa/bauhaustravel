#!/usr/bin/env python3
"""
Manual resync script for all trips with AeroAPI data.

This script addresses the critical data consistency issue by:
1. Fetching current flight status from AeroAPI for all active trips
2. Updating trips table with comprehensive flight data
3. Attempting to update flight_status_history (if permissions allow)
4. Providing detailed reporting on data inconsistencies found and fixed
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import SupabaseDBClient
from app.services.aeroapi_client import AeroAPIClient

async def resync_all_trips():
    """Resync all active trips with current AeroAPI data"""
    
    print("🔄 RESINCRONIZACIÓN MASIVA DE TRIPS CON AEROAPI")
    print("=" * 60)
    print("Propósito: Corregir inconsistencias de datos en trips table")
    print()
    
    db_client = SupabaseDBClient()
    aeroapi_client = AeroAPIClient()
    
    try:
        # Get all trips that are still active (not too old)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=2)
        
        print("1️⃣ OBTENIENDO TRIPS ACTIVOS...")
        
        response = await db_client._client.get(
            f"{db_client.rest_url}/trips",
            params={
                "departure_date": f"gte.{cutoff_date.isoformat()}",
                "select": "*",
                "order": "departure_date.desc"
            }
        )
        response.raise_for_status()
        trips_data = response.json()
        
        print(f"✅ Encontrados {len(trips_data)} trips activos (desde {cutoff_date.strftime('%Y-%m-%d')})")
        
        if not trips_data:
            print("ℹ️  No hay trips para resincronizar")
            return
        
        # Process each trip
        total_processed = 0
        total_updated = 0
        total_errors = 0
        inconsistencies_found = 0
        
        print(f"\n2️⃣ PROCESANDO {len(trips_data)} TRIPS...")
        print("-" * 50)
        
        for i, trip_data in enumerate(trips_data, 1):
            trip_id = trip_data["id"]
            flight_number = trip_data["flight_number"]
            client_name = trip_data["client_name"]
            departure_date = trip_data["departure_date"]
            current_status = trip_data["status"]
            current_gate = trip_data["gate"]
            
            print(f"\n{i:2d}. {flight_number} - {client_name}")
            print(f"    Salida: {departure_date}")
            print(f"    Estado actual en DB: {current_status}")
            print(f"    Gate actual en DB: {current_gate or 'NULL'}")
            
            try:
                # Get fresh data from AeroAPI
                departure_dt = datetime.fromisoformat(departure_date.replace('Z', '+00:00'))
                flight_date_str = departure_dt.strftime("%Y-%m-%d")
                
                fresh_status = await aeroapi_client.get_flight_status(
                    flight_number,
                    flight_date_str
                )
                
                if not fresh_status:
                    print(f"    ⚠️  AeroAPI: Sin datos disponibles")
                    total_errors += 1
                    continue
                
                # Compare data
                api_status = fresh_status.status
                api_gate = fresh_status.gate_origin
                api_estimated_out = fresh_status.estimated_out
                
                print(f"    AeroAPI: {api_status}")
                print(f"    Gate API: {api_gate or 'NULL'}")
                
                # Check for inconsistencies
                status_inconsistent = current_status != api_status
                gate_inconsistent = current_gate != api_gate
                
                if status_inconsistent or gate_inconsistent:
                    inconsistencies_found += 1
                    print(f"    🚨 INCONSISTENCIA DETECTADA:")
                    
                    if status_inconsistent:
                        print(f"       Status: DB='{current_status}' ≠ API='{api_status}'")
                    if gate_inconsistent:
                        print(f"       Gate: DB='{current_gate}' ≠ API='{api_gate}'")
                    
                    # Resync using the new comprehensive method
                    resync_result = await db_client.resync_trip_from_aeroapi(trip_id)
                    
                    if resync_result.success:
                        print(f"    ✅ RESINCRONIZADO exitosamente")
                        total_updated += 1
                        
                        # Show what was updated
                        if resync_result.data and "flight_status" in resync_result.data:
                            flight_status = resync_result.data["flight_status"]
                            print(f"       Nuevo estado: {flight_status.get('status')}")
                            print(f"       Nuevo gate: {flight_status.get('gate') or 'NULL'}")
                    else:
                        print(f"    ❌ Error en resync: {resync_result.error}")
                        total_errors += 1
                else:
                    print(f"    ✅ Datos consistentes")
                
                total_processed += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"    💥 Error procesando: {e}")
                total_errors += 1
                total_processed += 1
        
        # Summary report
        print(f"\n3️⃣ REPORTE FINAL")
        print("=" * 40)
        print(f"📊 Trips procesados: {total_processed}")
        print(f"🚨 Inconsistencias encontradas: {inconsistencies_found}")
        print(f"✅ Trips actualizados: {total_updated}")
        print(f"❌ Errores: {total_errors}")
        
        if inconsistencies_found > 0:
            consistency_rate = ((total_processed - inconsistencies_found) / total_processed) * 100
            print(f"📈 Tasa de consistencia original: {consistency_rate:.1f}%")
        
        if total_updated > 0:
            print(f"\n🎉 CORRECCIÓN EXITOSA:")
            print(f"   {total_updated} trips ahora tienen datos actualizados")
            print(f"   El sistema ya no debería mostrar información desactualizada")
        
        # Special handling for AR1662
        ar1662_trips = [t for t in trips_data if t["flight_number"] == "AR1662"]
        if ar1662_trips:
            print(f"\n🔍 ESTADO ESPECÍFICO AR1662:")
            for trip in ar1662_trips:
                print(f"   Trip ID: {trip['id']}")
                print(f"   Cliente: {trip['client_name']}")
                print(f"   Estado: {trip['status']}")
                print(f"   Gate: {trip['gate'] or 'NULL'}")
                print(f"   Next check: {trip['next_check_at']}")
        
        print(f"\n📋 PRÓXIMOS PASOS:")
        print("1. Verificar que el polling automático use update_trip_comprehensive()")
        print("2. Configurar permisos para flight_status_history si es necesario")
        print("3. Monitorear que no se repitan las inconsistencias")
        
    except Exception as e:
        print(f"💥 ERROR EN RESINCRONIZACIÓN: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()

async def resync_specific_trip(trip_id_or_flight_number: str):
    """Resync a specific trip by ID or flight number"""
    
    print(f"🔄 RESINCRONIZACIÓN ESPECÍFICA: {trip_id_or_flight_number}")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    
    try:
        # Try to find trip by ID first, then by flight number
        trip_data = None
        
        # Check if it's a UUID (trip ID)
        if len(trip_id_or_flight_number) == 36 and "-" in trip_id_or_flight_number:
            trip_result = await db_client.get_trip_by_id(trip_id_or_flight_number)
            if trip_result.success:
                trip_data = trip_result.data
        
        # If not found, search by flight number
        if not trip_data:
            response = await db_client._client.get(
                f"{db_client.rest_url}/trips",
                params={
                    "flight_number": f"eq.{trip_id_or_flight_number}",
                    "select": "*",
                    "order": "departure_date.desc",
                    "limit": "1"
                }
            )
            response.raise_for_status()
            trips_list = response.json()
            
            if trips_list:
                trip_data = trips_list[0]
        
        if not trip_data:
            print(f"❌ No se encontró trip con ID/flight: {trip_id_or_flight_number}")
            return
        
        trip_id = trip_data["id"]
        
        print(f"✅ Trip encontrado:")
        print(f"   ID: {trip_id}")
        print(f"   Flight: {trip_data['flight_number']}")
        print(f"   Cliente: {trip_data['client_name']}")
        print(f"   Estado actual: {trip_data['status']}")
        print(f"   Gate actual: {trip_data['gate'] or 'NULL'}")
        
        # Perform resync
        print(f"\n🔄 Ejecutando resincronización...")
        
        resync_result = await db_client.resync_trip_from_aeroapi(trip_id)
        
        if resync_result.success:
            print(f"✅ RESINCRONIZACIÓN EXITOSA")
            
            if resync_result.data and "flight_status" in resync_result.data:
                flight_status = resync_result.data["flight_status"]
                print(f"   Nuevo estado: {flight_status.get('status')}")
                print(f"   Nuevo gate: {flight_status.get('gate') or 'NULL'}")
                print(f"   Estimated out: {flight_status.get('estimated_out') or 'NULL'}")
                print(f"   Progreso: {flight_status.get('progress')}%")
        else:
            print(f"❌ Error en resincronización: {resync_result.error}")
    
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db_client.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Resync specific trip
        trip_identifier = sys.argv[1]
        asyncio.run(resync_specific_trip(trip_identifier))
    else:
        # Resync all trips
        asyncio.run(resync_all_trips()) 