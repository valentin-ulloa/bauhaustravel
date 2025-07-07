-- Migration 011: Add eta_round field for ETA deduplication
-- Date: 2025-01-07
-- Description: Add eta_round varchar field to notifications_log for precise ETA comparison
--              This replaces fragile LIKE queries with exact string matches

-- Add eta_round column to notifications_log table
ALTER TABLE notifications_log 
ADD COLUMN eta_round varchar(50) DEFAULT NULL;

-- Create index for efficient ETA deduplication queries
CREATE INDEX IF NOT EXISTS idx_notifications_log_eta_round 
ON notifications_log(trip_id, notification_type, eta_round, sent_at)
WHERE delivery_status = 'SENT' AND eta_round IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN notifications_log.eta_round IS 
'Rounded ETA to 5-minute intervals for deduplication (ISO format or TBD)';

-- Migration validation
DO $$
BEGIN
    -- Check if column was added successfully
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'notifications_log' 
        AND column_name = 'eta_round'
    ) THEN
        RAISE EXCEPTION 'Migration failed: eta_round column not created';
    END IF;
    
    -- Check if index was created
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'notifications_log' 
        AND indexname = 'idx_notifications_log_eta_round'
    ) THEN
        RAISE EXCEPTION 'Migration failed: eta_round index not created';
    END IF;
    
    RAISE NOTICE 'Migration 011 completed successfully: eta_round field added';
END $$; 