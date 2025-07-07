-- Migration: Add idempotency hash to notifications_log
-- Purpose: Prevent duplicate notifications during retries or parallel executions
-- Date: 2025-01-16

-- Add idempotency_hash column to notifications_log
ALTER TABLE public.notifications_log 
ADD COLUMN idempotency_hash text;

-- Create unique constraint to prevent duplicates
-- This will prevent the same notification from being sent multiple times
CREATE UNIQUE INDEX idx_notifications_log_idempotency 
ON public.notifications_log(trip_id, notification_type, idempotency_hash)
WHERE idempotency_hash IS NOT NULL;

-- Add index for performance on hash lookups
CREATE INDEX idx_notifications_log_hash 
ON public.notifications_log(idempotency_hash)
WHERE idempotency_hash IS NOT NULL;

-- Create function to generate idempotency hash
CREATE OR REPLACE FUNCTION generate_notification_idempotency_hash(
    p_trip_id uuid,
    p_notification_type text,
    p_extra_data jsonb DEFAULT NULL
)
RETURNS text AS $$
DECLARE
    hash_input text;
    hash_result text;
BEGIN
    -- Create hash input from trip_id, notification_type, and extra_data
    hash_input := p_trip_id::text || '|' || p_notification_type;
    
    -- Include extra_data if provided (for context-specific notifications)
    IF p_extra_data IS NOT NULL THEN
        hash_input := hash_input || '|' || p_extra_data::text;
    END IF;
    
    -- Generate SHA256 hash and take first 16 characters
    hash_result := encode(digest(hash_input, 'sha256'), 'hex');
    
    RETURN substring(hash_result, 1, 16);
END;
$$ LANGUAGE plpgsql;

-- Create function to check if notification already exists
CREATE OR REPLACE FUNCTION notification_already_sent(
    p_trip_id uuid,
    p_notification_type text,
    p_idempotency_hash text
)
RETURNS boolean AS $$
DECLARE
    existing_count integer;
BEGIN
    SELECT COUNT(*)
    INTO existing_count
    FROM public.notifications_log
    WHERE trip_id = p_trip_id
      AND notification_type = p_notification_type
      AND idempotency_hash = p_idempotency_hash
      AND delivery_status = 'SENT';
    
    RETURN existing_count > 0;
END;
$$ LANGUAGE plpgsql;

-- Update existing notifications_log entries with NULL hash
-- This allows the new constraint to work without breaking existing data
UPDATE public.notifications_log 
SET idempotency_hash = generate_notification_idempotency_hash(
    trip_id::uuid, 
    notification_type, 
    NULL
)
WHERE idempotency_hash IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN public.notifications_log.idempotency_hash IS 'Hash to prevent duplicate notifications during retries';
COMMENT ON FUNCTION generate_notification_idempotency_hash(uuid, text, jsonb) IS 'Generate idempotency hash for notification deduplication';
COMMENT ON FUNCTION notification_already_sent(uuid, text, text) IS 'Check if notification with hash already sent successfully';

-- Grant permissions (adjust as needed for your setup)
-- GRANT EXECUTE ON FUNCTION generate_notification_idempotency_hash(uuid, text, jsonb) TO your_app_user;
-- GRANT EXECUTE ON FUNCTION notification_already_sent(uuid, text, text) TO your_app_user; 