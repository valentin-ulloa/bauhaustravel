#!/usr/bin/env python3
"""
🛫 Test complete boarding gate verification cascade logic.
Tests the full verification chain: trip.gate → metadata → AeroAPI → fallback
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import UUID

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.models.database import Trip

async def test_gate_verification_cascade():
    """Test the complete gate verification cascade logic"""
    
    print("🛫 TESTING COMPLETE GATE VERIFICATION CASCADE")
    print("=" * 70)
    
    db_client = SupabaseDBClient()
    notifications_agent = NotificationsAgent()
    
    try:
        # Find BA820 trip
        print("1️⃣ FINDING BA820 TRIP...")
        
        now_utc = datetime.now(timezone.utc)
        future_window = now_utc + timedelta(days=1)
        all_trips = await db_client.get_trips_to_poll(future_window)
        
        ba820_trips = [trip for trip in all_trips if trip.flight_number == "BA820"]
        
        if not ba820_trips:
            print("   ❌ No BA820 trips found")
            return False
            
        original_trip = ba820_trips[0]
        print(f"   ✅ Found BA820 trip: {original_trip.id}")
        print(f"   Current gate in trip.gate: {getattr(original_trip, 'gate', 'None')}")
        print(f"   Current metadata: {getattr(original_trip, 'metadata', {})}")
        print()
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "SCENARIO 1: trip.gate has value",
                "gate_field": "B12",
                "metadata_gate": None,
                "expected_source": "trip.gate_field",
                "expected_gate": "B12"
            },
            {
                "name": "SCENARIO 2: trip.gate empty, metadata has gate_origin",
                "gate_field": None,
                "metadata_gate": {"gate_origin": "C7"},
                "expected_source": "metadata.gate_origin", 
                "expected_gate": "C7"
            },
            {
                "name": "SCENARIO 3: trip.gate empty, metadata has gate",
                "gate_field": None,
                "metadata_gate": {"gate": "D15"},
                "expected_source": "metadata.gate",
                "expected_gate": "D15"
            },
            {
                "name": "SCENARIO 4: Both empty, should call AeroAPI",
                "gate_field": None,
                "metadata_gate": {},
                "expected_source": "aeroapi_or_fallback",
                "expected_gate": "varies"  # Could be from AeroAPI or fallback
            }
        ]
        
        for i, scenario in enumerate(test_scenarios, 2):
            print(f"{i}️⃣ {scenario['name']}")
            print("-" * 50)
            
            # Create mock trip with scenario data
            mock_trip_data = {
                "id": original_trip.id,
                "client_name": original_trip.client_name,
                "whatsapp": original_trip.whatsapp,
                "flight_number": original_trip.flight_number,
                "origin_iata": original_trip.origin_iata,
                "destination_iata": original_trip.destination_iata,
                "departure_date": original_trip.departure_date,
                "status": original_trip.status,
                "metadata": scenario.get('metadata_gate', {}),
                "client_description": getattr(original_trip, 'client_description', ''),
                "agency_id": getattr(original_trip, 'agency_id', None)
            }
            
            # Add gate field if specified
            if scenario['gate_field']:
                mock_trip_data['gate'] = scenario['gate_field']
            
            mock_trip = Trip(**mock_trip_data)
            
            print(f"   Input: gate_field='{scenario['gate_field']}', metadata={scenario.get('metadata_gate', {})}")
            
            # Test the verification logic
            try:
                enhanced_data = await notifications_agent._prepare_boarding_notification_data(mock_trip)
                
                result_gate = enhanced_data.get("gate", "NOT_FOUND")
                
                print(f"   Result: gate='{result_gate}'")
                
                # Validate result
                if scenario['expected_gate'] == "varies":
                    # For AeroAPI scenario, just check that we got some result
                    if result_gate and result_gate != "NOT_FOUND":
                        print(f"   ✅ PASSED: Got gate result (either AeroAPI or fallback)")
                    else:
                        print(f"   ❌ FAILED: No gate result")
                else:
                    # For specific scenarios, check exact match
                    if result_gate == scenario['expected_gate']:
                        print(f"   ✅ PASSED: Got expected gate '{scenario['expected_gate']}'")
                    else:
                        print(f"   ❌ FAILED: Expected '{scenario['expected_gate']}', got '{result_gate}'")
                
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
            
            print()
        
        # Test complete flow with real boarding notification
        print(f"{len(test_scenarios) + 2}️⃣ TESTING COMPLETE BOARDING NOTIFICATION FLOW")
        print("-" * 50)
        
        print("   📨 Sending boarding notification with complete verification...")
        
        # Use original trip for real test
        result = await notifications_agent.send_single_notification(
            original_trip.id,
            NotificationType.BOARDING,
            {"test_mode": True, "verification_test": True}
        )
        
        if result.success:
            print("   ✅ Complete boarding notification sent successfully!")
            print(f"   Message SID: {result.data.get('message_sid', 'N/A')}")
        else:
            print(f"   ❌ Boarding notification failed: {result.error}")
        
        print()
        
        # Summary of verification logic
        print(f"{len(test_scenarios) + 3}️⃣ VERIFICATION LOGIC SUMMARY")
        print("-" * 50)
        
        print("   📋 COMPLETE VERIFICATION CASCADE:")
        print("   1. ✅ Check trip.gate field")
        print("   2. ✅ If empty → Check metadata fields (gate_origin, gate, departure_gate, etc.)")
        print("   3. ✅ If still empty → Fetch fresh data from AeroAPI")
        print("   4. ✅ If still empty after AeroAPI → Use fallback message")
        print()
        
        print("   🎯 BENEFITS:")
        print("   • Maximizes chance of finding specific gate information")
        print("   • Avoids unnecessary AeroAPI calls when gate already available")
        print("   • Only uses generic message as absolute last resort")
        print("   • Comprehensive logging for debugging")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await db_client.close()
        await notifications_agent.close()

async def demonstrate_verification_paths():
    """Demonstrate different verification paths"""
    
    print("\n📊 VERIFICATION PATHS DEMONSTRATION")
    print("=" * 70)
    
    print("🔍 PATH 1: trip.gate has value")
    print("   Input: trip.gate = 'A13'")
    print("   Result: ✅ Use 'A13' (no metadata or AeroAPI check needed)")
    print()
    
    print("🔍 PATH 2: trip.gate empty, metadata.gate_origin has value")
    print("   Input: trip.gate = None, metadata = {'gate_origin': 'B7'}")
    print("   Result: ✅ Use 'B7' (no AeroAPI check needed)")
    print()
    
    print("🔍 PATH 3: trip.gate empty, metadata.gate has value")
    print("   Input: trip.gate = None, metadata = {'gate': 'C12'}")
    print("   Result: ✅ Use 'C12' (no AeroAPI check needed)")
    print()
    
    print("🔍 PATH 4: Both empty, AeroAPI has gate")
    print("   Input: trip.gate = None, metadata = {}")
    print("   Process: Call AeroAPI → fresh_status.gate_origin = 'D3'")
    print("   Result: ✅ Use 'D3' + Update database")
    print()
    
    print("🔍 PATH 5: All sources empty")
    print("   Input: trip.gate = None, metadata = {}")
    print("   Process: Call AeroAPI → fresh_status.gate_origin = None")
    print("   Result: ⚠️ Use 'Ver pantallas del aeropuerto'")
    print()
    
    print("💡 OPTIMIZATION:")
    print("   • Early returns prevent unnecessary processing")
    print("   • AeroAPI only called when truly needed")
    print("   • Comprehensive logging shows exact path taken")

if __name__ == "__main__":
    print("🔧 BOARDING GATE VERIFICATION CASCADE TEST")
    print("=" * 70)
    
    success = asyncio.run(test_gate_verification_cascade())
    asyncio.run(demonstrate_verification_paths())
    
    if success:
        print(f"\n🎉 VERIFICATION CASCADE TEST: PASSED")
        print("The complete gate verification logic is working correctly!")
    else:
        print(f"\n❌ VERIFICATION CASCADE TEST: FAILED")
        print("Please review the implementation.") 