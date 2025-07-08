#!/usr/bin/env python3
"""
Apply flight_status_history migration directly to Supabase
"""

import asyncio
import os
import httpx
from datetime import datetime

async def apply_migration():
    """Apply the flight_status_history table migration"""
    
    print("🔧 APLICANDO MIGRACIÓN DIRECTA: flight_status_history")
    print("=" * 60)
    
    # Get Supabase credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Error: Variables SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY requeridas")
        return
    
    # SQL to create the table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS public.flight_status_history (
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        trip_id uuid NOT NULL,
        flight_number text NOT NULL,
        flight_date date NOT NULL,
        status text NOT NULL,
        gate_origin text,
        gate_destination text,
        terminal_origin text,
        terminal_destination text,
        estimated_out text,
        actual_out text,
        estimated_in text,
        actual_in text,
        raw_data jsonb,
        recorded_at timestamp with time zone DEFAULT now(),
        source text DEFAULT 'aeroapi' CHECK (source IN ('aeroapi', 'manual', 'webhook')),
        CONSTRAINT flight_status_history_pkey PRIMARY KEY (id),
        CONSTRAINT flight_status_history_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id) ON DELETE CASCADE
    );
    """
    
    # SQL to create indexes
    create_indexes_sql = """
    CREATE INDEX IF NOT EXISTS idx_flight_status_history_trip_recorded 
    ON public.flight_status_history(trip_id, recorded_at DESC);
    
    CREATE INDEX IF NOT EXISTS idx_flight_status_history_flight_date 
    ON public.flight_status_history(flight_number, flight_date, recorded_at DESC);
    """
    
    # SQL to create function
    create_function_sql = """
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
    """
    
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "apikey": supabase_key
        }
        
        try:
            # 1. Create table
            print("1️⃣ Creando tabla flight_status_history...")
            
            # Use a dummy insert to test if table exists
            test_response = await client.get(
                f"{supabase_url}/rest/v1/flight_status_history",
                headers=headers,
                params={"limit": "1"}
            )
            
            if test_response.status_code == 200:
                print("✅ Tabla flight_status_history ya existe")
            elif test_response.status_code == 404:
                print("❌ Tabla no existe - necesita ser creada manualmente")
                print("\n📋 INSTRUCCIONES MANUALES:")
                print("1. Abre el Dashboard de Supabase")
                print("2. Ve a SQL Editor")
                print("3. Ejecuta el siguiente SQL:")
                print("-" * 40)
                print(create_table_sql)
                print("-" * 40)
                print(create_indexes_sql)
                print("-" * 40)
                print(create_function_sql)
                print("-" * 40)
                
                # Wait for user to apply
                input("\n⏳ Presiona ENTER después de aplicar la migración en Supabase Dashboard...")
                
                # Test again
                test_response = await client.get(
                    f"{supabase_url}/rest/v1/flight_status_history",
                    headers=headers,
                    params={"limit": "1"}
                )
                
                if test_response.status_code == 200:
                    print("✅ Tabla flight_status_history creada exitosamente")
                else:
                    print(f"❌ Error verificando tabla: {test_response.status_code}")
                    print(test_response.text)
                    return
            else:
                print(f"❌ Error inesperado: {test_response.status_code}")
                print(test_response.text)
                return
            
            # 2. Test the table
            print("\n2️⃣ Probando acceso a la tabla...")
            
            test_response = await client.get(
                f"{supabase_url}/rest/v1/flight_status_history",
                headers=headers,
                params={"limit": "1"}
            )
            
            if test_response.status_code == 200:
                print("✅ Tabla accesible correctamente")
                data = test_response.json()
                print(f"   Records existentes: {len(data)}")
            else:
                print(f"❌ Error accediendo tabla: {test_response.status_code}")
                print(test_response.text)
                return
            
            print("\n🎉 MIGRACIÓN COMPLETADA EXITOSAMENTE")
            print("\n📊 SIGUIENTE PASO: Ejecutar diagnóstico AR1662")
            
        except Exception as e:
            print(f"💥 Error durante migración: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(apply_migration()) 