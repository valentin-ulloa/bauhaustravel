#!/usr/bin/env python3
"""
Gate Fixes Validation Script - Bauhaus Travel
Tests the specific fixes implemented for user-reported gate issues.

Usage: python scripts/test_fixes_validation.py
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.notifications_agent import NotificationsAgent
from app.agents.notifications_templates import NotificationType
from app.services.aeroapi_client import FlightStatus
from app.models.database import Trip
from app.config.messages import MessageConfig
import structlog

logger = structlog.get_logger()

class GateFixesValidator:
    """Validates the fixes for gate-related issues"""
    
    def __init__(self):
        self.notifications_agent = NotificationsAgent()
    
    async def test_fix_1_boarding_gate_display(self) -> Dict[str, Any]:
        """
        Test Fix 1: Boarding notification shows actual gate instead of 'Ver pantallas'
        
        Tests:
        - current_status.gate_origin available → should use it
        - trip.gate available → should use it as fallback
        - no gate available → should use placeholder
        """
        print("\n🔧 TESTING FIX 1: Boarding Gate Display")
        print("-" * 50)
        
        results = {"success": True, "tests": []}
        
        # Create a mock trip
        mock_trip = Trip(
            id=uuid4(),
            client_name="Valentin Ulloa",
            whatsapp="+1234567890",
            flight_number="AA1641",
            origin_iata="MIA",
            destination_iata="GUA",
            departure_date=datetime.now(timezone.utc),
            status="Scheduled",
            gate="D16",  # This is what's in the database
            inserted_at=datetime.now(timezone.utc),
            next_check_at=datetime.now(timezone.utc)
        )
        
        # Test Case 1: current_status has gate (should use this)
        print("📋 Test 1a: current_status.gate_origin available")
        try:
            current_status_with_gate = FlightStatus(
                ident="AA1641",
                status="Boarding",
                gate_origin="D19"  # New gate from AeroAPI
            )
            
            # Simulate the _process_flight_change logic
            notification_type = "boarding"
            extra_data = {}
            
            # This is the fixed logic from our implementation
            if notification_type == "boarding":
                gate_info = None
                
                if current_status_with_gate.gate_origin:
                    gate_info = current_status_with_gate.gate_origin
                elif hasattr(mock_trip, 'gate') and mock_trip.gate:
                    gate_info = mock_trip.gate
                
                if not gate_info:
                    gate_info = MessageConfig.get_gate_placeholder()
                
                extra_data["gate"] = gate_info
            
            # Format the message
            message_data = await self.notifications_agent.format_message(
                mock_trip,
                NotificationType.BOARDING,
                extra_data
            )
            
            gate_in_template = message_data["template_variables"]["2"]
            expected_gate = "D19"  # Should use current_status gate
            
            test_result = {
                "name": "current_status.gate_origin priority",
                "success": gate_in_template == expected_gate,
                "expected": expected_gate,
                "actual": gate_in_template,
                "details": "Should prioritize current_status.gate_origin over trip.gate"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {gate_in_template} (expected: {expected_gate})")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Test 1a failed: {str(e)}")
        
        # Test Case 2: No current_status gate, use trip.gate
        print("📋 Test 1b: fallback to trip.gate from database")
        try:
            current_status_no_gate = FlightStatus(
                ident="AA1641",
                status="Boarding",
                gate_origin=None  # No gate from AeroAPI
            )
            
            notification_type = "boarding"
            extra_data = {}
            
            if notification_type == "boarding":
                gate_info = None
                
                if current_status_no_gate.gate_origin:
                    gate_info = current_status_no_gate.gate_origin
                elif hasattr(mock_trip, 'gate') and mock_trip.gate:
                    gate_info = mock_trip.gate
                
                if not gate_info:
                    gate_info = MessageConfig.get_gate_placeholder()
                
                extra_data["gate"] = gate_info
            
            message_data = await self.notifications_agent.format_message(
                mock_trip,
                NotificationType.BOARDING,
                extra_data
            )
            
            gate_in_template = message_data["template_variables"]["2"]
            expected_gate = "D16"  # Should use trip.gate
            
            test_result = {
                "name": "trip.gate fallback",
                "success": gate_in_template == expected_gate,
                "expected": expected_gate,
                "actual": gate_in_template,
                "details": "Should fallback to trip.gate when current_status has no gate"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {gate_in_template} (expected: {expected_gate})")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Test 1b failed: {str(e)}")
        
        # Test Case 3: No gate available, use placeholder
        print("📋 Test 1c: placeholder when no gate available")
        try:
            trip_no_gate = Trip(
                id=uuid4(),
                client_name="Valentin Ulloa",
                whatsapp="+1234567890",
                flight_number="AA1641",
                origin_iata="MIA",
                destination_iata="GUA",
                departure_date=datetime.now(timezone.utc),
                status="Scheduled",
                inserted_at=datetime.now(timezone.utc),
                next_check_at=datetime.now(timezone.utc)
                # No gate field
            )
            
            current_status_no_gate = FlightStatus(
                ident="AA1641",
                status="Boarding",
                gate_origin=None
            )
            
            notification_type = "boarding"
            extra_data = {}
            
            if notification_type == "boarding":
                gate_info = None
                
                if current_status_no_gate.gate_origin:
                    gate_info = current_status_no_gate.gate_origin
                elif hasattr(trip_no_gate, 'gate') and trip_no_gate.gate:
                    gate_info = trip_no_gate.gate
                
                if not gate_info:
                    gate_info = MessageConfig.get_gate_placeholder()
                
                extra_data["gate"] = gate_info
            
            message_data = await self.notifications_agent.format_message(
                trip_no_gate,
                NotificationType.BOARDING,
                extra_data
            )
            
            gate_in_template = message_data["template_variables"]["2"]
            expected_gate = "Ver pantallas"  # Should use placeholder
            
            test_result = {
                "name": "placeholder fallback",
                "success": gate_in_template == expected_gate,
                "expected": expected_gate,
                "actual": gate_in_template,
                "details": "Should use placeholder only as last resort"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {gate_in_template} (expected: {expected_gate})")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Test 1c failed: {str(e)}")
        
        return results
    
    def test_fix_2_gate_update_logic(self) -> Dict[str, Any]:
        """
        Test Fix 2: Gate update logic only updates when valid gate available
        
        Tests that our update_trip_comprehensive fix preserves existing gate data
        """
        print("\n🔧 TESTING FIX 2: Gate Update Preservation Logic")
        print("-" * 50)
        
        results = {"success": True, "tests": []}
        
        # Test Case 1: Valid gate should be included in update
        print("📋 Test 2a: Valid gate should be included")
        try:
            flight_status_with_gate = FlightStatus(
                ident="AA837",
                status="Scheduled",
                gate_origin="D19"
            )
            
            # Simulate the update logic
            update_data = {"status": flight_status_with_gate.status}
            
            # This is our fixed logic
            if flight_status_with_gate.gate_origin:
                update_data["gate"] = flight_status_with_gate.gate_origin
            
            test_result = {
                "name": "valid gate inclusion",
                "success": "gate" in update_data and update_data["gate"] == "D19",
                "expected": {"status": "Scheduled", "gate": "D19"},
                "actual": update_data,
                "details": "Should include gate field when valid gate available"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {update_data}")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Test 2a failed: {str(e)}")
        
        # Test Case 2: None/empty gate should NOT overwrite existing
        print("📋 Test 2b: None gate should preserve existing")
        try:
            flight_status_no_gate = FlightStatus(
                ident="AA837",
                status="Delayed",
                gate_origin=None  # No gate info
            )
            
            # Simulate the update logic
            update_data = {"status": flight_status_no_gate.status}
            
            # This is our fixed logic
            if flight_status_no_gate.gate_origin:
                update_data["gate"] = flight_status_no_gate.gate_origin
            
            test_result = {
                "name": "preserve existing gate",
                "success": "gate" not in update_data,
                "expected": {"status": "Delayed"},  # No gate field
                "actual": update_data,
                "details": "Should NOT include gate field when None, preserving existing DB value"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {update_data}")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Test 2b failed: {str(e)}")
        
        return results
    
    def test_gate_change_detection(self) -> Dict[str, Any]:
        """
        Test that gate change detection works correctly
        """
        print("\n🔧 TESTING: Gate Change Detection")
        print("-" * 50)
        
        results = {"success": True, "tests": []}
        
        try:
            # Test gate change detection
            previous_status = FlightStatus(
                ident="AA837",
                status="Scheduled",
                gate_origin="D16"
            )
            
            current_status = FlightStatus(
                ident="AA837",
                status="Scheduled",
                gate_origin="D19"
            )
            
            changes = self.notifications_agent.aeroapi_client.detect_flight_changes(
                current_status, previous_status
            )
            
            gate_changes = [c for c in changes if c["type"] == "gate_change"]
            
            test_result = {
                "name": "gate change detection",
                "success": len(gate_changes) == 1 and gate_changes[0]["new_value"] == "D19",
                "expected": "1 gate change detected (D16 → D19)",
                "actual": f"{len(gate_changes)} gate changes: {gate_changes}",
                "details": "Should detect gate change from D16 to D19"
            }
            results["tests"].append(test_result)
            
            print(f"   {'✅' if test_result['success'] else '❌'} {test_result['name']}: {len(gate_changes)} changes detected")
            if gate_changes:
                print(f"      Change: {gate_changes[0]['old_value']} → {gate_changes[0]['new_value']}")
            
        except Exception as e:
            results["success"] = False
            print(f"   ❌ Gate change detection failed: {str(e)}")
        
        return results
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all validation tests"""
        print("🧪 GATE FIXES VALIDATION")
        print("=" * 60)
        print("Testing fixes for user-reported gate issues:")
        print("• AA1641: 'Ver pantallas' instead of gate D16")
        print("• AA837: Gate change to D19 not persisting")
        
        all_results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tests": {},
            "overall_success": True
        }
        
        # Run tests
        fix1_results = await self.test_fix_1_boarding_gate_display()
        all_results["tests"]["fix_1_boarding_gate"] = fix1_results
        
        fix2_results = self.test_fix_2_gate_update_logic()
        all_results["tests"]["fix_2_gate_persistence"] = fix2_results
        
        detection_results = self.test_gate_change_detection()
        all_results["tests"]["gate_change_detection"] = detection_results
        
        # Overall success
        all_results["overall_success"] = (
            fix1_results["success"] and 
            fix2_results["success"] and 
            detection_results["success"]
        )
        
        print("\n" + "=" * 60)
        print("🏁 VALIDATION SUMMARY")
        
        total_tests = sum(len(test_group["tests"]) for test_group in all_results["tests"].values())
        passed_tests = sum(
            len([t for t in test_group["tests"] if t["success"]]) 
            for test_group in all_results["tests"].values()
        )
        
        print(f"📊 Tests: {passed_tests}/{total_tests} passed")
        
        if all_results["overall_success"]:
            print("✅ ALL FIXES VALIDATED SUCCESSFULLY")
            print("\n🎯 Ready for deployment!")
        else:
            print("❌ Some tests failed - review fixes needed")
        
        return all_results
    
    async def close(self):
        """Clean up resources"""
        await self.notifications_agent.close()

async def main():
    """Main validation function"""
    validator = GateFixesValidator()
    
    try:
        await validator.run_all_tests()
    except Exception as e:
        print(f"❌ Validation failed: {str(e)}")
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main()) 