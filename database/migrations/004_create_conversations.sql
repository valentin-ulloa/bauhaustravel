-- Migration: Create conversations table for TC-003 ConciergeAgent
-- Purpose: Store user/bot conversation history for context and memory

CREATE TABLE conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id uuid REFERENCES trips(id) ON DELETE CASCADE,
  sender text NOT NULL CHECK (sender IN ('user','bot')),
  message text NOT NULL,
  intent text,  -- Optional: detected intent for analytics
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes for efficient queries
CREATE INDEX ON conversations (trip_id, created_at DESC);
CREATE INDEX ON conversations (sender);

-- Grant permissions for service_role
GRANT INSERT, SELECT, UPDATE, DELETE ON TABLE conversations TO service_role; 