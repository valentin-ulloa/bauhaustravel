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

## TC-002 — Itinerary Agent  
**Status:** Not Started  **Priority:** High  

---

### 🎯 Objective  

Implement the first version of Itinerary Agent to:

✅ Generate a day-by-day itinerary based on trip + profile (+ optional agency places).  
✅ Save it versioned in Supabase.  
✅ Notify user via WhatsApp that itinerary is ready (via template).  
✅ Allow triggering manually via API (to test with agencies and early B2C users).  

---

### 🛠️ Scope (MVP)

| # | Task | Key Details |
| - | ---- | ----------- |
| 1️⃣ | **Input Handling** | Load `trip`, `flights`, `profile`. If `agency_id` present → load `agency_places`. |
| 2️⃣ | **Itinerary Generation** | Build `raw_prompt` with full context. Call OpenAI (gpt-4o mini) or Perplexity. Save `raw_response`. |
| 3️⃣ | **Validation** | For each place: if match in `agency_places` → `source = "agency"`; else → `source = "low_validation"`. |
| 4️⃣ | **Parsed Itinerary** | Build parsed_itinerary JSON:  
```json5
{
  "days": [
    {
      "date": "YYYY-MM-DD",
      "items": [
        {
          "title": "…",
          "type": "…",
          "address": "…",
          "city": "…",
          "country": "…",
          "lat": …,
          "lng": …,
          "opening_hours": "…",
          "rating": null,
          "source": "agency" | "low_validation",
          "safety_warnings": [],
          "tags": []
        }
      ]
    }
  ]
}
``` |
| 5️⃣ | **Persistence** | Save parsed_itinerary to `itineraries` table (see migrations). First version: `version=1`, `status='draft'`. |
| 6️⃣ | **Notify User (WhatsApp)** | Send WhatsApp template `itinerary_ready` via NotificationsAgent:<br>Example body:<br>_“¡Tu itinerario está listo! Responde 'Sí' si querés verlo completo.”_ |
| 7️⃣ | **API Endpoint** | Implement `POST /itinerary?trip_id=uuid` to trigger itinerary generation manually. |

---

### ✅ Acceptance Criteria

1. `parsed_itinerary` saved in `itineraries` with `trip_id`, `version`, `status`.  
2. WhatsApp template `itinerary_ready` is sent after generation.  
3. If `agency_places` matches ≥1 item → source = "agency".  
4. Items without match → source = "low_validation".  
5. `POST /itinerary` triggers generation and returns `201` with itinerary ID.  
6. Unit tests cover: prompt build, agency validation, DB insert, WhatsApp send.

---

### 📂 Database Migrations

```sql
-- 002_create_itineraries.sql
CREATE TABLE itineraries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id uuid REFERENCES trips(id) ON DELETE CASCADE,
  version int NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'draft',  -- draft | approved | regenerating
  generated_at timestamptz NOT NULL DEFAULT now(),
  raw_prompt text,
  raw_response text,
  parsed_itinerary jsonb NOT NULL
);
CREATE INDEX ON itineraries (trip_id);

-- 003_create_agency_places.sql
CREATE TABLE agency_places (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid,
  name text,
  address text,
  city text,
  country text,  -- ISO-2 code
  lat double precision,
  lng double precision,
  type text,
  rating numeric,
  opening_hours text,
  tags text[],
  UNIQUE (agency_id, name, address)
);
CREATE INDEX ON agency_places (agency_id, city);

---


## TC-003 — Implement Concierge / Support Agent

**Status:** Not Started  **Priority:** High

---

### 🎯 Purpose

Provide travelers with a **conversational assistant via WhatsApp** to:

✅ Answer questions about their **itinerary**.
✅ Provide **local recommendations** (restaurants, activities, tips).
✅ Assist with **flight issues** (delays, cancellations, changes).
✅ Send **boarding pass** and travel **documents** (PDFs).
✅ Share **reservations** (hotels, car rentals, transfers, insurance).
✅ Maintain **conversation memory** for coherent follow-ups.

---

### 🛠️ Scope (MVP)

| #   | Task                             | Key Details                                                                                                                                                                                                                                                        |
| --- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1️⃣ | **Inbound Webhook**              | Implement `/webhooks/twilio` endpoint to receive incoming messages.<br>Extract `from_phone`, `body`, `media`, `timestamp`.                                                                                                                                         |
| 2️⃣ | **Conversation Memory**          | Create `conversations` table.<br>Log each turn (`user`/`bot`) with timestamp and content.                                                                                                                                                                          |
| 3️⃣ | **ConciergeAgent.run()**         | Identify `trip_id` via `trips.whatsapp`.<br>Load: itinerary, flights, documents, conversation history.<br>Generate response via GPT-4o mini.<br>Return `{ text, attachments? }`.                                                                                   |
| 4️⃣ | **Document Storage & Retrieval** | Create `documents` table to store links to files (boarding pass, hotel, car rental, transfers, insurance).<br>Enable ConciergeAgent to retrieve and send documents when requested.                                                                                 |
| 5️⃣ | **Response Flow**                | Use `NotificationsAgent.send_free_text()` to send responses.<br>Attach files or links when applicable.                                                                                                                                                             |
| 6️⃣ | **Basic Intents**                | Initial supported intents:<br>• "Itinerario" → send parsed itinerary.<br>• "Boarding pass" → send boarding PDF.<br>• "Vuelo" → send flight status.<br>• "Hotel", "Auto", "Seguro", etc. → send corresponding documents.<br>• Free-form questions → handled by LLM. |
| 7️⃣ | **Error Handling**               | If LLM fails or times out, send fallback message and log error.                                                                                                                                                                                                    |

---

### ✅ Acceptance Criteria

| ID   | Given / When / Then                                                                                                                                   |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC-1 | **Given** a message is received on WhatsApp, **then** it is stored in `conversations`.                                                                |
| AC-2 | **Given** a user asks for "Itinerario", **then** parsed itinerary is sent in ≤ 3 seconds.                                                             |
| AC-3 | **Given** a user asks for "Boarding pass", **then** the correct PDF is sent.                                                                          |
| AC-4 | **Given** a user asks for any stored reservation (hotel, car rental, transfer, insurance), **then** the corresponding document is retrieved and sent. |
| AC-5 | **Given** a user asks a follow-up question ("And what about day 2?"), **then** the reply uses conversation context.                                   |
| AC-6 | **Given** an internal error occurs, **then** a fallback message is sent and the error is logged.                                                      |

---

### 📂 Data / Persistence

* **Reads**:

  * `trips` (trip\_id, whatsapp, client\_name)
  * `itineraries.parsed_itinerary`
  * `flights` (status, gate, delay)
  * `documents` (file\_url, type)
  * `conversations` (last N messages)

* **Writes**:

  * `conversations` (trip\_id, sender, message, timestamp, intent)
  * `errors_log` (if applicable)

---

### 🔌 External Services

* **Twilio WhatsApp** — inbound & outbound messages.
* **OpenAI GPT-4o mini** — response generation with tools.
* **Supabase Storage** — document storage (PDFs, links).

---

### ⚙️ Technical Notes

* `ConciergeAgent.run(trip_id, incoming_message)` returns `{ text, attachments? }`.
* Document requests resolved via `documents` table:

  ```sql
  SELECT file_url FROM documents WHERE trip_id = X AND type = Y ORDER BY uploaded_at DESC LIMIT 1;
  ```
* GPT-4o mini uses a structured prompt with available tools:

  * `get_itinerary()`
  * `get_flight_status()`
  * `get_document(type)`
* Fallback if response > 2 seconds or LLM fails.
* Memory limited to last 10 conversation turns.

---

### 📂 Database Migrations

#### Conversations

```sql
CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id uuid REFERENCES trips(id) ON DELETE CASCADE,
  sender text NOT NULL CHECK (sender IN ('user','bot')),
  message text NOT NULL,
  intent text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON conversations (trip_id, created_at DESC);
```

#### Documents

```sql
CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id uuid REFERENCES trips(id) ON DELETE CASCADE,
  type text NOT NULL CHECK (type IN (
    'boarding_pass', 'hotel_reservation', 'car_rental', 'transfer', 'insurance', 'tour_reservation'
  )),
  file_url text NOT NULL,
  file_name text,
  uploaded_at timestamptz DEFAULT now()
);
CREATE INDEX ON documents (trip_id);
```

---

### Roadmap (Post-MVP)

| Phase | Feature                                                                               |
| ----- | ------------------------------------------------------------------------------------- |
| F-1   | Handoff to human agent if low confidence (<0.3).                                      |
| F-2   | Proactive suggestions (e.g. "Your flight is delayed, would you like hotel options?"). |
| F-3   | Contextual recommendations using embeddings.                                          |
| F-4   | Upsell flows (insurance, upgrades).                                                   |

---

