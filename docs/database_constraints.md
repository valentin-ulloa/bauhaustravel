# Database Constraints Documentation

## Overview
This document lists all database constraints in the Bauhaus Travel system. **Important:** When adding new notification types or statuses, these constraints must be updated in both the database and the code.

## Current Constraints (Updated: 2024-06-05)

### notifications_log Table

#### 1. notification_type_check
```sql
CHECK ((notification_type = ANY (ARRAY[
  'RESERVATION_CONFIRMATION'::text, 
  'REMINDER_24H'::text, 
  'DELAYED'::text, 
  'GATE_CHANGE'::text, 
  'CANCELLED'::text, 
  'BOARDING'::text,
  'ITINERARY_READY'::text
])))
```

**Mapped to:** `NotificationType` enum in `app/agents/notifications_templates.py`
**Used by:** `NotificationsAgent.send_notification()` with `.value.upper()` conversion

#### 2. delivery_status_check
```sql
CHECK ((delivery_status = ANY (ARRAY[
  'SENT'::text, 
  'FAILED'::text, 
  'PENDING'::text
])))
```

**Mapped to:** `NotificationLog.delivery_status` in `app/models/database.py`

#### 3. Primary Key
```sql
PRIMARY KEY (id)
```

#### 4. Foreign Key
```sql
FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
```

## ⚠️ When Adding New Notification Types

1. **Update NotificationType enum** in `app/agents/notifications_templates.py`
2. **Update Pydantic model** in `app/models/database.py` 
3. **Update database constraint** with new UPPERCASE values
4. **Add Twilio template mapping** in `WhatsAppTemplates.TEMPLATES`
5. **Add format method** in `WhatsAppTemplates` class
6. **Update this documentation**

## ⚠️ When Adding New Delivery Statuses

1. **Update database constraint** for `delivery_status_check`
2. **Update Pydantic model** in `app/models/database.py`
3. **Update this documentation**

## Value Conversion Flow

```
NotificationType.RESERVATION_CONFIRMATION  # Enum value
    ↓ .value
"reservation_confirmation"                 # String value  
    ↓ .upper()
"RESERVATION_CONFIRMATION"                 # Database format
```

## Validation

- **Code side:** Pydantic models validate against Literal types
- **Database side:** PostgreSQL CHECK constraints enforce allowed values
- **Both must match** for successful operations

## History

- **2024-06-05:** Fixed constraint mismatch between old `['24h_reminder', 'status_change', 'landing']` and current enum values
- **2024-06-05:** Updated NotificationLog model to match database constraint format 