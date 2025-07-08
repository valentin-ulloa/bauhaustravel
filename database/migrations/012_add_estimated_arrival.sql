-- Migration 012: Add estimated_arrival field to trips table  
-- Date: 2025-01-06
-- Purpose: Store estimated arrival time from AeroAPI for comprehensive trip tracking

-- Add estimated_arrival column to trips table
ALTER TABLE public.trips 
ADD COLUMN estimated_arrival timestamp with time zone DEFAULT NULL;

-- Create index for efficient arrival-based queries
CREATE INDEX IF NOT EXISTS idx_trips_estimated_arrival 
ON public.trips(estimated_arrival)
WHERE estimated_arrival IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN public.trips.estimated_arrival IS 
'Estimated arrival time from AeroAPI (estimated_on field) for complete flight tracking';

-- Migration validation
DO $$
BEGIN
    -- Check if column was added successfully
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'trips' 
        AND column_name = 'estimated_arrival'
    ) THEN
        RAISE EXCEPTION 'Migration failed: estimated_arrival column not created';
    END IF;
    
    -- Check if index was created
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'trips' 
        AND indexname = 'idx_trips_estimated_arrival'
    ) THEN
        RAISE EXCEPTION 'Migration failed: estimated_arrival index not created';
    END IF;
    
    RAISE NOTICE 'Migration 012 completed successfully: estimated_arrival field added to trips table';
END $$; 