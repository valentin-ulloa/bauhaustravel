# Current Sprint Tasks

## TC-001: Implement Flight Notifications Agent  
Status: In Progress  
Priority: High  

### Purpose  
Provide users with proactive and timely flight updates via WhatsApp:
- Send **reservation confirmation** at trip creation (POST /trips).
- Remind users of upcoming flights (24h).
- Alert users to critical changes (delay / gate / cancel).
- Welcome users upon landing.

### Scope  
This agent:  
✅ Sends **push notifications only** via **Twilio WhatsApp approved templates**.  
✅ Triggered by API (POST /trips), scheduler, or AeroAPI polling.  
✅ Reads / writes to Supabase tables: `trips`, `notifications_log`.  
❌ Does not handle hotel info, tips, or conversational replies.

### Triggers and Templates

| Trigger | Message (Twilio template) | Notes |
|---------|---------------------------|-------|
| **POST /trips** (new trip created) | `confirmacion_reserva` | Triggered immediately via `send_single_notification()` |
| 24 h before `departure_date` | `recordatorio_24h` | Only between 09:00–20:00 local time; if outside, schedule for 09:00 |
| Flight DELAYED | `demorado` | Triggered via AeroAPI polling |
| Gate CHANGE | `cambio_gate` | Triggered via AeroAPI polling |
| CANCELLED | `cancelado` | Triggered via AeroAPI polling |
| BOARDING | `embarcando` | (optional future trigger) |
| LANDED | (To be defined) | Send welcome message upon landing |

### Acceptance Criteria

| ID | Given / When / Then |
|----|---------------------|
| AC-1 | **Given** a new trip is created via `POST /trips`, **then** the user receives `confirmacion_reserva` WhatsApp message. |
| AC-2 | **Given** a flight is 24h from `departure_date`, **then** user receives `recordatorio_24h` in allowed time window. |
| AC-3 | **Given** AeroAPI reports **delay / gate / cancel**, **then** user receives proper update template, once per change. |
| AC-4 | **Given** flight reaches **LANDED**, **then** user receives welcome message. |
| AC-5 | **Given** a delivery fails, **then** agent retries up to 3× with backoff and logs final result. |

### Data / Persistence
- Reads: `trips` (trip_id, whatsapp, departure_date, status, next_check_at)
- Writes: `notifications_log` (trip_id, notification_type, sent_at, delivery_status, etc.)

### External Services
- **AeroAPI** — flight status
- **Twilio WhatsApp** — templates:
    - `confirmacion_reserva` (SID HX01a541412cda42dd91bff6995fdc3f4a)
    - `recordatorio_24h` (SID HXf79f6f380e09de4f1b953f7045c6aa19)
    - `demorado` (SID HXd5b757e51d032582949292a65a5afee1)
    - `cambio_gate` (SID HXd38d96ab6414b96fe214b132253c364e)
    - `cancelado` (SID HX1672fabd1ce98f5b7d06f1306ba3afcc)
    - `embarcando` (SID HX3571933547ed2f3b6e4c6dc64a84f3b7)

### Technical Notes
- On `POST /trips`, agent immediately sends `RESERVATION_CONFIRMATION`.
- `schedule_24h_reminders()` runs daily.
- `poll_flight_changes()` runs every 15 min, filters by `next_check_at`.
- `poll_landed_flights()` runs every 15 min.
- Template variables mapped in `notifications_templates.py`.
- Message sending centralized in `NotificationsAgent.send_notification()`.

### Poll Optimisation

| Time until departure | Next poll interval |
|----------------------|--------------------|
| > 24 h | +6 h |
| 24h–4h | +1 h |
| ≤ 4h | +15 min |
| In-flight | +30 min |

---

## TC-002: Implement Itinerary Agent  
Status: Not Started  
Priority: High  

### Requirements
- Generate day-by-day itinerary from destination & dates.
- Use OpenAI API.
- Store generated plan in Supabase.

### Acceptance Criteria
1. Itinerary saved to DB.
2. User receives formatted summary via WhatsApp.

---

## TC-003: Implement Concierge / Support Agent  
Status: Not Started  
Priority: High  

### Requirements
- Answer FAQs and give local recommendations.
- Maintain conversation memory (`conversations` table).

### Acceptance Criteria
1. Follow-up questions reference prior context.
2. Response latency <3 s.

