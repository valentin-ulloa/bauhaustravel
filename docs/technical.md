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

_To be expanded as modules are added._
