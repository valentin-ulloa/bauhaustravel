-- Migration 007 FIXED: Create agencies table (corrected version)
-- Date: 2025-01-16
-- Purpose: Enable multi-tenant system for travel agencies
-- NOTE: trips.agency_id already exists, so we skip that

-- Create agencies table (this is what's missing)
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

-- Add agency_id to itineraries table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='itineraries' AND column_name='agency_id'
    ) THEN
        ALTER TABLE itineraries ADD COLUMN agency_id uuid REFERENCES agencies(id);
        CREATE INDEX ON itineraries (agency_id);
    END IF;
END $$;

-- Add agency_id to documents table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='documents' AND column_name='agency_id'
    ) THEN
        ALTER TABLE documents ADD COLUMN agency_id uuid REFERENCES agencies(id);
        CREATE INDEX ON documents (agency_id);
    END IF;
END $$;

-- Add agency_id to conversations table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='conversations' AND column_name='agency_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN agency_id uuid REFERENCES agencies(id);
        CREATE INDEX ON conversations (agency_id);
    END IF;
END $$;

-- Add agency_id to notifications_log table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='notifications_log' AND column_name='agency_id'
    ) THEN
        ALTER TABLE notifications_log ADD COLUMN agency_id uuid REFERENCES agencies(id);
        CREATE INDEX ON notifications_log (agency_id);
    END IF;
END $$;

-- Add foreign key constraint to trips.agency_id (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name='trips_agency_id_fkey' AND table_name='trips'
    ) THEN
        ALTER TABLE trips ADD CONSTRAINT trips_agency_id_fkey 
        FOREIGN KEY (agency_id) REFERENCES agencies(id);
        
        -- Create index if not exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE tablename='trips' AND indexname like '%agency_id%'
        ) THEN
            CREATE INDEX ON trips (agency_id);
        END IF;
    END IF;
END $$;

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

-- Update existing trips to belong to Nagori Travel (only if agency_id is null)
UPDATE trips 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing itineraries to belong to Nagori Travel (only if agency_id is null)
UPDATE itineraries 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing documents to belong to Nagori Travel (only if agency_id is null)
UPDATE documents 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing conversations to belong to Nagori Travel (only if agency_id is null)
UPDATE conversations 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Update existing notifications_log to belong to Nagori Travel (only if agency_id is null)
UPDATE notifications_log 
SET agency_id = '00000000-0000-0000-0000-000000000001' 
WHERE agency_id IS NULL;

-- Si quieres mantener agency_places, verificar su estructura:
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'agency_places' ORDER BY ordinal_position; 