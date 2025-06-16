# Technical Guidelines

## Tech Stack
- Python 3.11+, FastAPI, async/await
- Supabase for persistence (PostgreSQL, vector store)
- structlog for JSON logging
- Pydantic v2 for models & validation
- httpx (async) for external API calls
- Tests: pytest + httpx-async-client

## Infrastructure & Services

### Twilio WhatsApp
- ✅ **Phone number configured** for WhatsApp Business API
- ✅ **Templates created** and approved for notifications
- Integration via Twilio REST API

### OpenAI
- ✅ **API key available** for LLM capabilities
- Used by Itinerary and Concierge agents

### Supabase Database Schema

#### `trips` table (existing)
```sql
- id (UUID, primary key)
- client_name (text)
- whatsapp (text) -- phone number in international format
- flight_number (text)
- origin_iata (bpchar) -- 3-letter airport code
- destination_iata (bpchar) -- 3-letter airport code
- departure_date (timestamptz) -- departure time with timezone
- status (text) -- flight status from AeroAPI
- metadata (jsonb) -- flexible data storage
- inserted_at (timestamptz) -- record creation time
- next_check_at (timestamptz) -- next polling time for flight status
- client_description (text) -- additional client context
```

#### `notifications_log` table (to be created)
```sql
- id (UUID, primary key)
- trip_id (UUID, foreign key → trips.id)
- notification_type (text) -- "24h_reminder" | "status_change" | "landing"
- template_name (text) -- Twilio template identifier
- delivery_status (text) -- "SENT" | "FAILED" | "PENDING"
- sent_at (timestamptz)
- error_message (text, nullable)
```

## API Contracts

### Agent Interface
All agents must implement:
```python
async def run(trigger_type: str, **kwargs) -> Result[dict]
```

### Error Handling
- Use Pydantic `Result` models for typed responses
- Exponential backoff for external API retries (max 3 attempts)
- Log all errors with structured logging

### External API Guidelines
- **AeroAPI**: 10s timeout, rate limit awareness
- **Twilio**: Use approved templates only, handle delivery status
- **OpenAI**: Context management, token limit awareness

## Logging Format
```python
import structlog
logger = structlog.get_logger()

logger.info("notification_sent", 
    agent="notifications", 
    trip_id=trip_id,
    notification_type="24h_reminder",
    phone=phone_number,
    status="success"
)
```

## Agent Context Pattern (TC-004)

Para optimizar la performance y robustez, todos los agentes deben cargar el contexto de viaje usando un método centralizado y validado:

- Modelo: `TripContext` (Pydantic)
- Método: `get_complete_trip_context(trip_id)` en `SupabaseDBClient`
- Retorna: trip, itinerary, documents, recent_messages

**Ejemplo de uso en agente:**

```python
context_obj = await self.db_client.get_complete_trip_context(trip.id)
context = context_obj.model_dump()
```

**Ventajas:**
- Validación de estructura y tipos
- Performance (queries en paralelo)
- Facilidad de testing y refactor
- Escalabilidad y mantenibilidad

**Recomendación:**
Replicar este patrón en todos los agentes (ItineraryAgent, NotificationsAgent) para unificar la carga de contexto y evitar bugs por cambios futuros.

_To be expanded as modules are added._

# Technical Documentation - Bauhaus Travel

## Context Loading Optimization (TC-004)

### Unified Context Method

Para evitar múltiples queries en cada agent, implementamos un método centralizado que carga todo el contexto de un trip en paralelo y lo valida:

```python
async def get_complete_trip_context(self, trip_id: UUID) -> TripContext:
    """
    Carga todo el contexto relevante de un viaje en paralelo y lo valida con TripContext.
    Retorna: TripContext
    """
    trip_task = self.get_trip_by_id(trip_id)
    itinerary_task = self.get_latest_itinerary(trip_id)
    documents_task = self.get_documents_by_trip(trip_id)
    messages_task = self.get_recent_conversations(trip_id, limit=10)

    trip_result, itinerary_result, documents, messages = await asyncio.gather(
        trip_task, itinerary_task, documents_task, messages_task
    )

    trip = trip_result.data if trip_result and trip_result.success else None
    itinerary = itinerary_result.data.get("parsed_itinerary") if itinerary_result and itinerary_result.success and itinerary_result.data else None
    documents = documents if documents else []
    messages = messages if messages else []

    context = TripContext(
        trip=trip or {},
        itinerary=itinerary,
        documents=documents,
        recent_messages=messages
    )
    return context
```

### TripContext Model

```python
class TripContext(BaseModel):
    """Contexto completo de un viaje para uso en agentes."""
    trip: Dict[str, Any]
    itinerary: Optional[Dict[str, Any]] = None
    documents: List[Dict[str, Any]] = []
    recent_messages: List[Dict[str, Any]] = []

    class Config:
        arbitrary_types_allowed = True
```

### Uso en Agentes

```python
# En ConciergeAgent, ItineraryAgent, etc.
async def _load_conversation_context(self, trip: Trip) -> Dict[str, Any]:
    """
    Load all relevant context for AI response generation using the optimized, unified method.
    """
    # Usar el método centralizado y validado
    context_obj = await self.db_client.get_complete_trip_context(trip.id)
    return context_obj.model_dump()
```

**Beneficios:**
- ✅ **Reduce queries** de 4+ individuales a 1 paralela
- ✅ **Validación automática** de datos con Pydantic
- ✅ **Consistencia** entre agentes
- ✅ **Reutilizable** para futuros agentes

Replicar este patrón en otros agentes cuando optimicemos en TC-004.

---

## WhatsApp Integration Patterns (TC-003)

### Phone Number Normalization

**Problem:** Twilio sends WhatsApp numbers as `whatsapp:+5491140383422` but we store them as `+5491140383422` in the database.

**Solution:** Always normalize phone numbers when receiving from Twilio:

```python
def normalize_phone(phone: str) -> str:
    """Normalize phone number by removing whatsapp: prefix if present."""
    return phone.replace("whatsapp:", "") if phone.startswith("whatsapp:") else phone

# Usage in webhook
whatsapp_number = normalize_phone(From)  # From = "whatsapp:+5491140383422"
# Result: whatsapp_number = "+5491140383422"
```

### Trip Identification Pattern

**Business Rule:** Multiple trips can exist for the same WhatsApp number. Always use the most recent trip within 90 days.

```python
async def get_latest_trip_by_whatsapp(self, whatsapp: str, within_days: int = 90) -> Optional[Trip]:
    """
    Get the most recent trip for a WhatsApp number (for user identification).
    
    Args:
        whatsapp: WhatsApp phone number (normalized)
        within_days: Only consider trips within this many days
        
    Returns:
        Trip object if found, None otherwise
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=within_days)
    
    params = {
        "whatsapp": f"eq.{whatsapp}",
        "departure_date": f"gte.{cutoff_date.isoformat()}",
        "select": "*",
        "order": "departure_date.desc",
        "limit": "1"
    }
    
    response = await self._client.get(f"{self.rest_url}/trips", params=params)
    # ... handle response
```

### Conversation Storage Pattern

**Design:** Store both user and bot messages for complete conversation history:

```python
# User message
user_conv_result = await self.db_client.create_conversation(
    trip_id=trip.id,
    sender="user",
    message=message_body,
    intent=intent
)

# Bot response  
bot_conv_result = await self.db_client.create_conversation(
    trip_id=trip.id,
    sender="bot",
    message=response_text,
    intent=f"response_to_{intent}" if intent else None
)
```

### Error Handling Pattern

**Fallback Strategy:** Always provide user-friendly messages even when systems fail:

```python
async def _send_error_fallback_message(self, whatsapp_number: str):
    """Send generic error message when processing fails."""
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
        logger.error("error_fallback_send_failed", to_number=whatsapp_number, error=str(e))
```

---

## Debugging and Testing Patterns

### Systematic Debugging Process (Learned from TC-003)

When debugging complex agent flows:

1. **Start from the endpoint** and work inward
2. **Add logging at each major step** to track execution
3. **Use print statements** temporarily for immediate feedback
4. **Verify data assumptions** - don't assume data exists where expected
5. **Check for silent failures** - errors might not always throw exceptions

### Testing Multiple Data Sources

**Issue:** Same WhatsApp number can have multiple trips, leading to confusion in testing.

**Solution:** Always verify which trip_id is actually being used:

```python
# In tests and debugging
print(f"Expected trip_id: {expected_trip_id}")
print(f"Actual trip_id found: {actual_trip.id}")

# Use the actual trip_id for verification queries
SELECT * FROM conversations WHERE trip_id = '{actual_trip.id}' ORDER BY created_at DESC;
```

### Background Task Testing

**Issue:** FastAPI background tasks don't execute during synchronous testing.

**Temporary Solution:** Process synchronously during testing:

```python
# For testing (temporary)
await process_inbound_message(...)

# For production (revert after testing)
background_tasks.add_task(process_inbound_message, ...)
```

---

## Production Deployment Patterns

### Environment Variable Handling

**Issue:** Missing environment variables can cause silent failures.

**Solution:** Provide fallbacks and clear error messages:

```python
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    if os.getenv("ENVIRONMENT") == "development":
        openai_api_key = "sk-test-key-for-development"
        logger.warning("using_fallback_openai_key")
    else:
        raise ValueError("Missing OPENAI_API_KEY in environment variables")
```

### Logging Strategy

**Pattern:** Use structured logging with consistent fields:

```python
logger.info("conversation_saved", 
    trip_id=trip.id, 
    sender=sender, 
    success=result.success, 
    error=result.error if not result.success else None
)
```

**Benefits:**
- Easy to query and filter
- Consistent format across agents
- Machine-readable for monitoring

---
