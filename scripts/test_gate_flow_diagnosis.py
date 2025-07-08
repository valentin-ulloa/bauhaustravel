#!/usr/bin/env python3
"""
Gate Flow Diagnostic Script - Bauhaus Travel
Diagnoses gate information flow issues reported by user.

Tests:
1. Gate detection from AeroAPI
2. Gate persistence to trips table
3. Gate retrieval for notifications
4. End-to-end gate change flow

Usage: python scripts/test_gate_flow_diagnosis.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.db.supabase_client import SupabaseDBClient
from app.services.aeroapi_client import AeroAPIClient, FlightStatus
from app.models.database import Trip
import structlog

logger = structlog.get_logger()

class GateFlowDiagnostic:
    """Comprehensive gate flow diagnostic tool"""
    
    def __init__(self):
        self.db_client = SupabaseDBClient()
        self.aeroapi_client = AeroAPIClient()
        self.notifications_agent = NotificationsAgent()
    
    async def test_full_gate_flow(self, flight_number: str, departure_date: str) -> Dict[str, Any]:
        """
        Test complete gate flow for a specific flight.
        
        Args:
            flight_number: Flight number (e.g., "AA1641", "AA837")
            departure_date: Departure date in YYYY-MM-DD format
            
        Returns:
            Diagnostic results dict
        """
        results = {
            "flight_number": flight_number,
            "departure_date": departure_date,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tests": {}
        }
        
        print(f"\n🔍 GATE FLOW DIAGNOSIS: {flight_number} on {departure_date}")
        print("=" * 60)
        
        # Test 1: AeroAPI Gate Detection
        print("\n1️⃣ Testing AeroAPI Gate Detection...")
        aeroapi_result = await self._test_aeroapi_gate_detection(flight_number, departure_date)
        results["tests"]["aeroapi_detection"] = aeroapi_result
        self._print_test_result("AeroAPI Gate Detection", aeroapi_result)
        
        # Test 2: Database Gate Storage
        print("\n2️⃣ Testing Database Gate Storage...")
        db_storage_result = await self._test_database_gate_storage(flight_number, departure_date, aeroapi_result.get("current_status"))
        results["tests"]["database_storage"] = db_storage_result
        self._print_test_result("Database Gate Storage", db_storage_result)
        
        # Test 3: Gate Change Detection
        print("\n3️⃣ Testing Gate Change Detection...")
        change_detection_result = await self._test_gate_change_detection(flight_number, departure_date)
        results["tests"]["change_detection"] = change_detection_result
        self._print_test_result("Gate Change Detection", change_detection_result)
        
        # Test 4: Notification Gate Retrieval
        print("\n4️⃣ Testing Notification Gate Retrieval...")
        notification_result = await self._test_notification_gate_retrieval(flight_number, departure_date)
        results["tests"]["notification_retrieval"] = notification_result
        self._print_test_result("Notification Gate Retrieval", notification_result)
        
        # Test 5: Trip Update Verification
        print("\n5️⃣ Testing Trip Update Verification...")
        trip_update_result = await self._test_trip_update_verification(flight_number, departure_date)
        results["tests"]["trip_update"] = trip_update_result
        self._print_test_result("Trip Update Verification", trip_update_result)
        
        print("\n" + "=" * 60)
        print("🏁 DIAGNOSIS COMPLETE")
        
        return results
    
    async def _test_aeroapi_gate_detection(self, flight_number: str, departure_date: str) -> Dict[str, Any]:
        """Test if AeroAPI correctly detects gate information"""
        try:
            current_status = await self.aeroapi_client.get_flight_status(flight_number, departure_date)
            
            if not current_status:
                return {
                    "success": False,
                    "error": "No flight status returned from AeroAPI",
                    "current_status": None
                }
            
            gate_info = {
                "gate_origin": current_status.gate_origin,
                "gate_destination": current_status.gate_destination,
                "status": current_status.status,
                "has_gate_origin": bool(current_status.gate_origin),
                "has_gate_destination": bool(current_status.gate_destination)
            }
            
            return {
                "success": True,
                "current_status": current_status,
                "gate_info": gate_info,
                "message": f"Gate Origin: {current_status.gate_origin or 'N/A'}, Gate Destination: {current_status.gate_destination or 'N/A'}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "current_status": None
            }
    
    async def _test_database_gate_storage(self, flight_number: str, departure_date: str, flight_status: Optional[FlightStatus]) -> Dict[str, Any]:
        """Test if gate information is properly stored in database"""
        try:
            if not flight_status:
                return {
                    "success": False,
                    "error": "No flight status to test with"
                }
            
            # Find trip by flight number and date
            trips = await self._find_trips_by_flight(flight_number, departure_date)
            
            if not trips:
                return {
                    "success": False,
                    "error": f"No trips found for {flight_number} on {departure_date}"
                }
            
            trip = trips[0]  # Use first matching trip
            
            # Test comprehensive update
            update_result = await self.db_client.update_trip_comprehensive(
                trip.id,
                flight_status,
                update_metadata=True
            )
            
            if not update_result.success:
                return {
                    "success": False,
                    "error": f"Failed to update trip: {update_result.error}",
                    "trip_id": str(trip.id)
                }
            
            # Verify the update by fetching trip again
            updated_trip_result = await self.db_client.get_trip_by_id(trip.id)
            
            if not updated_trip_result.success:
                return {
                    "success": False,
                    "error": f"Failed to fetch updated trip: {updated_trip_result.error}",
                    "trip_id": str(trip.id)
                }
            
            updated_trip_data = updated_trip_result.data
            stored_gate = updated_trip_data.get("gate")
            
            return {
                "success": True,
                "trip_id": str(trip.id),
                "flight_status_gate": flight_status.gate_origin,
                "stored_gate": stored_gate,
                "gate_match": flight_status.gate_origin == stored_gate,
                "message": f"Flight Status Gate: {flight_status.gate_origin}, Stored Gate: {stored_gate}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _test_gate_change_detection(self, flight_number: str, departure_date: str) -> Dict[str, Any]:
        """Test gate change detection logic"""
        try:
            # Create mock previous and current status with different gates
            from app.services.aeroapi_client import FlightStatus
            
            previous_status = FlightStatus(
                ident=flight_number,
                status="Scheduled",
                gate_origin="D16"
            )
            
            current_status = FlightStatus(
                ident=flight_number,
                status="Scheduled", 
                gate_origin="D19"
            )
            
            # Test change detection
            changes = self.aeroapi_client.detect_flight_changes(current_status, previous_status)
            
            gate_changes = [change for change in changes if change["type"] == "gate_change"]
            
            return {
                "success": True,
                "changes_detected": len(changes),
                "gate_changes": len(gate_changes),
                "gate_change_details": gate_changes[0] if gate_changes else None,
                "message": f"Detected {len(gate_changes)} gate changes out of {len(changes)} total changes"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _test_notification_gate_retrieval(self, flight_number: str, departure_date: str) -> Dict[str, Any]:
        """Test gate retrieval for notification formatting"""
        try:
            # Find trip
            trips = await self._find_trips_by_flight(flight_number, departure_date)
            
            if not trips:
                return {
                    "success": False,
                    "error": f"No trips found for {flight_number} on {departure_date}"
                }
            
            trip = trips[0]
            
            # Test notification formatting for boarding
            message_data = await self.notifications_agent.format_message(
                trip,
                NotificationType.BOARDING,
                extra_data={"gate": "D16"}  # Simulated gate info
            )
            
            gate_variable = message_data.get("template_variables", {}).get("2", "N/A")
            
            return {
                "success": True,
                "trip_id": str(trip.id),
                "template_variables": message_data.get("template_variables", {}),
                "gate_variable": gate_variable,
                "message": f"Gate in notification template: {gate_variable}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _test_trip_update_verification(self, flight_number: str, departure_date: str) -> Dict[str, Any]:
        """Verify that trip updates are working correctly"""
        try:
            # Find trip
            trips = await self._find_trips_by_flight(flight_number, departure_date)
            
            if not trips:
                return {
                    "success": False,
                    "error": f"No trips found for {flight_number} on {departure_date}"
                }
            
            trip = trips[0]
            
            # Test direct gate update
            test_gate = "TEST_GATE_123"
            update_result = await self.db_client.update_trip_status(
                trip.id,
                {"gate": test_gate}
            )
            
            if not update_result.success:
                return {
                    "success": False,
                    "error": f"Failed to update trip gate: {update_result.error}"
                }
            
            # Verify update
            verification_result = await self.db_client.get_trip_by_id(trip.id)
            
            if not verification_result.success:
                return {
                    "success": False,
                    "error": f"Failed to verify trip update: {verification_result.error}"
                }
            
            verified_gate = verification_result.data.get("gate")
            
            # Restore original gate if we can
            original_gate = getattr(trip, 'gate', None)
            if original_gate:
                await self.db_client.update_trip_status(trip.id, {"gate": original_gate})
            
            return {
                "success": True,
                "trip_id": str(trip.id),
                "test_gate": test_gate,
                "verified_gate": verified_gate,
                "update_successful": test_gate == verified_gate,
                "message": f"Test gate: {test_gate}, Verified gate: {verified_gate}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _find_trips_by_flight(self, flight_number: str, departure_date: str) -> list:
        """Find trips matching flight number and date"""
        try:
            # Get all recent trips and filter
            from datetime import datetime
            date_dt = datetime.strptime(departure_date, "%Y-%m-%d")
            
            # Search around the date
            start_date = date_dt.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            end_date = date_dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            
            trips_result = await self.db_client.execute_query(
                """
                SELECT * FROM trips 
                WHERE flight_number = %s 
                AND departure_date >= %s 
                AND departure_date <= %s
                """,
                (flight_number, start_date.isoformat(), end_date.isoformat())
            )
            
            if not trips_result.success or not trips_result.data:
                return []
            
            return [Trip(**trip_data) for trip_data in trips_result.data]
            
        except Exception as e:
            logger.error("trip_search_failed", flight_number=flight_number, error=str(e))
            return []
    
    def _print_test_result(self, test_name: str, result: Dict[str, Any]):
        """Print formatted test result"""
        if result["success"]:
            print(f"   ✅ {test_name}: {result.get('message', 'PASSED')}")
        else:
            print(f"   ❌ {test_name}: {result.get('error', 'FAILED')}")
    
    async def close(self):
        """Clean up resources"""
        await self.db_client.close()
        await self.notifications_agent.close()

async def main():
    """Main diagnostic function"""
    print("🏥 GATE FLOW DIAGNOSTIC TOOL")
    print("Testing gate information flow for reported issues...")
    
    diagnostic = GateFlowDiagnostic()
    
    try:
        # Test the specific flights mentioned by user
        print("\n🔍 Testing AA1641 (reported boarding gate issue)")
        aa1641_result = await diagnostic.test_full_gate_flow("AA1641", "2025-01-16")
        
        print("\n🔍 Testing AA837 (reported gate change issue)")
        aa837_result = await diagnostic.test_full_gate_flow("AA837", "2025-01-16")
        
        # Summary
        print("\n📊 DIAGNOSTIC SUMMARY")
        print("=" * 60)
        
        # Check for critical failures
        critical_failures = []
        
        for flight, result in [("AA1641", aa1641_result), ("AA837", aa837_result)]:
            for test_name, test_result in result["tests"].items():
                if not test_result["success"]:
                    critical_failures.append(f"{flight} - {test_name}: {test_result.get('error', 'Unknown error')}")
        
        if critical_failures:
            print("🚨 CRITICAL ISSUES FOUND:")
            for failure in critical_failures:
                print(f"   • {failure}")
        else:
            print("✅ All critical tests passed")
        
        print(f"\n📝 Full diagnostic results saved to console")
        
    except Exception as e:
        print(f"❌ Diagnostic failed: {str(e)}")
        
    finally:
        await diagnostic.close()

if __name__ == "__main__":
    asyncio.run(main()) 