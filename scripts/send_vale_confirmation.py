#!/usr/bin/env python3
"""
Script to manually send booking confirmation to Vale for trip ac544252-065c-4565-a1dc-8231e80b1af9
"""

import asyncio
import os
import sys
from uuid import UUID

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.db.supabase_client import SupabaseDBClient
from app.models.database import Trip
import structlog

logger = structlog.get_logger()


async def send_vale_confirmation():
    """Send booking confirmation to Vale manually"""
    
    print("📱 Enviando confirmación de reserva a Vale...")
    
    # Vale's trip ID from the creation
    trip_id = UUID("ac544252-065c-4565-a1dc-8231e80b1af9")
    
    db_client = SupabaseDBClient()
    agent = None
    
    try:
        # Get the trip from database
        print(f"🔍 Buscando trip ID: {trip_id}")
        result = await db_client.get_trip_by_id(trip_id)
        
        if not result.success:
            print(f"❌ ERROR: No se encontró el trip: {result.error}")
            return False
        
        # Create Trip object
        trip_data = result.data
        trip = Trip(**trip_data)
        
        print(f"✅ Trip encontrado:")
        print(f"   Cliente: {trip.client_name}")
        print(f"   WhatsApp: {trip.whatsapp}")
        print(f"   Vuelo: {trip.flight_number}")
        print(f"   Ruta: {trip.origin_iata} → {trip.destination_iata}")
        print(f"   Fecha: {trip.departure_date.strftime('%d/%m/%Y %H:%M')} UTC")
        
        # Check if confirmation already sent
        print(f"\n🔍 Verificando historial de notificaciones...")
        notifications = await db_client.get_notification_history(trip_id, "RESERVATION_CONFIRMATION")
        
        sent_confirmations = [n for n in notifications if n.delivery_status == "SENT"]
        if sent_confirmations:
            print(f"⚠️  Ya se envió confirmación:")
            for notif in sent_confirmations:
                print(f"   - Enviado: {notif.sent_at}")
                print(f"   - Template: {notif.template_name}")
                print(f"   - Twilio SID: {notif.twilio_message_sid}")
            
            user_input = input(f"\n¿Enviar confirmación de nuevo? (y/N): ")
            if user_input.lower() != 'y':
                print(f"🛑 Cancelado por usuario")
                return False
        
        # Initialize NotificationsAgent
        print(f"\n📨 Enviando confirmación de reserva...")
        agent = NotificationsAgent()
        
        # Send booking confirmation
        result = await agent.send_notification(
            trip=trip,
            notification_type=NotificationType.RESERVATION_CONFIRMATION
        )
        
        if result.success:
            message_sid = result.data.get("message_sid")
            print(f"✅ CONFIRMACIÓN ENVIADA EXITOSAMENTE!")
            print(f"   WhatsApp: {trip.whatsapp}")
            print(f"   Twilio Message SID: {message_sid}")
            print(f"   Template: RESERVATION_CONFIRMATION")
            return True
        else:
            print(f"❌ ERROR enviando confirmación: {result.error}")
            return False
    
    except Exception as e:
        print(f"💥 EXCEPCIÓN: {str(e)}")
        return False
    
    finally:
        if agent:
            await agent.close()
        await db_client.close()


async def main():
    """Main function"""
    print("📧 Envío manual de confirmación - Vale")
    print("=" * 50)
    
    success = await send_vale_confirmation()
    
    if success:
        print(f"\n🎉 ¡Confirmación enviada a Vale!")
        print(f"📱 Revisa tu WhatsApp +5491140383422")
        print(f"💬 Deberías recibir la confirmación del AR 1662")
    else:
        print(f"\n😞 No se pudo enviar la confirmación.")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 