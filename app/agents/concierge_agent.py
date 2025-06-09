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
from ..models.database import Trip, DatabaseResult
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
            raise ValueError("Missing OPENAI_API_KEY in environment variables")
        
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        logger.info("concierge_agent_initialized")
    
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
                # Send fallback message for unidentified users
                return await self._send_no_trip_found_message(whatsapp_number)
            
            # Step 2: Detect intent for enhanced handling
            intent = self._detect_intent(message_body)
            
            # Step 3: Log user message in conversation
            await self.db_client.create_conversation(
                trip_id=trip.id,
                sender="user",
                message=message_body,
                intent=intent
            )
            
            # Step 4: Handle media if present
            if media_url:
                await self._handle_media_message(trip.id, media_url, media_type)
                # For MVP, acknowledge media but continue with text processing
                message_body += "\n[Imagen/audio recibido - procesando...]"
            
            # Step 5: Handle specific intents
            response_text = await self._handle_intent_based_response(trip, message_body, intent)
            
            # Step 6: Log bot response
            await self.db_client.create_conversation(
                trip_id=trip.id,
                sender="bot",
                message=response_text,
                intent=f"response_to_{intent}" if intent else None
            )
            
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
                
                # TODO: In Phase 3, actually send the document file
                # For now, acknowledge that we have it
                return f"""¡Perfecto! Tengo tu {self._get_document_type_spanish(document_type)}.

📄 **{doc_name}**
📅 Subido: {doc.get('uploaded_at', 'Fecha no disponible')[:10]}

🔄 *Próximamente podrás recibir el archivo directamente por WhatsApp.*

¿Necesitas algo más de tu viaje a {trip.destination_iata}?"""
            
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
        """Handle flight information requests."""
        departure_date = trip.departure_date.strftime("%d/%m/%Y a las %H:%M")
        
        return f"""Aquí tienes la información de tu vuelo ✈️:

🛫 **{trip.flight_number}**
📍 {trip.origin_iata} → {trip.destination_iata}
📅 {departure_date}
🎯 Estado: {trip.status}

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
        
        Args:
            trip: Trip object with traveler information
            
        Returns:
            Dict with complete context for AI prompt
        """
        context = {
            "trip": {
                "client_name": trip.client_name,
                "flight_number": trip.flight_number,
                "origin": trip.origin_iata,
                "destination": trip.destination_iata,
                "departure_date": trip.departure_date.strftime("%Y-%m-%d %H:%M"),
                "client_description": trip.client_description or "No profile provided"
            },
            "conversation_history": [],
            "itinerary": None,
            "documents": []
        }
        
        try:
            # Load recent conversation history
            conversations = await self.db_client.get_recent_conversations(trip.id, limit=10)
            context["conversation_history"] = conversations
            
            # Load latest itinerary if exists
            itinerary_result = await self.db_client.get_latest_itinerary(trip.id)
            if itinerary_result.success and itinerary_result.data:
                context["itinerary"] = itinerary_result.data.get("parsed_itinerary", {})
            
            # Load available documents
            documents = await self.db_client.get_documents_by_trip(trip.id)
            context["documents"] = [
                {
                    "type": doc.get("type"),
                    "file_name": doc.get("file_name"),
                    "uploaded_at": doc.get("uploaded_at")
                }
                for doc in documents
            ]
            
            logger.info("context_loaded",
                trip_id=str(trip.id),
                conversation_count=len(context["conversation_history"]),
                has_itinerary=context["itinerary"] is not None,
                documents_count=len(context["documents"])
            )
            
        except Exception as e:
            logger.error("context_loading_failed",
                trip_id=str(trip.id),
                error=str(e)
            )
            # Continue with partial context
        
        return context
    
    async def _generate_ai_response(self, context: Dict[str, Any], user_message: str) -> str:
        """
        Generate AI response using GPT-4o mini with loaded context.
        
        Args:
            context: Complete conversation context
            user_message: Current user message
            
        Returns:
            Generated response text
        """
        try:
            # Build comprehensive prompt
            prompt = self._build_concierge_prompt(context, user_message)
            
            # Call OpenAI with timeout
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente de viajes experto y amigable. Ayudas a viajeros con información sobre sus itinerarios, vuelos y documentos. Responde en español de manera concisa y útil."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            ai_response = response.choices[0].message.content
            
            logger.info("ai_response_generated",
                tokens_used=response.usage.total_tokens,
                response_length=len(ai_response)
            )
            
            return ai_response.strip()
            
        except Exception as e:
            logger.error("ai_response_generation_failed",
                error_code="AI_GENERATION_ERROR",
                error=str(e)
            )
            return "Disculpa, estoy teniendo problemas técnicos. ¿Podrías intentar de nuevo en un momento?"
    
    def _build_concierge_prompt(self, context: Dict[str, Any], user_message: str) -> str:
        """
        Build comprehensive prompt for AI response generation.
        
        Args:
            context: Complete conversation context
            user_message: Current user message
            
        Returns:
            Complete prompt string
        """
        # Format trip information
        trip_info = f"""
INFORMACIÓN DEL VIAJE:
- Viajero: {context['trip']['client_name']}
- Vuelo: {context['trip']['flight_number']}
- Ruta: {context['trip']['origin']} → {context['trip']['destination']}
- Salida: {context['trip']['departure_date']}
- Perfil: {context['trip']['client_description']}
"""
        
        # Format conversation history
        history_text = ""
        if context.get("conversation_history"):
            history_text = "\nHISTORIAL DE CONVERSACIÓN RECIENTE:\n"
            for conv in context["conversation_history"][-6:]:  # Last 3 exchanges
                sender_label = "Usuario" if conv["sender"] == "user" else "Asistente"
                history_text += f"{sender_label}: {conv['message']}\n"
        
        # Format itinerary info
        itinerary_text = ""
        if context.get("itinerary") and context["itinerary"].get("days"):
            itinerary_text = f"\nITINERARIO DISPONIBLE:\n"
            for day in context["itinerary"]["days"][:2]:  # First 2 days summary
                itinerary_text += f"Día {day['date']}: {len(day.get('items', []))} actividades\n"
        
        # Format available documents
        docs_text = ""
        if context.get("documents"):
            doc_types = [doc["type"] for doc in context["documents"]]
            docs_text = f"\nDOCUMENTOS DISPONIBLES: {', '.join(set(doc_types))}"
        
        prompt = f"""{trip_info}{history_text}{itinerary_text}{docs_text}

MENSAJE ACTUAL DEL USUARIO: {user_message}

INSTRUCCIONES:
- Responde de manera amigable y profesional en español
- Si preguntan por itinerario y está disponible, ofrece detalles específicos
- Si preguntan por documentos, confirma qué tienes disponible
- Si no tienes la información, sé honesto y ofrece alternativas
- Mantén respuestas concisas (máximo 200 palabras)
- Si detectas una pregunta urgente sobre vuelos, prioriza esa información

RESPUESTA:"""
        
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