# Current Sprint Tasks

## TC-001: Implement Notifications Agent
Status: Not Started
Priority: High

### Requirements
- Send flight status notifications (AeroAPI)
- Send weather reminders (OpenWeather) before departure
- Schedule reminders via APScheduler or Supabase cron

### Acceptance Criteria
1. User receives delay/gate change alerts
2. Weather reminder is sent 6 h before departure
3. All messages delivered through Twilio

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
