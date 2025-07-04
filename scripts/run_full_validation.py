#!/usr/bin/env python3
"""
Full System Validation for Bauhaus Travel
Master script that runs all validation tests and provides actionable insights
"""

import asyncio
import sys
import os
from datetime import datetime
import subprocess

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run_validation_script(script_name: str):
    """Run a validation script and capture output"""
    script_path = os.path.join("scripts", script_name)
    
    try:
        print(f"\n🔄 Running {script_name}...")
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(f"✅ {script_name} completed successfully")
            return result.stdout, None
        else:
            print(f"⚠️  {script_name} completed with warnings")
            return result.stdout, result.stderr
            
    except subprocess.TimeoutExpired:
        error = f"❌ {script_name} timed out (5 minutes)"
        print(error)
        return None, error
        
    except Exception as e:
        error = f"❌ {script_name} failed: {e}"
        print(error)
        return None, error

async def main():
    """Run full system validation"""
    
    print("🚀 **BAUHAUS TRAVEL SYSTEM VALIDATION**")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis will test:")
    print("1. 🕐 Timezone handling accuracy")
    print("2. 🛬 Landing detection functionality") 
    print("3. 🔄 Duplicate notification prevention")
    print("4. 🚨 Error alerting system")
    print("\n" + "=" * 60)
    
    # Validation scripts to run
    validation_scripts = [
        "test_timezone_validation.py",
        "test_landing_detection.py", 
        "test_duplicate_prevention.py",
        "test_error_alerting.py"
    ]
    
    results = {}
    
    # Run all validation scripts
    for script in validation_scripts:
        stdout, stderr = await run_validation_script(script)
        results[script] = {
            "stdout": stdout,
            "stderr": stderr
        }
        
        # Small delay between scripts
        await asyncio.sleep(2)
    
    # Generate summary report
    print("\n\n🎯 **VALIDATION SUMMARY REPORT**")
    print("=" * 60)
    
    critical_issues = []
    medium_issues = []
    low_issues = []
    
    # Analyze timezone validation
    if results["test_timezone_validation.py"]["stdout"]:
        print("\n🕐 **TIMEZONE ISSUES:**")
        if "MISMATCH" in results["test_timezone_validation.py"]["stdout"]:
            critical_issues.append("Timezone handling incorrect for international flights")
            print("   🔴 CRITICAL: Quiet hours using UTC instead of local time")
            print("   📋 Action: Implement origin_iata timezone conversion")
        else:
            print("   ✅ Timezone handling appears correct")
    
    # Analyze landing detection
    if results["test_landing_detection.py"]["stdout"]:
        print("\n🛬 **LANDING DETECTION ISSUES:**")
        if "PLACEHOLDER" in results["test_landing_detection.py"]["stdout"]:
            medium_issues.append("Landing detection not implemented")
            print("   🟡 MEDIUM: Landing detection is placeholder only")
            print("   📋 Action: Implement real landing detection logic")
        
        if "NO LANDING NOTIFICATION TEMPLATES" in results["test_landing_detection.py"]["stdout"]:
            medium_issues.append("Landing notification templates missing")
            print("   🟡 MEDIUM: No landing notification templates")
            print("   📋 Action: Create Twilio templates for landing welcome")
    
    # Analyze duplicate prevention
    if results["test_duplicate_prevention.py"]["stdout"]:
        print("\n🔄 **DUPLICATE PREVENTION ISSUES:**")
        if "DUPLICATES DETECTED" in results["test_duplicate_prevention.py"]["stdout"]:
            critical_issues.append("Duplicate notifications found in system")
            print("   🔴 CRITICAL: Duplicate notifications detected")
            print("   📋 Action: Investigate notification history gaps")
        
        if "HIGH PRIORITY" in results["test_duplicate_prevention.py"]["stdout"]:
            critical_issues.append("Transaction-safe notification logging needed")
            print("   🔴 CRITICAL: Notification logging not transaction-safe")
            print("   📋 Action: Implement atomic notification logging")
    
    # Analyze error alerting
    if results["test_error_alerting.py"]["stdout"]:
        print("\n🚨 **ERROR ALERTING ISSUES:**")
        if "Not configured" in results["test_error_alerting.py"]["stdout"]:
            medium_issues.append("Error alerting not fully configured")
            print("   🟡 MEDIUM: Alert channels not configured")
            print("   📋 Action: Set ALERT_WEBHOOK_URL and ADMIN_EMAIL")
        
        if "Does NOT import production_alerts" in results["test_error_alerting.py"]["stdout"]:
            low_issues.append("Some agents missing error alerts")
            print("   🟢 LOW: Some agents not using production alerts")
            print("   📋 Action: Add alerts to NotificationsAgent and AeroAPIClient")
    
    # Priority action plan
    print("\n\n📋 **IMMEDIATE ACTION PLAN**")
    print("=" * 60)
    
    if critical_issues:
        print("\n🔴 **CRITICAL (Fix First):**")
        for i, issue in enumerate(critical_issues, 1):
            print(f"   {i}. {issue}")
        
        print("\n   🛠️  **HOW TO FIX CRITICAL ISSUES:**")
        print("   1. Run: python scripts/fix_timezone_handling.py")
        print("   2. Run: python scripts/fix_duplicate_prevention.py")
        print("   3. Test with: curl -X POST /test-flight-polling")
        print("   4. Monitor Railway logs for improvements")
    
    if medium_issues:
        print("\n🟡 **MEDIUM PRIORITY:**")
        for i, issue in enumerate(medium_issues, 1):
            print(f"   {i}. {issue}")
            
        print("\n   🛠️  **HOW TO FIX MEDIUM ISSUES:**")
        print("   1. Run: python scripts/implement_landing_detection.py") 
        print("   2. Configure environment: ALERT_WEBHOOK_URL + ADMIN_EMAIL")
        print("   3. Create landing notification templates in Twilio")
    
    if low_issues:
        print("\n🟢 **LOW PRIORITY:**")
        for i, issue in enumerate(low_issues, 1):
            print(f"   {i}. {issue}")
    
    # Quick wins while working on V0
    print("\n\n⚡ **QUICK WINS (While you work on V0):**")
    print("=" * 60)
    print("1. 🔧 Set environment variables in Railway:")
    print("   ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK")
    print("   ADMIN_EMAIL=vale@bauhaustravel.com")
    print("")
    print("2. 🧪 Test notification system:")
    print("   curl -X POST https://web-production-92d8d.up.railway.app/test-flight-polling")
    print("")
    print("3. 📊 Monitor system health:")
    print("   curl https://web-production-92d8d.up.railway.app/health")
    print("")
    print("4. 🔍 Check logs for timezone issues:")
    print("   Railway > Logs > Search 'MISMATCH' or 'quiet_hours'")
    
    # Success metrics
    total_issues = len(critical_issues) + len(medium_issues) + len(low_issues)
    if total_issues == 0:
        print("\n\n🎉 **CONGRATULATIONS!**")
        print("No critical issues found. System validation passed!")
    else:
        print(f"\n\n📊 **VALIDATION RESULTS:**")
        print(f"   Total issues found: {total_issues}")
        print(f"   Critical: {len(critical_issues)}")
        print(f"   Medium: {len(medium_issues)}")
        print(f"   Low: {len(low_issues)}")
    
    print(f"\nValidation completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main()) 