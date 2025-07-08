#!/usr/bin/env python3
"""
Apply the missing flight_status_history migration to production
"""

import asyncio
import os
from app.db.supabase_client import SupabaseDBClient

async def apply_flight_status_history_migration():
    """Apply the flight_status_history table and indexes"""
    
    print("🔧 APLICANDO MIGRACIÓN: flight_status_history")
    print("=" * 50)
    
    db_client = SupabaseDBClient()
    
    # Read the migration file
    migration_path = "database/migrations/008_add_flight_status_history.sql"
    
    try:
        with open(migration_path, 'r') as f:
            migration_sql = f.read()
        
        print(f"📖 Leyendo migración desde: {migration_path}")
        
        # Extract individual SQL statements
        statements = []
        current_statement = ""
        
        for line in migration_sql.split('\n'):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('--'):
                continue
            
            current_statement += line + "\n"
            
            # End of statement
            if line.endswith(';'):
                statements.append(current_statement.strip())
                current_statement = ""
        
        print(f"🔍 Encontradas {len(statements)} sentencias SQL")
        
        # Execute each statement
        for i, statement in enumerate(statements, 1):
            if not statement.strip():
                continue
                
            try:
                print(f"\n{i}. Ejecutando: {statement[:100]}...")
                
                # Use raw SQL execution
                # Note: This is a simplified approach - in production you'd want proper migration tracking
                response = await db_client._client.post(
                    f"{db_client.rest_url}/rpc/exec_sql",
                    json={"sql": statement}
                )
                
                if response.status_code == 200:
                    print(f"   ✅ Ejecutado correctamente")
                else:
                    print(f"   ⚠️  Status: {response.status_code}")
                    print(f"   Response: {response.text}")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                # Continue with other statements
        
        print(f"\n🎉 MIGRACIÓN COMPLETADA")
        
        # Test the table
        print(f"\n🧪 PROBANDO TABLA...")
        try:
            response = await db_client._client.get(
                f"{db_client.rest_url}/flight_status_history",
                params={"limit": "1"}
            )
            
            if response.status_code == 200:
                print("✅ Tabla flight_status_history accesible")
            else:
                print(f"❌ Error accediendo tabla: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error probando tabla: {e}")
        
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo de migración: {migration_path}")
    except Exception as e:
        print(f"💥 Error aplicando migración: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_client.close()

if __name__ == "__main__":
    asyncio.run(apply_flight_status_history_migration()) 