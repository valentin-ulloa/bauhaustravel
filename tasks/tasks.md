# Current Sprint Tasks

## TC-001: Implement Flight Notifications Agent
Status: In Progress
Priority: High

### Purpose
Provide users with proactive and timely flight updates via WhatsApp:
- Remind users of their upcoming flights.
- Alert users to any critical changes (delay / gate / cancel).
- Welcome users upon landing.

### Scope
This agent:
✅ Sends **push notifications** only (no chat) via **Twilio WhatsApp approved templates**.  
✅ Triggers based on **flight timing** and **AeroAPI status**.  
✅ Reads / writes exclusively to Supabase tables (`flights`, `notifications_log`).  
❌ Does **not** handle hotel info, tips, or conversational replies.

### Triggers and Messages

| Trigger | Message (Twilio template) | Send window |
|---------|---------------------------|-------------|
| 24 h before `departure_time` | Flight confirmation | **Only 09:00 – 20:00** local time. If the nominal send-time falls outside, schedule for 09:00 local. |
| Flight status change (delay / gate / cancel) | Flight update | Dynamic polling (see below) |
| Flight status == **LANDED** | Welcome message | Detected via polling |

### Acceptance Criteria

| ID | Given / When / Then |
|----|---------------------|
| AC-1 | **Given** a flight record, **when** it reaches 24 h before departure, **then** the user receives a WhatsApp confirmation (template) inside the 09-20 h window. |
| AC-2 | **Given** an active flight, **when** AeroAPI reports delay / gate / cancel, **then** the user is notified once per change (template) and `notifications_log` stores `SENT`. |
| AC-3 | **Given** a flight whose status becomes **LANDED**, **then** the user receives a welcome message and log entry. |
| AC-4 | **Given** a delivery failure, **then** the agent retries up to 3× with exponential back-off and logs `FAILED` after the final attempt. |

### Data / Persistence
- **Reads** from `flights` (flight_id, user_phone, departure_time, arrival_city, status, next_poll_at).
- **Writes** to `notifications_log` (flight_id, notification_type, timestamp, delivery_status).

### External Services
- **AeroAPI** – flight status & changes  
- **Twilio WhatsApp** – message delivery (templates)  
- **OpenWeather** (future) – not used in this task

### Technical Notes
- Convert `departure_time` to the **origin airport’s timezone** using `zoneinfo`.
- 24 h reminder: if send-time < 09:00 or ≥ 20:00, schedule for 09:00 same day.
- **Schedulers** (APScheduler or Supabase cron):
  - `schedule_24h_reminders()` runs daily.
  - `poll_flight_changes()` runs every 15 min and filters by `next_poll_at`.
  - `poll_landed_flights()` runs every 15 min (same filter).
- Use `httpx.AsyncClient` (timeout 10 s) for AeroAPI; exponential-back-off retry helper.
- Message creation centralised in `NotificationsAgent.format_message()`.
- All WhatsApp templates and variable mappings defined in `notifications_templates.py`.

### Poll Optimisation
| Time until departure | Next poll interval |
|----------------------|--------------------|
| > 24 h               | +6 h |
| 24 h – 4 h           | +1 h |
| ≤ 4 h                | +15 min |
| **In-flight**        | +30 min (to detect LANDED) |

- Column `next_poll_at` updated after each poll.  
- `poll_flight_changes()` queries: `WHERE next_poll_at <= NOW() AT TIME ZONE 'UTC'`.

---

## TC-002: Implement Itinerary Agent
Status: Not Started
Priority: High

### Requirements
- Generate day-by-day itinerary from destination & dates
- Use OpenAI API
- Store generated plan in Supabase

### Acceptance Criteria
1. Itinerary saved to DB
2. User receives formatted summary via WhatsApp

---

## TC-003: Implement Concierge / Support Agent
Status: Not Started
Priority: High

### Requirements
- Answer FAQs and give local recommendations
- Maintain conversation memory (conversations table)

### Acceptance Criteria
1. Follow-up questions reference prior context
2. Response latency <3 s
