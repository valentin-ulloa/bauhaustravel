#!/usr/bin/env python3
"""
Test AR1662 with different dates to find available data
"""

import asyncio
from datetime import datetime, timezone, timedelta
from app.services.aeroapi_client import AeroAPIClient

async def test_ar1662_dates():
    """Test AR1662 with various dates to find available data"""
    
    print("🔍 PRUEBA DE FECHAS PARA AR1662")
    print("=" * 40)
    
    aeroapi_client = AeroAPIClient()
    
    # Test dates around the scheduled departure
    base_date = datetime(2025, 7, 8)
    test_dates = []
    
    # Add dates from -7 days to +7 days
    for i in range(-7, 8):
        test_date = base_date + timedelta(days=i)
        test_dates.append(test_date.strftime("%Y-%m-%d"))
    
    print(f"Probando {len(test_dates)} fechas para AR1662...")
    print()
    
    found_data = False
    
    for date_str in test_dates:
        try:
            print(f"📅 Probando {date_str}...", end=" ")
            
            status = await aeroapi_client.get_flight_status("AR1662", date_str)
            
            if status:
                found_data = True
                print("✅ DATOS ENCONTRADOS!")
                print(f"   Status: {status.status}")
                print(f"   Gate: {status.gate_origin or 'NULL'}")
                print(f"   Estimated out: {status.estimated_out or 'NULL'}")
                print(f"   Progress: {status.progress_percent}%")
                print(f"   Cancelled: {status.cancelled}")
                
                if status.origin_iata and status.destination_iata:
                    print(f"   Route: {status.origin_iata} → {status.destination_iata}")
                
                print()
            else:
                print("❌ Sin datos")
                
        except Exception as e:
            print(f"💥 Error: {e}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.3)
    
    if not found_data:
        print("\n🚨 NO SE ENCONTRARON DATOS PARA AR1662 EN NINGUNA FECHA")
        print("\nPosibles causas:")
        print("1. Número de vuelo incorrecto")
        print("2. Vuelo cancelado/no existe")
        print("3. Aerolínea no cubierta por AeroAPI")
        print("4. Fecha muy futura (AeroAPI tiene límites)")
        
        # Test with other AR flights
        print("\n🔍 Probando otros vuelos AR...")
        
        test_flights = ["AR1661", "AR1663", "AR1100", "AR1200"]
        
        for flight in test_flights:
            try:
                print(f"✈️  Probando {flight} para 2025-07-08...", end=" ")
                status = await aeroapi_client.get_flight_status(flight, "2025-07-08")
                
                if status:
                    print("✅ Tiene datos!")
                else:
                    print("❌ Sin datos")
                    
            except Exception as e:
                print(f"💥 Error: {e}")
    
    else:
        print("✅ Se encontraron datos para AR1662 en al menos una fecha")
    
    print(f"\n📋 ANÁLISIS:")
    print("Si no hay datos disponibles en AeroAPI:")
    print("1. Verificar que AR1662 es el número correcto")
    print("2. Confirmar que el vuelo existe en esa fecha")
    print("3. Posiblemente usar datos simulados para pruebas")

if __name__ == "__main__":
    asyncio.run(test_ar1662_dates()) 