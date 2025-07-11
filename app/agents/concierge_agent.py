"""ConciergeAgent for Bauhaus Travel - handles conversational WhatsApp support."""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog
from openai import OpenAI

from ..db.supabase_client import SupabaseDBClient
from ..models.database import Trip, DatabaseResult, TripContext
from .notifications_agent import NotificationsAgent

logger = structlog.get_logger()


class ConciergeAgent:
    """
    Autonomous conversational agent for traveler support via WhatsApp.
    
    Handles:
    - Inbound message processing and user identification
    - Context loading (trip, itinerary, conversation history)
    - AI response generation via GPT-4o mini
    - Document retrieval and sharing
    - Response sending via NotificationsAgent
    """
    
    def __init__(self):
        """Initialize the ConciergeAgent with required services."""
        self.db_client = SupabaseDBClient()
        
        # OpenAI setup
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            # IMPROVED: Better fallback handling
            logger.warning("openai_api_key_missing", 
                reason="OPENAI_API_KEY not found - using fallback responses")
            self.openai_client = None
        else:
            self.openai_client = OpenAI(api_key=openai_api_key)
        
        logger.info("concierge_agent_initialized", 
            openai_enabled=self.openai_client is not None
        )
    
    async def handle_inbound_message(
        self,
        whatsapp_number: str,
        message_body: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        message_sid: Optional[str] = None
    ) -> DatabaseResult:
        """
        Handle an inbound WhatsApp message and generate appropriate response.
        
        Args:
            whatsapp_number: Phone number without whatsapp: prefix
            message_body: Text content of the message
            media_url: Optional media URL if message contains media
            media_type: Optional media type (image, audio, etc.)
            message_sid: Twilio message SID for tracking
            
        Returns:
            DatabaseResult with processing status
        """
        logger.info("handling_inbound_message",
            from_number=whatsapp_number,
            message_length=len(message_body),
            has_media=media_url is not None,
            message_sid=message_sid
        )
        
        try:
            # Step 1: Identify user trip
            trip = await self.db_client.get_latest_trip_by_whatsapp(whatsapp_number)
            
            if not trip:
                logger.warning("no_trip_found", whatsapp_number=whatsapp_number)
                # Send fallback message for unidentified users
                return await self._send_no_trip_found_message(whatsapp_number)
            
            logger.info("trip_found", trip_id=trip.id, whatsapp_number=whatsapp_number)
            # Step 2: Detect intent for enhanced handling
            intent = self._detect_intent(message_body)
            
            # Step 3: Log user message in conversation
            logger.info("saving_conversation", trip_id=trip.id, sender="user", message=message_body)
            user_conv_result = await self.db_client.create_conversation(
                trip_id=trip.id,
                sender="user",
                message=message_body,
                intent=intent
            )
            logger.info("conversation_saved", trip_id=trip.id, sender="user", success=user_conv_result.success, error=user_conv_result.error if not user_conv_result.success else None)
            
            logger.info("reached_midpoint", trip_id=trip.id)
            # Step 4: Handle media if present
            if media_url:
                await self._handle_media_message(trip.id, media_url, media_type)
                # For MVP, acknowledge media but continue with text processing
                message_body += "\n[Imagen/audio recibido - procesando...]"
            
            # Step 5: Handle specific intents
            response_text = await self._handle_intent_based_response(trip, message_body, intent)
            
            # Step 6: Log bot response
            logger.info("saving_conversation", trip_id=trip.id, sender="bot", message=response_text)
            bot_conv_result = await self.db_client.create_conversation(
                trip_id=trip.id,
                sender="bot",
                message=response_text,
                intent=f"response_to_{intent}" if intent else None
            )
            logger.info("conversation_saved", trip_id=trip.id, sender="bot", success=bot_conv_result.success, error=bot_conv_result.error if not bot_conv_result.success else None)
            
            # Step 7: Send response via WhatsApp
            notifications_agent = NotificationsAgent()
            try:
                send_result = await notifications_agent.send_free_text(
                    whatsapp_number=whatsapp_number,
                    message=response_text
                )
                
                if send_result.success:
                    logger.info("concierge_response_sent",
                        to_number=whatsapp_number,
                        trip_id=str(trip.id),
                        intent=intent,
                        message_sid=send_result.data.get("message_sid")
                    )
                else:
                    logger.error("concierge_response_failed",
                        error_code="RESPONSE_SEND_FAILED",
                        to_number=whatsapp_number,
                        error=send_result.error
                    )
                    
            finally:
                await notifications_agent.close()
            
            return DatabaseResult(
                success=True,
                data={
                    "trip_id": str(trip.id),
                    "intent": intent,
                    "response_sent": send_result.success if 'send_result' in locals() else False,
                    "message_sid": send_result.data.get("message_sid") if 'send_result' in locals() and send_result.success else None
                }
            )
            
        except Exception as e:
            logger.error("inbound_message_handling_failed",
                error_code="MESSAGE_HANDLING_ERROR",
                from_number=whatsapp_number,
                error=str(e)
            )
            
            # Send fallback message to user
            await self._send_error_fallback_message(whatsapp_number)
            
            return DatabaseResult(
                success=False,
                error=str(e)
            )
    
    def _detect_intent(self, message: str) -> Optional[str]:
        """
        Detect user intent from message for enhanced handling.
        
        Args:
            message: User message text
            
        Returns:
            Detected intent or None
        """
        message_lower = message.lower()
        
        # Document-related intents
        if any(keyword in message_lower for keyword in ['boarding', 'pass', 'pase', 'embarque']):
            return "boarding_pass_request"
        
        if any(keyword in message_lower for keyword in ['hotel', 'reserva', 'voucher', 'hospedaje']):
            return "hotel_document_request"
        
        if any(keyword in message_lower for keyword in ['seguro', 'insurance', 'cobertura']):
            return "insurance_document_request"
        
        if any(keyword in message_lower for keyword in ['auto', 'car', 'rental', 'alquiler', 'coche']):
            return "car_rental_request"
        
        if any(keyword in message_lower for keyword in ['transfer', 'traslado', 'transporte']):
            return "transfer_document_request"
        
        # Itinerary-related intents
        if any(keyword in message_lower for keyword in ['itinerario', 'plan', 'actividades', 'agenda']):
            return "itinerary_request"
        
        # Flight-related intents
        if any(keyword in message_lower for keyword in ['vuelo', 'flight', 'gate', 'puerta', 'horario']):
            return "flight_info_request"
        
        # General help
        if any(keyword in message_lower for keyword in ['ayuda', 'help', 'que puedes', 'como']):
            return "help_request"
        
        # Greeting
        if any(keyword in message_lower for keyword in ['hola', 'hello', 'hi', 'hey', 'buenos']):
            return "greeting"
        
        return "general_query"
    
    async def _handle_intent_based_response(
        self, 
        trip: Trip, 
        message: str, 
        intent: Optional[str]
    ) -> str:
        """
        Generate response based on detected intent.
        
        Args:
            trip: Trip object
            message: User message
            intent: Detected intent
            
        Returns:
            Response text
        """
        try:
            # Handle document requests with actual document lookup
            if intent and intent.endswith("_request") and "document" in intent:
                document_type = self._map_intent_to_document_type(intent)
                return await self._handle_document_request(trip, document_type)
            
            elif intent == "boarding_pass_request":
                return await self._handle_document_request(trip, "boarding_pass")
            
            elif intent == "itinerary_request":
                return await self._handle_itinerary_request(trip)
            
            elif intent == "flight_info_request":
                return await self._handle_flight_info_request(trip)
            
            elif intent == "help_request":
                return self._generate_help_response(trip)
            
            elif intent == "greeting":
                return await self._generate_greeting_response(trip)
            
            else:
                # Default to AI-generated response for general queries
                context = await self._load_conversation_context(trip)
                return await self._generate_ai_response(context, message)
                
        except Exception as e:
            logger.error("intent_handling_failed",
                intent=intent,
                trip_id=str(trip.id),
                error=str(e)
            )
            # Fallback to AI response
            context = await self._load_conversation_context(trip)
            return await self._generate_ai_response(context, message)
    
    def _map_intent_to_document_type(self, intent: str) -> str:
        """Map intent to document type."""
        intent_mapping = {
            "hotel_document_request": "hotel_reservation",
            "insurance_document_request": "insurance",
            "car_rental_request": "car_rental", 
            "transfer_document_request": "transfer"
        }
        return intent_mapping.get(intent, "boarding_pass")
    
    async def _handle_document_request(self, trip: Trip, document_type: str) -> str:
        """
        Handle document request with actual document lookup.
        
        Args:
            trip: Trip object
            document_type: Type of document requested
            
        Returns:
            Response text with document info or not found message
        """
        try:
            # Get documents of requested type
            documents = await self.db_client.get_documents_by_trip(trip.id, document_type)
            
            if documents:
                # Document found - provide information
                doc = documents[0]  # Get most recent
                doc_name = doc.get('file_name', f'{document_type}.pdf')
                
                logger.info("document_found_for_user",
                    trip_id=str(trip.id),
                    document_type=document_type,
                    document_id=doc.get('id')
                )
                
                # FIXED: Actually send the document link
                document_url = doc.get('file_url') or doc.get('url') or doc.get('storage_path')
                
                if document_url:
                    # Document available with URL
                    return f"""¡Perfecto! Aquí tienes tu {self._get_document_type_spanish(document_type)} ✈️

📄 **{doc_name}**
📅 Subido: {doc.get('uploaded_at', 'Fecha no disponible')[:10]}
🔗 [Descargar documento]({document_url})

¿Necesitas algo más de tu viaje a {trip.destination_iata}?"""
                else:
                    # Document exists but no URL available
                    return f"""¡Encontré tu {self._get_document_type_spanish(document_type)}! 📄

📄 **{doc_name}**
📅 Subido: {doc.get('uploaded_at', 'Fecha no disponible')[:10]}

⚠️ *El archivo está en el sistema pero necesito configurar el link de descarga. Contacta a tu agencia para recibirlo.*

¿Puedo ayudarte con algo más?"""
            
            else:
                # Document not found
                logger.info("document_not_found",
                    trip_id=str(trip.id),
                    document_type=document_type
                )
                
                return f"""No encontré tu {self._get_document_type_spanish(document_type)} en el sistema. 📄

Esto puede pasar si:
• Aún no ha sido subido por tu agencia
• Se encuentra bajo un nombre diferente

Te recomiendo contactar a tu agencia de viajes para que suban el documento.

¿Puedo ayudarte con algo más mientras tanto?"""
        
        except Exception as e:
            logger.error("document_request_failed",
                trip_id=str(trip.id),
                document_type=document_type,
                error=str(e)
            )
            return "Disculpa, tengo problemas para acceder a tus documentos en este momento. ¿Podrías intentar de nuevo más tarde?"
    
    def _get_document_type_spanish(self, document_type: str) -> str:
        """Get Spanish name for document type."""
        spanish_names = {
            "boarding_pass": "pase de abordar",
            "hotel_reservation": "reserva de hotel",
            "car_rental": "reserva de auto",
            "transfer": "voucher de traslado",
            "insurance": "seguro de viaje",
            "tour_reservation": "reserva de tour"
        }
        return spanish_names.get(document_type, document_type)
    
    async def _handle_itinerary_request(self, trip: Trip) -> str:
        """Handle itinerary-specific requests."""
        try:
            itinerary_result = await self.db_client.get_latest_itinerary(trip.id)
            
            if itinerary_result.success and itinerary_result.data:
                itinerary = itinerary_result.data.get("parsed_itinerary", {})
                days = itinerary.get("days", [])
                
                if days:
                    response = f"¡Aquí tienes tu itinerario para {trip.destination_iata}! ✈️\n\n"
                    
                    for i, day in enumerate(days[:3]):  # Show first 3 days
                        response += f"**📅 Día {day.get('date', i+1)}:**\n"
                        items = day.get('items', [])
                        
                        for j, item in enumerate(items[:3], 1):  # Show first 3 items per day
                            response += f"{j}. {item.get('title', 'Actividad')}\n"
                        
                        if len(items) > 3:
                            response += f"   ... y {len(items) - 3} actividades más\n"
                        response += "\n"
                    
                    if len(days) > 3:
                        response += f"📝 *Tienes {len(days)} días planificados en total.*\n\n"
                    
                    response += "¿Te gustaría saber detalles de alguna actividad específica?"
                    
                    return response
            
            return f"""Aún no tienes un itinerario generado para tu viaje a {trip.destination_iata}. 

¿Te gustaría que prepare una propuesta de actividades basada en tu perfil? Solo dime "genera itinerario" y me pondré a trabajar en ello. 🎯"""
        
        except Exception as e:
            logger.error("itinerary_request_failed",
                trip_id=str(trip.id),
                error=str(e)
            )
            return "Disculpa, tengo problemas para acceder a tu itinerario. ¿Podrías intentar de nuevo?"
    
    async def _handle_flight_info_request(self, trip: Trip) -> str:
        """Handle flight information requests with real-time AeroAPI data."""
        from ..utils.timezone_utils import format_departure_time_local
        from ..services.aeroapi_client import AeroAPIClient
        
        # Get real-time flight status from AeroAPI
        aeroapi_client = AeroAPIClient()
        try:
            departure_date_str = trip.departure_date.strftime("%Y-%m-%d")
            current_status = await aeroapi_client.get_flight_status(
                trip.flight_number, 
                departure_date_str
            )
            
            # Use real-time status if available, fallback to database
            if current_status:
                flight_status = current_status.status
                gate_info = f"\n🚪 Puerta: {current_status.gate_origin}" if current_status.gate_origin else ""
                progress_info = f"\n✈️ Progreso: {current_status.progress_percent}%" if current_status.progress_percent > 0 else ""
            else:
                flight_status = trip.status or "Información no disponible"
                gate_info = ""
                progress_info = ""
            
        except Exception as e:
            logger.error("aeroapi_request_failed_in_concierge", 
                trip_id=str(trip.id),
                error=str(e)
            )
            flight_status = trip.status or "Información no disponible"
            gate_info = ""
            progress_info = ""
        
        # Convert UTC departure time to local airport time
        formatted_time = format_departure_time_local(trip.departure_date, trip.origin_iata)
        
        return f"""Aquí tienes la información de tu vuelo ✈️:

🛫 **{trip.flight_number}**
📍 {trip.origin_iata} → {trip.destination_iata}
📅 {trip.departure_date.strftime("%d/%m/%Y")} a las {formatted_time}
🎯 Estado: {flight_status}{gate_info}{progress_info}

ℹ️ *Te notificaré automáticamente sobre cualquier cambio de horario, puerta o retrasos.*

¿Necesitas alguna información específica sobre tu vuelo?"""
    
    def _generate_help_response(self, trip: Trip) -> str:
        """Generate help response showing available features."""
        return f"""¡Hola {trip.client_name}! Puedo ayudarte con tu viaje a {trip.destination_iata} 🌟

**¿Qué puedo hacer por ti?**
• 📋 Ver tu itinerario completo
• ✈️ Información de tu vuelo {trip.flight_number}
• 📄 Acceder a tus documentos:
  - Pase de abordar
  - Reserva de hotel
  - Seguro de viaje
  - Vouchers de traslados
• 🗨️ Responder preguntas sobre tu destino

**Solo escribe lo que necesitas**, por ejemplo:
- "itinerario"
- "pase de abordar"
- "¿qué hacer en {trip.destination_iata}?"

¿En qué te puedo ayudar hoy?"""
    
    async def _generate_greeting_response(self, trip: Trip) -> str:
        """Generate personalized greeting response."""
        # Check if we have itinerary to provide preview
        try:
            itinerary_result = await self.db_client.get_latest_itinerary(trip.id)
            
            if itinerary_result.success and itinerary_result.data:
                itinerary = itinerary_result.data.get("parsed_itinerary", {})
                days = itinerary.get("days", [])
                
                if days:
                    return f"""¡Hola {trip.client_name}! 👋

¡Qué emocionante tu viaje a {trip.destination_iata}! 

Tengo tu itinerario listo con {len(days)} días de actividades increíbles. Si quieres verlo completo, solo escribe "itinerario".

¿En qué te puedo ayudar hoy?"""
            
            return f"""¡Hola {trip.client_name}! 👋 

Todo listo para tu viaje a {trip.destination_iata} con el vuelo {trip.flight_number}.

¿En qué te puedo ayudar? Puedo mostrarte tu itinerario, documentos de viaje, o responder cualquier pregunta sobre tu destino."""
        
        except Exception:
            return f"""¡Hola {trip.client_name}! 👋 

¿Cómo estás? Estoy aquí para ayudarte con tu viaje a {trip.destination_iata}.

¿En qué te puedo ayudar hoy?"""
    
    async def _load_conversation_context(self, trip: Trip) -> Dict[str, Any]:
        """
        Load all relevant context for AI response generation.
        """
        context_obj = await self.db_client.get_complete_trip_context(trip.id)
        return context_obj.model_dump()
    
    async def _generate_ai_response(self, context: Dict[str, Any], user_message: str) -> str:
        """
        Generate AI response with loaded context - FIXED VERSION with fallbacks.
        """
        trip_id = context.get('trip', {}).get('id')
        trip = context.get('trip', {})
        
        # IMPROVED: Fallback if OpenAI not available
        if not self.openai_client:
            return self._generate_fallback_response(trip, user_message)
        
        try:
            # Build simplified prompt
            prompt = self._build_concierge_prompt_original(context, user_message)
            
            # Make OpenAI request with simplified response handling
            response = await self._make_openai_request(prompt)
            ai_response = response.choices[0].message.content.strip()
            
            # FIXED: Handle response as plain text, not JSON
            logger.info("ai_response_generated",
                trip_id=str(trip_id) if trip_id else None,
                tokens_used=response.usage.total_tokens,
                response_length=len(ai_response)
            )
            
            return ai_response
            
        except Exception as e:
            logger.error("ai_response_generation_failed",
                trip_id=str(trip_id) if trip_id else None,
                error=str(e)
            )
            
            # IMPROVED: Use fallback instead of generic error
            return self._generate_fallback_response(trip, user_message)
    
    def _generate_fallback_response(self, trip: Dict[str, Any], user_message: str) -> str:
        """
        Generate intelligent fallback response when OpenAI is unavailable.
        """
        client_name = trip.get('client_name', 'viajero')
        destination = trip.get('destination_iata', 'tu destino')
        
        # Smart fallback based on message content
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['hola', 'hello', 'hi', 'buenos']):
            return f"¡Hola {client_name}! 👋 Estoy aquí para ayudarte con tu viaje a {destination}. ¿En qué te puedo asistir?"
        
        elif any(word in message_lower for word in ['vuelo', 'flight', 'horario']):
            flight_number = trip.get('flight_number', 'tu vuelo')
            return f"Tu vuelo {flight_number} está programado. Para información actualizada, contacta a tu agencia de viajes. ¿Algo más en lo que pueda ayudarte?"
        
        elif any(word in message_lower for word in ['itinerario', 'plan', 'actividades']):
            return f"Para tu itinerario en {destination}, contacta a tu agencia de viajes. Ellos tienen toda la información detallada. ¿Te puedo ayudar con algo más?"
        
        else:
            return f"Gracias por tu mensaje, {client_name}. Para asistencia especializada con tu viaje a {destination}, te recomiendo contactar directamente a tu agencia de viajes. ¿Hay algo urgente en lo que pueda ayudarte?"
    
    async def _make_openai_request(self, prompt: str, model: str = "gpt-4o-mini"):
        """
        Make OpenAI request with optimized system prompt - FIXED VERSION.
        """
        import asyncio
        
        def sync_openai_call():
            return self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system", 
                        "content": "Eres un asistente de viajes experto de Nagori Travel. Responde siempre en español de manera concisa, empática y útil. Máximo 90 palabras."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150  # OPTIMIZED: Reduced for concise responses
            )
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_openai_call)
    
    def _build_concierge_prompt_original(self, context: Dict[str, Any], user_message: str) -> str:
        """
        Build optimized prompt for AI response generation - FIXED VERSION.
        """
        # Extract trip data
        trip = context.get('trip', {})
        recent_messages = context.get('recent_messages', [])  # FIXED: Use correct key
        
        # Format recent conversation (last 6 messages)
        conversation_context = ""
        if recent_messages:
            conversation_context = "\n\nCONVERSACIÓN RECIENTE:\n"
            for msg in recent_messages[-6:]:  # Last 6 messages
                sender = "Usuario" if msg.get('sender') == 'user' else "Asistente"
                conversation_context += f"{sender}: {msg.get('message', '')}\n"
        
        # Build simple, effective prompt
        prompt = f"""Eres el "Concierge 24/7" de Nagori Travel. Eres experto, formal y cálido.

INFORMACIÓN DEL VIAJE:
- Cliente: {trip.get('client_name', 'Viajero')}
- Vuelo: {trip.get('flight_number', 'N/A')} 
- Origen: {trip.get('origin_iata', 'N/A')} → Destino: {trip.get('destination_iata', 'N/A')}
- Fecha: {trip.get('departure_date', 'N/A')}
- Estado: {trip.get('status', 'Programado')}

{conversation_context}

MENSAJE ACTUAL DEL USUARIO: "{user_message}"

INSTRUCCIONES:
- Responde en español neutro, máximo 90 palabras
- Usa máximo 3 emojis
- Si no sabes algo, ofrece contactar a un agente humano
- Sé empático y útil
- Termina con una pregunta o llamada a la acción

RESPONDE DIRECTAMENTE (NO JSON, SOLO TEXTO):"""

        return prompt
    
    async def _handle_media_message(self, trip_id: UUID, media_url: str, media_type: Optional[str]):
        """
        Handle media messages for future processing.
        
        Args:
            trip_id: UUID of the trip
            media_url: URL of the media
            media_type: Type of media received
        """
        try:
            # For MVP: Just log media for future processing
            logger.info("media_message_received",
                trip_id=str(trip_id),
                media_url=media_url,
                media_type=media_type
            )
            
            # TODO: Store media reference for future AI processing
            # TODO: Add image recognition, audio transcription, etc.
            
        except Exception as e:
            logger.error("media_handling_failed",
                trip_id=str(trip_id),
                error=str(e)
            )
    
    async def _send_no_trip_found_message(self, whatsapp_number: str) -> DatabaseResult:
        """
        Send fallback message when no trip is found for user.
        
        Args:
            whatsapp_number: Phone number to send message to
            
        Returns:
            DatabaseResult with send status
        """
        fallback_message = """¡Hola! 👋 

No encontré viajes recientes asociados a este número. 

Para poder ayudarte mejor, por favor:
• Verifica que sea el mismo número usado al hacer la reserva
• O contacta a tu agencia de viajes

¡Estaremos aquí cuando tengas un viaje confirmado! ✈️"""
        
        notifications_agent = NotificationsAgent()
        try:
            result = await notifications_agent.send_free_text(
                whatsapp_number=whatsapp_number,
                message=fallback_message
            )
            return result
        finally:
            await notifications_agent.close()
    
    async def _send_error_fallback_message(self, whatsapp_number: str):
        """
        Send generic error message when processing fails.
        
        Args:
            whatsapp_number: Phone number to send message to
        """
        try:
            error_message = """Disculpa, estoy teniendo problemas técnicos en este momento. 🔧

Por favor intenta de nuevo en unos minutos, o contacta directamente a tu agencia de viajes.

¡Gracias por tu paciencia!"""
            
            notifications_agent = NotificationsAgent()
            try:
                await notifications_agent.send_free_text(
                    whatsapp_number=whatsapp_number,
                    message=error_message
                )
            finally:
                await notifications_agent.close()
                
        except Exception as e:
            logger.error("error_fallback_send_failed",
                to_number=whatsapp_number,
                error=str(e)
            )
    
    async def close(self):
        """Clean up resources."""
        await self.db_client.close()
        logger.info("concierge_agent_closed") 