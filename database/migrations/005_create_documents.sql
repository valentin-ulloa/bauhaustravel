-- Migration: Create documents table for TC-003 ConciergeAgent
-- Purpose: Store travel documents (boarding passes, vouchers, etc.) with audit trail

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id uuid REFERENCES trips(id) ON DELETE CASCADE,
  type text NOT NULL CHECK (type IN (
    'boarding_pass', 
    'hotel_reservation', 
    'car_rental', 
    'transfer', 
    'insurance', 
    'tour_reservation'
  )),
  file_url text NOT NULL,
  file_name text,
  
  -- AUDIT FIELDS for agency compliance
  uploaded_by text NOT NULL,           -- "maria.garcia@agencia.com" | "system" | "+1234567890"
  uploaded_by_type text NOT NULL CHECK (uploaded_by_type IN (
    'agency_agent', 'system', 'client', 'api_integration'
  )),
  agency_id uuid,                      -- For multi-tenant agencies
  
  uploaded_at timestamptz DEFAULT now(),
  metadata jsonb                       -- Additional info as needed
);

-- Indexes for efficient queries
CREATE INDEX ON documents (trip_id);
CREATE INDEX ON documents (uploaded_by_type);
CREATE INDEX ON documents (agency_id);
CREATE INDEX ON documents (type);

-- Grant permissions for service_role
GRANT INSERT, SELECT, UPDATE, DELETE ON TABLE documents TO service_role; 