-- Migration 007: Create agencies table and add agency support
-- Date: 2025-01-16
-- Purpose: Enable multi-tenant system for travel agencies

-- Create agencies table
CREATE TABLE agencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  email text UNIQUE NOT NULL,
  phone text,
  website text,
  country text DEFAULT 'AR',
  status text DEFAULT 'active' CHECK (status IN ('active','suspended','pending')),
  branding jsonb DEFAULT '{}',
  pricing_tier text DEFAULT 'startup' CHECK (pricing_tier IN ('startup','growth','enterprise')),
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Add indexes for performance
CREATE INDEX ON agencies (email);
CREATE INDEX ON agencies (status);
CREATE INDEX ON agencies (country);

-- Add agency_id to trips table (nullable for backward compatibility)
ALTER TABLE trips ADD COLUMN agency_id uuid REFERENCES agencies(id);
CREATE INDEX ON trips (agency_id);

-- Add agency_id to itineraries table (for multi-tenant isolation)
ALTER TABLE itineraries ADD COLUMN agency_id uuid REFERENCES agencies(id);
CREATE INDEX ON itineraries (agency_id);

-- Add agency_id to documents table (for multi-tenant isolation)
ALTER TABLE documents ADD COLUMN agency_id uuid REFERENCES agencies(id);
CREATE INDEX ON documents (agency_id);

-- Add agency_id to conversations table (for multi-tenant isolation)
ALTER TABLE conversations ADD COLUMN agency_id uuid REFERENCES agencies(id);
CREATE INDEX ON conversations (agency_id);

-- Add agency_id to notifications_log table (for multi-tenant isolation)
ALTER TABLE notifications_log ADD COLUMN agency_id uuid REFERENCES agencies(id);
CREATE INDEX ON notifications_log (agency_id);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_agencies_updated_at BEFORE UPDATE ON agencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default "Nagori Travel" agency for existing trips
INSERT INTO agencies (
  id,
  name, 
  email, 
  phone,
  website,
  country,
  status,
  branding,
  pricing_tier
) VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Nagori Travel',
  'vale@bauhaustravel.com',
  '+13613094264',
  'https://nagortravel.com',
  'AR',
  'active',
  '{
    "display_name": "Nagori Travel",
    "color": "#4f46e5",
    "logo_url": "",
    "welcome_message": "¡Hola! Soy tu asistente AI de Nagori Travel. ¿En qué puedo ayudarte con tu viaje?"
  }',
  'enterprise'
);

-- Update existing trips to belong to Nagori Travel
UPDATE trips 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing itineraries to belong to Nagori Travel
UPDATE itineraries 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing documents to belong to Nagori Travel
UPDATE documents 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing conversations to belong to Nagori Travel
UPDATE conversations 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing notifications_log to belong to Nagori Travel
UPDATE notifications_log 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL; 