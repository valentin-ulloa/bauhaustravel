-- Migration 006: Add gate field to trips table for flight tracking
-- Date: 2025-01-06
-- Purpose: Track gate information for flight change notifications

-- Add gate field to trips table
ALTER TABLE trips ADD COLUMN gate text;

-- Add index for efficient gate lookups (optional, for performance)
CREATE INDEX idx_trips_gate ON trips(gate) WHERE gate IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN trips.gate IS 'Flight departure gate (e.g., "A12", "B3") - updated from AeroAPI'; 