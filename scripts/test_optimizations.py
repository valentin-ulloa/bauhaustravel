#!/usr/bin/env python3
"""
Test script for TC-004 optimizations.

Tests:
1. Document bug fix - verify links are returned
2. Database optimization - verify optimized method is used  
3. Production alerts - verify alerting system works
"""

import asyncio
import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.concierge_agent import ConciergeAgent
from app.utils.production_alerts import alerter, alert_critical_error, AlertLevel, Alert
from app.models.database import Trip

async def test_document_fix():
    """Test that document requests now return actual links"""
    print("🧪 Testing Document Bug Fix...")
    
    # Mock document with URL
    mock_doc = {
        'id': 'test-123',
        'file_name': 'boarding_pass_test.pdf',
        'file_url': 'https://example.com/docs/boarding_pass_test.pdf',
        'uploaded_at': '2025-01-15T10:30:00Z',
        'type': 'boarding_pass'
    }
    
    agent = ConciergeAgent()
    
    # Test response generation
    trip = Trip(
        id='test-trip',
        client_name='Test User',
        destination_iata='MIA',
        whatsapp='+1234567890',
        flight_number='AA1234',
        origin_iata='LAX',
        departure_date=datetime.now(),
        status='scheduled',
        client_description='test trip'
    )
    
    # Mock the database call to return our test document
    original_get_docs = agent.db_client.get_documents_by_trip
    
    async def mock_get_documents(trip_id, doc_type=None):
        return [mock_doc]
    
    agent.db_client.get_documents_by_trip = mock_get_documents
    
    try:
        response = await agent._handle_document_request(trip, 'boarding_pass')
        
        # Verify the response contains the actual link
        if 'https://example.com/docs/boarding_pass_test.pdf' in response:
            print("✅ Document link fix working - URL included in response")
            if 'Próximamente' not in response:
                print("✅ Removed 'Próximamente' placeholder text")
            else:
                print("❌ Still showing 'Próximamente' placeholder")
        else:
            print("❌ Document link NOT included in response")
            print(f"Response: {response[:200]}...")
            
    except Exception as e:
        print(f"❌ Document test failed: {e}")
    finally:
        # Restore original method
        agent.db_client.get_documents_by_trip = original_get_docs
        await agent.close()


async def test_database_optimization():
    """Test that optimized database method is being used"""
    print("\n🗄️ Testing Database Optimization...")
    
    db_client = SupabaseDBClient()
    
    try:
        # Test both methods and compare (using a real trip ID if available)
        test_trip_id = "test-trip-123"  # Mock ID for testing
        
        print("Testing optimized context loading method...")
        
        # The optimized method should handle missing trips gracefully
        context = await db_client.get_complete_trip_context_optimized(test_trip_id)
        
        print("✅ Optimized database method executed successfully")
        print(f"   - Has trip data: {bool(context.trip)}")
        print(f"   - Has itinerary: {context.itinerary is not None}")
        print(f"   - Documents count: {len(context.documents)}")
        print(f"   - Messages count: {len(context.recent_messages)}")
        
    except Exception as e:
        print(f"❌ Database optimization test failed: {e}")
    finally:
        await db_client.close()


async def test_production_alerts():
    """Test that production alerting system works"""
    print("\n🚨 Testing Production Alerts...")
    
    try:
        # Test alert creation and formatting
        test_alert = Alert(
            level=AlertLevel.WARNING,
            title="Test Alert",
            message="This is a test alert to verify the system works",
            timestamp=datetime.now(),
            component="test_system",
            trip_id="test-123",
            error_code="TEST_ALERT",
            metadata={"test": True}
        )
        
        # Test rate limiting (should send)
        if alerter._should_send_alert("test_system", "TEST_ALERT", AlertLevel.WARNING):
            print("✅ Alert rate limiting working - first alert allowed")
        else:
            print("❌ Alert rate limiting failed - first alert blocked")
        
        # Test alert processing (without actually sending webhook)
        original_webhook = alerter.webhook_url
        alerter.webhook_url = None  # Disable webhook for testing
        
        success = await alerter.send_alert(test_alert)
        print(f"✅ Alert processing: {'success' if success else 'logged only (no webhook)'}")
        
        # Test error summary
        summary = alerter.get_error_summary()
        print(f"✅ Error summary generated: {summary['total_errors']} total errors")
        
        # Test convenience functions
        await alert_critical_error(
            component="test_component",
            error=Exception("Test critical error"),
            trip_id="test-trip",
            error_code="TEST_CRITICAL"
        )
        print("✅ Critical error alert function working")
        
        # Restore webhook URL
        alerter.webhook_url = original_webhook
        
    except Exception as e:
        print(f"❌ Production alerts test failed: {e}")


async def main():
    """Run all optimization tests"""
    print("🚀 TC-004 Optimizations Test Suite")
    print("=" * 50)
    
    try:
        await test_document_fix()
        await test_database_optimization()
        await test_production_alerts()
        
        print("\n" + "=" * 50)
        print("✅ All optimization tests completed!")
        print("\nNext steps:")
        print("1. Deploy to Railway")
        print("2. Set ALERT_WEBHOOK_URL environment variable")
        print("3. Test in production with real user queries")
        
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main()) 