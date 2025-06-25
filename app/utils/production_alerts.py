"""
Production Alerting System - Basic error monitoring and alerts.

TC-004: Minimal alerting for production stability.
"""

import os
import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import httpx

logger = structlog.get_logger(__name__)

class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class Alert:
    """Alert data structure"""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    component: str
    trip_id: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = None

class ProductionAlerter:
    """
    Minimal production alerting system.
    
    Features:
    - Critical error detection
    - API failure monitoring
    - Simple rate limiting to avoid spam
    - Multiple notification channels (logs, webhook, email)
    """
    
    def __init__(self):
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL")  # Slack/Discord webhook
        self.admin_email = os.getenv("ADMIN_EMAIL", "vale@bauhaustravel.com")
        
        # Rate limiting: max 1 alert per error type per 15 minutes
        self._alert_cache: Dict[str, datetime] = {}
        self._rate_limit_minutes = 15
        
        # Error counters for trending
        self._error_counts: Dict[str, int] = {}
        
    def _get_cache_key(self, component: str, error_code: str) -> str:
        """Generate cache key for rate limiting"""
        return f"{component}:{error_code}"
    
    def _should_send_alert(self, component: str, error_code: str, level: AlertLevel) -> bool:
        """Check if alert should be sent based on rate limiting"""
        # Always send CRITICAL alerts
        if level == AlertLevel.CRITICAL:
            return True
        
        cache_key = self._get_cache_key(component, error_code)
        now = datetime.now(timezone.utc)
        
        # Check if we've sent this alert recently
        if cache_key in self._alert_cache:
            last_sent = self._alert_cache[cache_key]
            time_diff = now - last_sent
            
            if time_diff < timedelta(minutes=self._rate_limit_minutes):
                logger.debug("alert_rate_limited", 
                    component=component,
                    error_code=error_code,
                    minutes_since_last=time_diff.total_seconds() / 60
                )
                return False
        
        # Update cache
        self._alert_cache[cache_key] = now
        return True
    
    async def send_alert(self, alert: Alert) -> bool:
        """
        Send alert through available channels.
        
        Args:
            alert: Alert object to send
            
        Returns:
            True if alert was sent successfully
        """
        # Rate limiting check
        if not self._should_send_alert(alert.component, alert.error_code or "unknown", alert.level):
            return False
        
        # Update error counts
        error_key = f"{alert.component}:{alert.error_code}"
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        
        # Log the alert (always)
        logger.error("production_alert",
            level=alert.level.value,
            title=alert.title,
            message=alert.message,
            component=alert.component,
            trip_id=alert.trip_id,
            error_code=alert.error_code,
            error_count=self._error_counts[error_key],
            metadata=alert.metadata
        )
        
        # Send to webhook if configured
        success = False
        if self.webhook_url:
            success = await self._send_webhook_alert(alert)
        
        return success
    
    async def _send_webhook_alert(self, alert: Alert) -> bool:
        """Send alert to webhook (Slack/Discord/etc)"""
        try:
            # Format message for webhook
            emoji = self._get_alert_emoji(alert.level)
            color = self._get_alert_color(alert.level)
            
            webhook_data = {
                "embeds": [{
                    "title": f"{emoji} {alert.title}",
                    "description": alert.message,
                    "color": color,
                    "timestamp": alert.timestamp.isoformat(),
                    "fields": [
                        {"name": "Component", "value": alert.component, "inline": True},
                        {"name": "Level", "value": alert.level.value.upper(), "inline": True}
                    ]
                }]
            }
            
            if alert.trip_id:
                webhook_data["embeds"][0]["fields"].append({
                    "name": "Trip ID", "value": alert.trip_id[:8], "inline": True
                })
            
            if alert.error_code:
                webhook_data["embeds"][0]["fields"].append({
                    "name": "Error Code", "value": alert.error_code, "inline": True
                })
            
            # Send webhook
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(self.webhook_url, json=webhook_data)
                response.raise_for_status()
                
                logger.info("webhook_alert_sent", 
                    component=alert.component,
                    level=alert.level.value,
                    status_code=response.status_code
                )
                return True
                
        except Exception as e:
            logger.error("webhook_alert_failed", 
                error=str(e),
                component=alert.component
            )
            return False
    
    def _get_alert_emoji(self, level: AlertLevel) -> str:
        """Get emoji for alert level"""
        emojis = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨"
        }
        return emojis.get(level, "❓")
    
    def _get_alert_color(self, level: AlertLevel) -> int:
        """Get color code for alert level (Discord colors)"""
        colors = {
            AlertLevel.INFO: 0x3498DB,     # Blue
            AlertLevel.WARNING: 0xF39C12,  # Orange
            AlertLevel.ERROR: 0xE74C3C,    # Red
            AlertLevel.CRITICAL: 0x992D22  # Dark Red
        }
        return colors.get(level, 0x95A5A6)  # Gray
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of recent errors for health checks"""
        total_errors = sum(self._error_counts.values())
        
        # Get top 5 error types
        top_errors = sorted(
            self._error_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        return {
            "total_errors": total_errors,
            "unique_error_types": len(self._error_counts),
            "top_errors": [{"error": error, "count": count} for error, count in top_errors],
            "alert_cache_size": len(self._alert_cache)
        }

# Global alerter instance
alerter = ProductionAlerter()

# Convenience functions for common alert patterns
async def alert_critical_error(
    component: str, 
    error: Exception, 
    trip_id: Optional[str] = None,
    error_code: Optional[str] = None
):
    """Send critical error alert"""
    alert = Alert(
        level=AlertLevel.CRITICAL,
        title=f"Critical Error in {component}",
        message=f"Unexpected error: {str(error)[:200]}",
        timestamp=datetime.now(timezone.utc),
        component=component,
        trip_id=trip_id,
        error_code=error_code or "CRITICAL_ERROR",
        metadata={"error_type": type(error).__name__}
    )
    
    await alerter.send_alert(alert)

async def alert_api_failure(
    api_name: str,
    error: Exception,
    trip_id: Optional[str] = None,
    endpoint: Optional[str] = None
):
    """Send API failure alert"""
    alert = Alert(
        level=AlertLevel.ERROR,
        title=f"{api_name} API Failure",
        message=f"API request failed: {str(error)[:200]}",
        timestamp=datetime.now(timezone.utc),
        component=f"{api_name.lower()}_api",
        trip_id=trip_id,
        error_code="API_FAILURE",
        metadata={"endpoint": endpoint, "error_type": type(error).__name__}
    )
    
    await alerter.send_alert(alert)

async def alert_database_error(
    operation: str,
    error: Exception,
    trip_id: Optional[str] = None
):
    """Send database error alert"""
    alert = Alert(
        level=AlertLevel.ERROR,
        title=f"Database Error: {operation}",
        message=f"Database operation failed: {str(error)[:200]}",
        timestamp=datetime.now(timezone.utc),
        component="database",
        trip_id=trip_id,
        error_code="DATABASE_ERROR",
        metadata={"operation": operation, "error_type": type(error).__name__}
    )
    
    await alerter.send_alert(alert)

async def alert_user_experience_issue(
    issue_type: str,
    description: str,
    trip_id: Optional[str] = None,
    whatsapp_number: Optional[str] = None
):
    """Send user experience issue alert"""
    alert = Alert(
        level=AlertLevel.WARNING,
        title=f"UX Issue: {issue_type}",
        message=description,
        timestamp=datetime.now(timezone.utc),
        component="user_experience",
        trip_id=trip_id,
        error_code="UX_ISSUE",
        metadata={"whatsapp": whatsapp_number[-4:] if whatsapp_number else None}
    )
    
    await alerter.send_alert(alert) 