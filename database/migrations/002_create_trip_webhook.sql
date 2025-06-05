-- Migration: Create webhook trigger for trip confirmations
-- Purpose: Automatically send booking confirmation when a trip is inserted
-- Relates to: TC-001 Booking Confirmation

-- Step 1: Enable the HTTP extension (if not already enabled)
-- You may need to enable this in Supabase Dashboard > Database > Extensions
-- CREATE EXTENSION IF NOT EXISTS http;

-- Step 2: Create function to call webhook
CREATE OR REPLACE FUNCTION notify_trip_confirmation()
RETURNS TRIGGER AS $$
BEGIN
    -- Call webhook to send booking confirmation
    -- Replace 'YOUR_API_URL' with your actual API URL
    PERFORM
        net.http_post(
            url := 'YOUR_API_URL/webhooks/trip-confirmation',
            headers := jsonb_build_object(
                'Content-Type', 'application/json'
            ),
            body := jsonb_build_object(
                'type', 'INSERT',
                'table', 'trips',
                'schema', 'public',
                'record', row_to_json(NEW)
            )
        );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 3: Create trigger that fires after INSERT
DROP TRIGGER IF EXISTS trip_confirmation_trigger ON trips;

CREATE TRIGGER trip_confirmation_trigger
    AFTER INSERT ON trips
    FOR EACH ROW
    EXECUTE FUNCTION notify_trip_confirmation();

-- Step 4: Add comment for documentation
COMMENT ON FUNCTION notify_trip_confirmation() IS 
'Webhook function that sends booking confirmation when a trip is inserted';

COMMENT ON TRIGGER trip_confirmation_trigger ON trips IS 
'Trigger that automatically sends booking confirmation via webhook'; 