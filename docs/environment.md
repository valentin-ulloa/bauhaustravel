# Environment Configuration

## Required Environment Variables

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Twilio WhatsApp (✅ Already configured)
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=whatsapp:+1234567890  # Your WhatsApp Business number

# OpenAI (✅ API key available)
OPENAI_API_KEY=your-openai-api-key

# AeroAPI (Flight data)
AERO_API_KEY=your-aero-api-key
AERO_API_BASE_URL=https://aeroapi.flightaware.com/aeroapi

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=development  # development | staging | production
```

## Twilio WhatsApp Templates

### Available Templates (✅ Created and approved)
Based on TC-001 requirements, we need these template types:

1. **Flight Confirmation (24h reminder)**
   - Template name: `flight_confirmation_24h`
   - Variables: flight_number, departure_time, origin, destination

2. **Flight Update (delays/changes)**
   - Template name: `flight_status_update`
   - Variables: flight_number, status_change, new_time, gate_info

3. **Landing Welcome**
   - Template name: `flight_landing_welcome`
   - Variables: destination_city, local_time

### Template Configuration
Templates should be defined in `app/agents/notifications_templates.py` for centralized management.

## Database Setup

### Required Tables
- ✅ `trips` table (already exists)
- ❌ `notifications_log` table (needs creation)
- ❌ `conversations` table (for Concierge agent - future)

### Migration Scripts
Place SQL migration files in `database/migrations/` for version control. 