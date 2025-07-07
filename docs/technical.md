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

**Last Updated:** 2025-01-16  
**Architecture Version:** 2.0 - Async Production-Ready

---

## 🏗️ **SYSTEM ARCHITECTURE OVERVIEW**

### **Core Design Principles**
- **Async-First**: All I/O operations are non-blocking
- **Resilience Patterns**: Retry logic, idempotency, circuit breakers
- **Multi-Tenant Ready**: Configurable per-agency settings
- **Observability**: Structured logging, metrics, error tracking
- **Scalability**: Horizontal scaling with stateless design

### **Technology Stack**
- **Runtime**: Python 3.11+ with asyncio
- **Web Framework**: FastAPI (async)
- **Database**: Supabase (PostgreSQL + vector store)
- **External APIs**: Twilio (async httpx), AeroAPI, OpenAI
- **Background Jobs**: APScheduler
- **Deployment**: Railway with auto-scaling

---

## 🤖 **AGENT ARCHITECTURE**

### **NotificationsAgent** - Production-Ready Async Implementation

**Purpose**: Handle all WhatsApp notifications with high reliability and performance

**Key Components**:
```python
class NotificationsAgent:
    def __init__(self):
        self.async_twilio_client = AsyncTwilioClient()  # Non-blocking
        self.retry_service = NotificationRetryService()  # Exponential backoff
        self.db_client = SupabaseDBClient()  # Enhanced with new tables
        self.aeroapi_client = AeroAPIClient()  # Flight data
```

**Performance Characteristics**:
- **Concurrency**: 100+ concurrent notifications
- **Latency**: p95 < 500ms for template messages
- **Reliability**: 95%+ delivery success with retry
- **Idempotency**: 0 duplicate notifications guaranteed

### **Async Twilio Integration**

**File**: `app/services/async_twilio_client.py`

```python
class AsyncTwilioClient:
    async def send_template_message(self, to: str, content_sid: str, 
                                   content_variables: Dict[str, str]) -> TwilioResponse:
        # Uses httpx.AsyncClient with configurable timeouts
        # Supports template messages, text messages, and media
        
    async def send_text_message(self, to: str, body: str) -> TwilioResponse:
        # Free-form text messages for ConciergeAgent
        
    async def send_media_message(self, to: str, media_url: str) -> TwilioResponse:
        # Attachment support for documents/images
```

**Benefits**:
- Non-blocking I/O operations
- Configurable timeouts (30s message, 60s media)
- Proper error handling with structured responses
- Connection pooling and reuse

### **Retry Service with Exponential Backoff**

**File**: `app/services/notification_retry_service.py`

```python
class NotificationRetryService:
    async def send_with_retry(self, send_func: Callable, 
                             max_attempts: int = 3, 
                             context: Dict[str, Any] = None) -> DatabaseResult:
        # Implements exponential backoff: 5s → 10s → 20s → 40s
        # Adds jitter to prevent thundering herd
        # Max delay cap at 5 minutes
        # Comprehensive logging for observability
```

**Configuration**:
- **Base Delay**: 5 seconds
- **Max Attempts**: 3 (configurable per agency)
- **Jitter**: ±20% random variation
- **Max Delay**: 5 minutes cap
- **Backoff Factor**: 2x per attempt

---

## 🗄️ **DATABASE SCHEMA - ENHANCED**

### **New Tables Added**

#### **flight_status_history** - Precise Flight Tracking
```sql
CREATE TABLE flight_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id),
    flight_number VARCHAR(10) NOT NULL,
    flight_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL,
    gate_origin VARCHAR(10),
    gate_destination VARCHAR(10),
    estimated_out TIMESTAMPTZ,
    actual_out TIMESTAMPTZ,
    estimated_in TIMESTAMPTZ,
    actual_in TIMESTAMPTZ,
    raw_data JSONB,
    source VARCHAR(20) DEFAULT 'aeroapi',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Optimized indexes for frequent queries
CREATE INDEX idx_flight_status_history_trip_id ON flight_status_history(trip_id);
CREATE INDEX idx_flight_status_history_flight_date ON flight_status_history(flight_number, flight_date);
```

**Purpose**: 
- Store complete flight status history for precise change detection
- Enable accurate diff calculations between states
- Support audit trails and analytics

#### **agencies_settings** - Multi-Tenant Configuration
```sql
CREATE TABLE agencies_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES agencies(id),
    setting_key VARCHAR(100) NOT NULL,
    setting_value JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agency_id, setting_key)
);
```

**Configurable Settings**:
- `quiet_hours`: Local time ranges for no notifications
- `retry_limits`: Custom retry attempts per agency
- `rate_limiting`: Messages per minute limits
- `feature_flags`: Enable/disable specific features
- `notification_preferences`: Template customizations

#### **notifications_log** - Enhanced with Idempotency
```sql
-- Added column to existing table
ALTER TABLE notifications_log 
ADD COLUMN idempotency_hash VARCHAR(16);

-- Unique constraint to prevent duplicates
CREATE UNIQUE INDEX idx_notifications_log_idempotency 
ON notifications_log(trip_id, notification_type, idempotency_hash) 
WHERE delivery_status = 'SENT';
```

**Idempotency Implementation**:
```python
# Generate consistent hash for same notification
idempotency_data = {
    "trip_id": str(trip.id),
    "notification_type": notification_type_db,
    "extra_data": extra_data or {}
}
idempotency_hash = hashlib.sha256(
    json.dumps(idempotency_data, sort_keys=True).encode()
).hexdigest()[:16]
```

---

## 🔄 **NOTIFICATION FLOW - OPTIMIZED**

### **1. Template-Based Notifications**
```python
async def send_notification(self, trip: Trip, notification_type: NotificationType, 
                           extra_data: Optional[Dict[str, Any]] = None) -> DatabaseResult:
    # 1. Generate idempotency hash
    # 2. Check for existing notification
    # 3. Format message using templates
    # 4. Send with retry logic
    # 5. Log result with hash
```

### **2. Flight Status Monitoring**
```python
async def poll_flight_changes(self) -> DatabaseResult:
    # 1. Get trips needing status check
    # 2. Fetch current status from AeroAPI
    # 3. Compare with flight_status_history
    # 4. Detect changes (status, gate, time)
    # 5. Send notifications for changes
    # 6. Update history and next_check_at
```

### **3. Landing Detection**
```python
async def poll_landed_flights(self) -> DatabaseResult:
    # 1. Get trips that should have landed
    # 2. Check AeroAPI for LANDED/ARRIVED status
    # 3. Send welcome message if not already sent
    # 4. Respect quiet hours at destination
```

---

## 🧪 **TESTING STRATEGY**

### **Unit Tests** - Critical Functions Only
**File**: `tests/test_notifications_agent_core.py`

**Test Coverage**:
- ✅ `calculate_next_check_time` - Polling optimization rules
- ✅ `format_message` - Template formatting with various inputs
- ✅ Idempotency hash generation and consistency
- ✅ Integration workflows with mocked external services

**Testing Philosophy**:
- Focus on business logic, not infrastructure
- Mock external APIs (Twilio, AeroAPI) intelligently
- Test edge cases and error conditions
- Avoid over-testing simple CRUD operations

### **Integration Testing**
```python
# Simple integration test for critical paths
async def test_notification_end_to_end():
    # 1. Create test trip
    # 2. Trigger notification
    # 3. Verify delivery
    # 4. Check idempotency
    # 5. Cleanup
```

---

## 📊 **MONITORING & OBSERVABILITY**

### **Structured Logging**
```python
logger.info("notification_sent_successfully", 
    trip_id=str(trip.id),
    message_sid=send_result.data.get("message_sid"),
    notification_type=notification_type,
    latency_ms=int((time.time() - start_time) * 1000)
)
```

### **Key Metrics to Track**
- **Performance**: p95 notification latency
- **Reliability**: Retry success rate, final delivery rate
- **Quality**: Duplicate prevention effectiveness
- **Business**: Notifications per trip, user engagement

### **Error Alerting**
- Failed notifications after all retries
- AeroAPI rate limiting or outages
- Database connection issues
- Template formatting errors

---

## 🚀 **DEPLOYMENT CONFIGURATION**

### **Environment Variables**
```bash
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_MESSAGING_SERVICE_SID=MGxxxxx

# AeroAPI Configuration
AEROAPI_KEY=xxxxx
AEROAPI_BASE_URL=https://aeroapi.flightaware.com/aeroapi

# Database
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=xxxxx

# OpenAI
OPENAI_API_KEY=sk-xxxxx
```

### **Dependencies**
```txt
# Core async dependencies
httpx==0.25.2          # Async HTTP client for Twilio
fastapi==0.104.1       # Async web framework
uvicorn==0.24.0        # ASGI server
asyncio                # Built-in async support

# Database & External APIs
supabase==2.0.0        # Database client
openai==1.3.0          # AI completions
```

### **Railway Deployment**
```toml
# railway.toml
[build]
builder = "NIXPACKS"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
```

---

## 🔐 **SECURITY CONSIDERATIONS**

### **API Security**
- All external API calls use HTTPS
- API keys stored in environment variables
- Rate limiting on all endpoints
- Input validation and sanitization

### **Data Protection**
- PII data not logged in structured logs
- Sensitive fields encrypted at rest
- Audit trails for all notification sends
- GDPR-compliant data retention policies

### **Multi-Tenant Isolation**
- Agency data strictly isolated
- Per-agency configuration validation
- No cross-agency data leakage
- Secure agency ID validation

---

## 🎯 **PERFORMANCE TARGETS**

### **Notification Performance**
- **Latency**: p95 < 500ms for template messages
- **Throughput**: 100+ concurrent notifications
- **Reliability**: 95%+ final delivery success
- **Idempotency**: 0 duplicate notifications

### **Database Performance**
- **Query Time**: p95 < 100ms for trip lookups
- **Connection Pool**: 10-20 connections
- **Index Usage**: All frequent queries indexed
- **Batch Operations**: Minimize N+1 query patterns

### **External API Performance**
- **AeroAPI**: 5-minute cache for status data
- **Twilio**: Connection pooling and reuse
- **OpenAI**: Prompt optimization for cost/speed
- **Circuit Breakers**: Prevent cascade failures

---

## 🔧 **MAINTENANCE PROCEDURES**

### **Database Migrations**
```sql
-- Apply in order for NotificationsAgent optimization
-- 1. flight_status_history table
-- 2. agencies_settings table  
-- 3. notifications_log idempotency column
```

### **Monitoring Checklist**
- [ ] Notification delivery rates
- [ ] Retry success rates
- [ ] Database query performance
- [ ] External API error rates
- [ ] Memory and CPU usage

### **Troubleshooting**
- Check structured logs for error patterns
- Verify external API connectivity
- Monitor database connection pool
- Review retry attempt distributions

---

**Status:** ✅ **PRODUCTION READY - ASYNC ARCHITECTURE DOCUMENTED**

**Next Update:** After deployment metrics and optimization feedback

---
