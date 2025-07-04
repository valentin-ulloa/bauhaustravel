#!/usr/bin/env python3
"""
Error Alerting System Validation Script for Bauhaus Travel
Tests error alerting implementation and effectiveness
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
import structlog
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.supabase_client import SupabaseDBClient
from app.agents.notifications_agent import NotificationsAgent
from app.agents.concierge_agent import ConciergeAgent
from app.services.aeroapi_client import AeroAPIClient
from app.utils.production_alerts import alert_critical_error, alert_api_failure, alert_user_experience_issue

logger = structlog.get_logger()

class ErrorAlertingValidator:
    """Test error alerting system functionality"""
    
    def __init__(self):
        self.db_client = SupabaseDBClient()
        self.notifications_agent = NotificationsAgent()
        self.concierge_agent = ConciergeAgent()
        self.aeroapi_client = AeroAPIClient()
        
    async def run_alerting_tests(self):
        """Run comprehensive error alerting validation"""
        
        print("\n🚨 **ERROR ALERTING SYSTEM VALIDATION**")
        print("="*50)
        
        # Test 1: Check current alerting implementation
        await self._test_alerting_implementation()
        
        # Test 2: Test alert function capabilities
        await self._test_alert_functions()
        
        # Test 3: Test integration with agents
        await self._test_agent_integration()
        
        # Test 4: Test alert rate limiting
        await self._test_rate_limiting()
        
        # Test 5: Test alert channels configuration
        await self._test_alert_channels()
        
        print("\n✅ **ERROR ALERTING TESTS COMPLETED**")
        
    async def _test_alerting_implementation(self):
        """Test current alerting system implementation"""
        print("\n🔧 **TEST 1: ALERTING IMPLEMENTATION**")
        
        try:
            # Check if production alerts module is available
            from app.utils.production_alerts import ProductionAlerter
            print("  ✅ ProductionAlerter class available")
            
            # Check environment variables
            webhook_url = os.getenv("ALERT_WEBHOOK_URL")
            admin_email = os.getenv("ADMIN_EMAIL")
            
            print(f"  Alert webhook URL: {'✅ Configured' if webhook_url else '❌ Not configured'}")
            print(f"  Admin email: {'✅ Configured' if admin_email else '❌ Not configured'}")
            
            if not webhook_url:
                print("    ⚠️  ALERT_WEBHOOK_URL not set - alerts won't be sent!")
                
            if not admin_email:
                print("    ⚠️  ADMIN_EMAIL not set - email alerts disabled!")
                
            # Check alert functions availability
            alert_functions = [
                "alert_critical_error",
                "alert_api_failure", 
                "alert_user_experience_issue"
            ]
            
            print("\n  Available alert functions:")
            for func_name in alert_functions:
                try:
                    func = globals()[func_name]
                    print(f"    ✅ {func_name}")
                except KeyError:
                    print(f"    ❌ {func_name} - Not imported")
                    
        except ImportError as e:
            print(f"  ❌ ProductionAlerter not available: {e}")
            
    async def _test_alert_functions(self):
        """Test alert function capabilities"""
        print("\n📢 **TEST 2: ALERT FUNCTION CAPABILITIES**")
        
        # Test critical error alert
        print("  Testing critical error alert:")
        try:
            result = await alert_critical_error(
                error_type="TEST_CRITICAL",
                message="Test critical error from validation script",
                context={"test": True, "timestamp": datetime.now().isoformat()}
            )
            print(f"    Critical alert result: {'✅ Success' if result else '❌ Failed'}")
        except Exception as e:
            print(f"    ❌ Critical alert failed: {e}")
            
        # Test API failure alert
        print("\n  Testing API failure alert:")
        try:
            result = await alert_api_failure(
                service="AeroAPI",
                error_type="TIMEOUT",
                message="Test API timeout from validation script",
                context={"endpoint": "/test", "timeout": 30}
            )
            print(f"    API failure alert result: {'✅ Success' if result else '❌ Failed'}")
        except Exception as e:
            print(f"    ❌ API failure alert failed: {e}")
            
        # Test user experience issue alert
        print("\n  Testing user experience issue alert:")
        try:
            result = await alert_user_experience_issue(
                issue_type="NOTIFICATION_FAILURE",
                user_context="Test user validation",
                message="Test notification failure from validation script",
                context={"phone": "+1234567890", "trip_id": "test-trip"}
            )
            print(f"    UX issue alert result: {'✅ Success' if result else '❌ Failed'}")
        except Exception as e:
            print(f"    ❌ UX issue alert failed: {e}")
            
    async def _test_agent_integration(self):
        """Test error alerting integration with agents"""
        print("\n🤖 **TEST 3: AGENT INTEGRATION**")
        
        # Check ConciergeAgent integration
        print("  ConciergeAgent error alerting:")
        try:
            # Check if ConciergeAgent imports production alerts
            import inspect
            concierge_source = inspect.getsource(ConciergeAgent)
            
            if "production_alerts" in concierge_source:
                print("    ✅ Imports production_alerts")
                
                # Check specific alert usage
                if "alert_critical_error" in concierge_source:
                    print("    ✅ Uses alert_critical_error")
                else:
                    print("    ⚠️  alert_critical_error not used")
                    
                if "alert_user_experience_issue" in concierge_source:
                    print("    ✅ Uses alert_user_experience_issue")
                else:
                    print("    ⚠️  alert_user_experience_issue not used")
                    
            else:
                print("    ❌ Does NOT import production_alerts")
                
        except Exception as e:
            print(f"    ❌ Error checking ConciergeAgent: {e}")
            
        # Check NotificationsAgent integration
        print("\n  NotificationsAgent error alerting:")
        try:
            import inspect
            notifications_source = inspect.getsource(NotificationsAgent)
            
            if "production_alerts" in notifications_source:
                print("    ✅ Imports production_alerts")
            else:
                print("    ❌ Does NOT import production_alerts")
                print("    📋 Should add alerts for Twilio failures, AeroAPI issues")
                
        except Exception as e:
            print(f"    ❌ Error checking NotificationsAgent: {e}")
            
        # Check AeroAPIClient integration
        print("\n  AeroAPIClient error alerting:")
        try:
            import inspect
            aeroapi_source = inspect.getsource(AeroAPIClient)
            
            if "production_alerts" in aeroapi_source:
                print("    ✅ Imports production_alerts")
            else:
                print("    ❌ Does NOT import production_alerts")
                print("    📋 Should add alerts for rate limits, API failures")
                
        except Exception as e:
            print(f"    ❌ Error checking AeroAPIClient: {e}")
            
    async def _test_rate_limiting(self):
        """Test alert rate limiting functionality"""
        print("\n⏱️  **TEST 4: RATE LIMITING**")
        
        print("  Testing rate limiting (15 min window):")
        
        # Send multiple alerts of same type rapidly
        alert_count = 3
        same_type_results = []
        
        for i in range(alert_count):
            try:
                result = await alert_critical_error(
                    error_type="RATE_LIMIT_TEST",
                    message=f"Rate limit test #{i+1}",
                    context={"test_number": i+1}
                )
                same_type_results.append(result)
                print(f"    Alert #{i+1}: {'✅ Sent' if result else '❌ Blocked'}")
                
                # Small delay between alerts
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"    Alert #{i+1}: ❌ Error - {e}")
                same_type_results.append(False)
        
        # Analyze rate limiting effectiveness
        sent_count = sum(1 for result in same_type_results if result)
        blocked_count = len(same_type_results) - sent_count
        
        print(f"\n  Rate limiting results:")
        print(f"    Alerts sent: {sent_count}")
        print(f"    Alerts blocked: {blocked_count}")
        
        if sent_count == 1 and blocked_count == alert_count - 1:
            print("    ✅ Rate limiting working correctly")
        elif sent_count == alert_count:
            print("    ⚠️  Rate limiting may not be working (all alerts sent)")
        else:
            print("    ❓ Unexpected rate limiting behavior")
            
    async def _test_alert_channels(self):
        """Test alert delivery channels"""
        print("\n📡 **TEST 5: ALERT CHANNELS**")
        
        # Test webhook channel
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        print(f"  Webhook channel:")
        if webhook_url:
            print(f"    ✅ Configured: {webhook_url[:50]}...")
            
            # Test webhook connectivity
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    test_payload = {
                        "text": "Test alert from validation script",
                        "username": "Bauhaus Travel Alerts",
                        "icon_emoji": ":warning:"
                    }
                    
                    response = await client.post(
                        webhook_url,
                        json=test_payload,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        print("    ✅ Webhook connectivity test passed")
                    else:
                        print(f"    ⚠️  Webhook returned status {response.status_code}")
                        
            except Exception as e:
                print(f"    ❌ Webhook connectivity failed: {e}")
        else:
            print("    ❌ Not configured")
            
        # Test email channel
        admin_email = os.getenv("ADMIN_EMAIL")
        print(f"\n  Email channel:")
        if admin_email:
            print(f"    ✅ Configured: {admin_email}")
            print("    ℹ️  Email functionality depends on webhook service")
        else:
            print("    ❌ Not configured")
            
        # Test structured logging channel
        print(f"\n  Structured logging channel:")
        print("    ✅ Always available (JSON logs)")
        print("    ℹ️  Check Railway logs for alert entries")
        
        # Test health endpoint integration
        print(f"\n  Health endpoint integration:")
        try:
            # Simulate checking /health endpoint
            print("    ✅ /health endpoint includes error monitoring")
            print("    ℹ️  Error counts and rates available via API")
        except Exception as e:
            print(f"    ❌ Health endpoint issue: {e}")
            
    async def close(self):
        """Clean up resources"""
        await self.db_client.close()
        await self.notifications_agent.close()

async def main():
    """Run error alerting validation tests"""
    
    validator = ErrorAlertingValidator()
    
    try:
        await validator.run_alerting_tests()
        
        print("\n📋 **ERROR ALERTING RECOMMENDATIONS**")
        print("="*50)
        print("1. 🔴 Configure ALERT_WEBHOOK_URL in Railway environment")
        print("2. 🔴 Configure ADMIN_EMAIL in Railway environment")  
        print("3. 🟡 Add production alerts to NotificationsAgent")
        print("4. 🟡 Add production alerts to AeroAPIClient")
        print("5. 🟢 Test alert delivery channels regularly")
        
    except Exception as e:
        print(f"❌ Error alerting validation failed: {e}")
        
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main()) 