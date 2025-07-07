#!/usr/bin/env python3
"""
Script to create Vale's trip: AR 1662, EZE->BRC, 08-07-2025 04:15
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.models.database import TripCreate
from uuid import UUID
import structlog

logger = structlog.get_logger()


async def create_vale_trip():
    """Create Vale's business trip in Supabase"""
    
    print("🛫 Creando viaje de Vale en Supabase...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Vale's trip data
        departure_datetime = datetime(2025, 7, 8, 4, 15, 0, tzinfo=timezone.utc)
        
        trip_data = TripCreate(
            client_name="Valentin",
            whatsapp="+5491140383422",  # Argentina format
            flight_number="AR1662",
            origin_iata="EZE",
            destination_iata="BRC", 
            departure_date=departure_datetime,
            status="SCHEDULED",
            client_description="Viaje de negocios de 3 días - Bariloche",
            metadata={
                "trip_type": "business",
                "duration_days": 3,
                "check_in_sector": "176-190",
                "terminal_sector": "D",
                "gate": "Por confirmar",
                "created_by": "vale_manual_entry"
            },
            agency_id=UUID("00000000-0000-0000-0000-000000000001")  # Default agency
        )
        
        print(f"📋 Datos del viaje:")
        print(f"   Cliente: {trip_data.client_name}")
        print(f"   WhatsApp: {trip_data.whatsapp}")
        print(f"   Vuelo: {trip_data.flight_number}")
        print(f"   Ruta: {trip_data.origin_iata} → {trip_data.destination_iata}")
        print(f"   Fecha/Hora: {departure_datetime.strftime('%d/%m/%Y %H:%M')} UTC")
        print(f"   Descripción: {trip_data.client_description}")
        
        # Check for duplicates first
        print(f"\n🔍 Verificando duplicados...")
        duplicate_check = await db_client.check_duplicate_trip(
            trip_data.whatsapp,
            trip_data.flight_number,
            trip_data.departure_date
        )
        
        if duplicate_check.success and duplicate_check.data.get("exists"):
            print(f"⚠️  DUPLICADO DETECTADO: Ya existe un viaje con estos datos")
            print(f"   WhatsApp: {trip_data.whatsapp}")
            print(f"   Vuelo: {trip_data.flight_number}")
            print(f"   Fecha: {trip_data.departure_date.strftime('%Y-%m-%d')}")
            return False
        
        # Create the trip
        print(f"\n💾 Creando viaje en Supabase...")
        result = await db_client.create_trip(trip_data)
        
        if result.success:
            trip_id = result.data.get("id")
            print(f"✅ VIAJE CREADO EXITOSAMENTE!")
            print(f"   Trip ID: {trip_id}")
            print(f"   Cliente: {result.data.get('client_name')}")
            print(f"   Vuelo: {result.data.get('flight_number')}")
            print(f"   WhatsApp: {result.data.get('whatsapp')}")
            
            # Calculate time until departure
            now = datetime.now(timezone.utc)
            time_until = departure_datetime - now
            hours_until = time_until.total_seconds() / 3600
            
            print(f"\n⏰ Tiempo hasta la salida: {hours_until:.1f} horas")
            
            if hours_until > 24:
                print(f"📅 Se enviará recordatorio 24h antes: {(departure_datetime - timezone.utc.localize(datetime.now())).total_seconds() / 3600:.1f} horas desde ahora")
            else:
                print(f"⚡ Viaje en menos de 24h - se debería enviar recordatorio inmediato")
            
            return True
        else:
            print(f"❌ ERROR al crear viaje: {result.error}")
            return False
    
    except Exception as e:
        print(f"💥 EXCEPCIÓN: {str(e)}")
        return False
    
    finally:
        await db_client.close()


async def main():
    """Main function"""
    print("🚁 Script de creación de viaje - Vale")
    print("=" * 50)
    
    success = await create_vale_trip()
    
    if success:
        print(f"\n🎉 ¡Listo Vale! Tu viaje AR 1662 está en el sistema.")
        print(f"📱 Recibirás notificaciones en +5491140383422")
        print(f"🛎️  El sistema monitoreará tu vuelo automáticamente")
    else:
        print(f"\n😞 Hubo un problema creando el viaje. Revisa los logs.")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 