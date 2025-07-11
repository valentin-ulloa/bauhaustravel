-- Migration 013: Add stay field to trips table
-- Date: 2025-01-16
-- Purpose: Store hotel/accommodation information for notifications

-- Add stay field to trips table
ALTER TABLE public.trips 
ADD COLUMN stay text DEFAULT NULL;

-- Create index for efficient stay lookups (optional, for performance)
CREATE INDEX IF NOT EXISTS idx_trips_stay 
ON public.trips(stay)
WHERE stay IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN public.trips.stay IS 
'Hotel/accommodation information in format: "Hotel Name, Address" for notification rendering';

-- Migration validation
DO $$
BEGIN
    -- Check if column was added successfully
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'trips' 
        AND column_name = 'stay'
    ) THEN
        RAISE EXCEPTION 'Migration failed: stay column not created';
    END IF;
    
    -- Check if index was created
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'trips' 
        AND indexname = 'idx_trips_stay'
    ) THEN
        RAISE EXCEPTION 'Migration failed: stay index not created';
    END IF;
    
    RAISE NOTICE 'Migration 013 completed successfully: stay field added to trips table';
END $$; 