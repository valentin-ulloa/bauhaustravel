-- Migration: Add flight_status_history table for precise flight state tracking
-- Purpose: Enable accurate flight status diffs and prevent duplicate notifications
-- Date: 2025-01-16

-- Create flight_status_history table
CREATE TABLE public.flight_status_history (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    trip_id uuid NOT NULL,
    flight_number text NOT NULL,
    flight_date date NOT NULL,
    
    -- Flight status fields from AeroAPI
    status text NOT NULL,
    gate_origin text,
    gate_destination text,
    terminal_origin text,
    terminal_destination text,
    
    -- Timing fields
    estimated_out text,
    actual_out text,
    estimated_in text,
    actual_in text,
    
    -- Raw data for debugging and future fields
    raw_data jsonb,
    
    -- Metadata
    recorded_at timestamp with time zone DEFAULT now(),
    source text DEFAULT 'aeroapi' CHECK (source IN ('aeroapi', 'manual', 'webhook')),
    
    CONSTRAINT flight_status_history_pkey PRIMARY KEY (id),
    CONSTRAINT flight_status_history_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id) ON DELETE CASCADE
);

-- Create indexes for efficient lookups
CREATE INDEX idx_flight_status_history_trip_recorded 
ON public.flight_status_history(trip_id, recorded_at DESC);

CREATE INDEX idx_flight_status_history_flight_date 
ON public.flight_status_history(flight_number, flight_date, recorded_at DESC);

-- Create function to get latest status for a trip
CREATE OR REPLACE FUNCTION get_latest_flight_status(p_trip_id uuid)
RETURNS TABLE (
    status text,
    gate_origin text,
    gate_destination text,
    estimated_out text,
    actual_out text,
    estimated_in text,
    actual_in text,
    recorded_at timestamp with time zone
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        h.status,
        h.gate_origin,
        h.gate_destination,
        h.estimated_out,
        h.actual_out,
        h.estimated_in,
        h.actual_in,
        h.recorded_at
    FROM public.flight_status_history h
    WHERE h.trip_id = p_trip_id
    ORDER BY h.recorded_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Add comment for documentation
COMMENT ON TABLE public.flight_status_history IS 'Historical flight status data for change detection and auditing';
COMMENT ON FUNCTION get_latest_flight_status(uuid) IS 'Get the most recent flight status for a trip';

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT ON public.flight_status_history TO your_app_user;
-- GRANT USAGE ON SEQUENCE flight_status_history_id_seq TO your_app_user; 