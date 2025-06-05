-- Migration: Create notifications_log table
-- Purpose: Track WhatsApp notification delivery for flight updates
-- Relates to: TC-001 Notifications Agent

CREATE TABLE notifications_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    notification_type TEXT NOT NULL CHECK (notification_type IN ('24h_reminder', 'status_change', 'landing')),
    template_name TEXT NOT NULL,
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('SENT', 'FAILED', 'PENDING')) DEFAULT 'PENDING',
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT,
    twilio_message_sid TEXT, -- Twilio's unique message identifier
    retry_count INTEGER DEFAULT 0,
    
    -- Metadata for debugging and analytics
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX idx_notifications_log_trip_id ON notifications_log(trip_id);
CREATE INDEX idx_notifications_log_status ON notifications_log(delivery_status);
CREATE INDEX idx_notifications_log_type ON notifications_log(notification_type);
CREATE INDEX idx_notifications_log_sent_at ON notifications_log(sent_at);

-- Update trigger for updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_notifications_log_updated_at 
    BEFORE UPDATE ON notifications_log 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column(); 


