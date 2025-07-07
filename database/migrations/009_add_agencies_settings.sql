-- Migration: Add agencies_settings table for multi-tenant configuration
-- Purpose: Enable per-agency business rules configuration (quiet hours, retry limits, etc.)
-- Date: 2025-01-16

-- Create agencies_settings table
CREATE TABLE public.agencies_settings (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    agency_id uuid NOT NULL,
    
    -- Notification timing settings
    quiet_hours_start time DEFAULT '22:00:00',
    quiet_hours_end time DEFAULT '09:00:00',
    timezone_override text, -- Optional timezone override (e.g., 'America/New_York')
    
    -- Flight notification settings
    boarding_notification_offset_minutes integer DEFAULT 90,
    landing_notification_enabled boolean DEFAULT true,
    reminder_24h_enabled boolean DEFAULT true,
    
    -- Retry and reliability settings
    max_retry_attempts integer DEFAULT 3,
    retry_initial_delay_seconds integer DEFAULT 5,
    retry_backoff_factor numeric DEFAULT 2.0,
    retry_max_delay_seconds integer DEFAULT 300,
    
    -- Rate limiting settings
    max_notifications_per_hour integer DEFAULT 50,
    max_notifications_per_day integer DEFAULT 200,
    
    -- Feature flags
    features jsonb DEFAULT '{}',
    
    -- Metadata
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    
    CONSTRAINT agencies_settings_pkey PRIMARY KEY (id),
    CONSTRAINT agencies_settings_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agencies(id) ON DELETE CASCADE,
    CONSTRAINT agencies_settings_agency_id_unique UNIQUE (agency_id),
    
    -- Validation constraints
    CONSTRAINT agencies_settings_boarding_offset_positive CHECK (boarding_notification_offset_minutes > 0),
    CONSTRAINT agencies_settings_retry_attempts_positive CHECK (max_retry_attempts > 0),
    CONSTRAINT agencies_settings_retry_delay_positive CHECK (retry_initial_delay_seconds > 0),
    CONSTRAINT agencies_settings_backoff_factor_valid CHECK (retry_backoff_factor >= 1.0),
    CONSTRAINT agencies_settings_rate_limits_positive CHECK (
        max_notifications_per_hour > 0 AND max_notifications_per_day > 0
    )
);

-- Create function to automatically update updated_at
CREATE OR REPLACE FUNCTION update_agencies_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for updated_at
CREATE TRIGGER trigger_agencies_settings_updated_at
    BEFORE UPDATE ON public.agencies_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_agencies_settings_updated_at();

-- Insert default settings for existing agencies
INSERT INTO public.agencies_settings (agency_id)
SELECT id FROM public.agencies 
ON CONFLICT (agency_id) DO NOTHING;

-- Create function to get agency settings with defaults
CREATE OR REPLACE FUNCTION get_agency_settings(p_agency_id uuid)
RETURNS TABLE (
    quiet_hours_start time,
    quiet_hours_end time,
    timezone_override text,
    boarding_notification_offset_minutes integer,
    landing_notification_enabled boolean,
    reminder_24h_enabled boolean,
    max_retry_attempts integer,
    retry_initial_delay_seconds integer,
    retry_backoff_factor numeric,
    retry_max_delay_seconds integer,
    max_notifications_per_hour integer,
    max_notifications_per_day integer,
    features jsonb
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.quiet_hours_start,
        s.quiet_hours_end,
        s.timezone_override,
        s.boarding_notification_offset_minutes,
        s.landing_notification_enabled,
        s.reminder_24h_enabled,
        s.max_retry_attempts,
        s.retry_initial_delay_seconds,
        s.retry_backoff_factor,
        s.retry_max_delay_seconds,
        s.max_notifications_per_hour,
        s.max_notifications_per_day,
        s.features
    FROM public.agencies_settings s
    WHERE s.agency_id = p_agency_id;
    
    -- If no settings found, return defaults
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT 
            '22:00:00'::time,
            '09:00:00'::time,
            NULL::text,
            90,
            true,
            true,
            3,
            5,
            2.0::numeric,
            300,
            50,
            200,
            '{}'::jsonb;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Add indexes for performance
CREATE INDEX idx_agencies_settings_agency_id ON public.agencies_settings(agency_id);

-- Add comments for documentation
COMMENT ON TABLE public.agencies_settings IS 'Per-agency configuration for notification behavior and business rules';
COMMENT ON FUNCTION get_agency_settings(uuid) IS 'Get agency settings with fallback to defaults';
COMMENT ON FUNCTION update_agencies_settings_updated_at() IS 'Auto-update updated_at timestamp';

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON public.agencies_settings TO your_app_user;
-- GRANT USAGE ON SEQUENCE agencies_settings_id_seq TO your_app_user; 