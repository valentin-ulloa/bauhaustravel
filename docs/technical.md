# Technical Guidelines

## 🕐 **TIMEZONE POLICY (CRITICAL)**

**SYSTEM-WIDE RULE** - Eliminates timezone confusion:

1. **INPUT**: All departure times are LOCAL TIME of origin airport
2. **STORAGE**: Automatic conversion to UTC for database storage  
3. **DISPLAY**: Automatic conversion back to local time for user display

**Implementation:**
- `TripCreate` model auto-converts local → UTC via validator
- `format_departure_time_*()` functions convert UTC → local for display
- **NO MANUAL TIMEZONE CONVERSIONS** in code

**Example:**
```python
# ✅ CORRECT - Let model handle conversion
trip = TripCreate(
    departure_date=datetime(2025, 7, 8, 22, 5),  # LHR local time
    origin_iata="LHR"
)
# → Auto-stored as UTC: 2025-07-08T21:05:00+00:00

# ❌ WRONG - Don't do manual conversions
utc_time = local_time.astimezone(timezone.utc)  # NEVER DO THIS
```

---

## 🏗️ **ARCHITECTURE**

### **Tech Stack**
- **Runtime**: Python 3.11+ with asyncio
- **Web**: FastAPI (async)
- **Database**: Supabase (PostgreSQL + vector store)
- **APIs**: Twilio (httpx async), AeroAPI, OpenAI
- **Jobs**: APScheduler
- **Deploy**: Railway

### **Core Components**
```python
# All agents implement:
async def run(trigger_type: str, **kwargs) -> Result[dict]

# Async clients for external services:
AsyncTwilioClient()  # Non-blocking WhatsApp
AeroAPIClient()      # Flight data with caching
OpenAI()            # AI completions
```

---

## 🗄️ **DATABASE SCHEMA**

### **Core Tables**
```sql
-- Main trip data
trips (id, client_name, whatsapp, flight_number, departure_date, agency_id, ...)

-- Multi-tenant agencies
agencies (id, name, email, branding, pricing_tier, ...)
agencies_settings (agency_id, setting_key, setting_value, ...)

-- Notifications with idempotency
notifications_log (id, trip_id, notification_type, idempotency_hash, ...)

-- Flight tracking
flight_status_history (id, trip_id, status, gate_*, estimated_*, actual_*, ...)

-- AI features
itineraries (id, trip_id, parsed_itinerary, ...)
conversations (id, trip_id, sender, message, intent, ...)
documents (id, trip_id, type, file_url, ...)
```

### **Key Constraints**
- All foreign keys with CASCADE delete
- Unique constraints on idempotency fields
- Multi-tenant isolation via agency_id

---

## 🔄 **NOTIFICATION FLOW**

### **Template System**
```python
# Twilio approved templates with SIDs
NotificationType.RESERVATION_CONFIRMATION → "HXb777321..."
NotificationType.REMINDER_24H → "HXf79f6f380..."
NotificationType.DELAYED → "HXd5b757e51..."
NotificationType.GATE_CHANGE → "HXd38d96ab6..."
```

### **Intelligent Polling**
```python
# Adaptive intervals by flight phase
> 24h: every 6 hours      # Low cost
24h-4h: every 1 hour      # Moderate
< 4h: every 15 minutes    # High precision  
In-flight: every 30 min   # Landing detection
```

### **Retry Logic**
```python
# Exponential backoff: 5s → 10s → 20s → 40s
# Max 3 attempts with jitter
# 95%+ final delivery success
```

---

## 📊 **PERFORMANCE TARGETS**

| Component | Target | Status |
|-----------|--------|--------|
| Notification latency | p95 < 500ms | ✅ |
| Flight polling cost | 80% reduction | ✅ |
| Landing detection | 98%+ accuracy | ✅ |
| Duplicate prevention | 0 duplicates | ✅ |
| System uptime | 99.9% | ✅ |

---

## 🔧 **DEVELOPMENT**

### **Error Handling**
```python
# Structured logging
logger.info("notification_sent", 
    trip_id=trip_id, 
    notification_type=type,
    status="success"
)

# Pydantic Result models
return DatabaseResult(success=True, data=result)
```

### **Testing Strategy**
- Unit tests for business logic only
- Mock external APIs intelligently  
- Integration tests for critical workflows
- No over-testing of simple CRUD

### **Environment Variables**
```bash
# External APIs
TWILIO_ACCOUNT_SID=ACxxxxx
AEROAPI_KEY=xxxxx
OPENAI_API_KEY=sk-xxxxx

# Database
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=xxxxx
```

---

## 🚀 **DEPLOYMENT**

### **Railway Configuration**
```toml
# railway.toml
[deploy]
healthcheckPath = "/health"
restartPolicyType = "ON_FAILURE"
```

### **Dependencies**
```txt
httpx==0.25.2          # Async HTTP for Twilio
fastapi==0.104.1       # Web framework
supabase==2.0.0        # Database
openai==1.3.0          # AI
apscheduler==3.10.0    # Background jobs
```

---

## 🛡️ **SECURITY & OPERATIONS**

### **Multi-Tenant Isolation**
- Agency data strictly separated
- No cross-agency data access
- Configurable settings per agency

### **Monitoring**
- Structured JSON logging
- Health check endpoints
- Error alerting for failed notifications
- Performance metrics tracking

### **Maintenance**
- Database migrations in sequence
- Connection pooling optimized
- External API circuit breakers
