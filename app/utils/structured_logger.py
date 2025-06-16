"""
TC-004 Structured Logging Utility
MVP approach: Enhance existing structlog with agent context and standardized error tracking
"""

import structlog
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
import os
from enum import Enum

class LogLevel(Enum):
    """Standard log levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AgentLogger:
    """
    Enhanced structured logger for Bauhaus Travel agents.
    
    TC-004 Design Principles:
    - Consistent JSON structure across all agents
    - Agent context automatically included
    - Error tracking with stack traces
    - Performance metrics logging
    - Environment-aware verbosity
    """
    
    def __init__(self, agent_name: str, component: str = None):
        """
        Initialize agent logger with context.
        
        Args:
            agent_name: Name of the agent (e.g., 'concierge', 'notifications', 'itinerary')
            component: Optional sub-component (e.g., 'ai_response', 'context_loading')
        """
        self.agent_name = agent_name
        self.component = component
        self.base_logger = structlog.get_logger()
        
        # Base context that will be included in all logs
        self.base_context = {
            'agent': agent_name,
            'component': component,
            'environment': os.getenv('ENVIRONMENT', 'development'),
            'service': 'bauhaus-travel'
        }
    
    def _log(
        self, 
        level: LogLevel, 
        message: str, 
        operation: str = None,
        trip_id: str = None,
        user_id: str = None,
        duration_ms: float = None,
        error_code: str = None,
        **kwargs
    ) -> None:
        """
        Core logging method with standardized structure.
        
        Args:
            level: Log level
            message: Human-readable message
            operation: Operation name (e.g., 'generate_response', 'load_context')
            trip_id: Trip ID for correlation
            user_id: User/phone for correlation
            duration_ms: Operation duration in milliseconds
            error_code: Error code for categorization
            **kwargs: Additional context fields
        """
        
        # Build structured log entry
        log_entry = {
            **self.base_context,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'message': message,
            'level': level.value
        }
        
        # Add optional fields
        if operation:
            log_entry['operation'] = operation
        if trip_id:
            log_entry['trip_id'] = trip_id
        if user_id:
            log_entry['user_id'] = user_id
        if duration_ms is not None:
            log_entry['duration_ms'] = duration_ms
        if error_code:
            log_entry['error_code'] = error_code
        
        # Add any additional context
        log_entry.update(kwargs)
        
        # Log using structlog
        logger_method = getattr(self.base_logger, level.value)
        logger_method(message, **log_entry)
    
    def info(
        self, 
        message: str, 
        operation: str = None,
        trip_id: str = None,
        duration_ms: float = None,
        **kwargs
    ) -> None:
        """Log info level message"""
        self._log(LogLevel.INFO, message, operation=operation, trip_id=trip_id, 
                 duration_ms=duration_ms, **kwargs)
    
    def warning(
        self, 
        message: str, 
        operation: str = None,
        trip_id: str = None,
        error_code: str = None,
        **kwargs
    ) -> None:
        """Log warning level message"""
        self._log(LogLevel.WARNING, message, operation=operation, trip_id=trip_id, 
                 error_code=error_code, **kwargs)
    
    def error(
        self, 
        message: str, 
        error: Exception = None,
        operation: str = None,
        trip_id: str = None,
        error_code: str = None,
        **kwargs
    ) -> None:
        """
        Log error with optional exception details.
        
        Args:
            message: Error description
            error: Exception object for stack trace
            operation: Operation that failed
            trip_id: Trip ID for correlation
            error_code: Error code for categorization
            **kwargs: Additional context
        """
        log_kwargs = kwargs.copy()
        
        # Add exception details if provided
        if error:
            log_kwargs.update({
                'exception_type': type(error).__name__,
                'exception_message': str(error),
                'stack_trace': traceback.format_exc() if self._should_include_stacktrace() else None
            })
        
        self._log(LogLevel.ERROR, message, operation=operation, trip_id=trip_id, 
                 error_code=error_code, **log_kwargs)
    
    def performance(
        self, 
        operation: str,
        duration_ms: float,
        trip_id: str = None,
        success: bool = True,
        **metrics
    ) -> None:
        """
        Log performance metrics for operations.
        
        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            trip_id: Trip ID for correlation
            success: Whether operation succeeded
            **metrics: Additional performance metrics
        """
        message = f"{operation} completed in {duration_ms:.2f}ms"
        
        self.info(
            message,
            operation=operation,
            trip_id=trip_id,
            duration_ms=duration_ms,
            success=success,
            category="performance",
            **metrics
        )
    
    def api_call(
        self,
        service: str,
        endpoint: str,
        method: str = "GET",
        status_code: int = None,
        duration_ms: float = None,
        trip_id: str = None,
        retry_count: int = 0,
        **kwargs
    ) -> None:
        """
        Log external API calls with standardized format.
        
        Args:
            service: Service name (e.g., 'openai', 'aero_api', 'twilio')
            endpoint: API endpoint
            method: HTTP method
            status_code: Response status code
            duration_ms: Request duration
            trip_id: Trip ID for correlation
            retry_count: Number of retries made
            **kwargs: Additional API call context
        """
        success = status_code and 200 <= status_code < 300
        level = LogLevel.INFO if success else LogLevel.WARNING
        
        message = f"{service} API call: {method} {endpoint}"
        if status_code:
            message += f" -> {status_code}"
        
        self._log(
            level,
            message,
            operation="api_call",
            trip_id=trip_id,
            duration_ms=duration_ms,
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            retry_count=retry_count,
            success=success,
            category="api_call",
            **kwargs
        )
    
    def user_interaction(
        self,
        action: str,
        trip_id: str = None,
        user_phone: str = None,
        message_length: int = None,
        intent: str = None,
        **kwargs
    ) -> None:
        """
        Log user interactions (WhatsApp messages, API calls).
        
        Args:
            action: Action taken (e.g., 'message_received', 'response_sent')
            trip_id: Trip ID for correlation
            user_phone: User phone number (anonymized)
            message_length: Length of message
            intent: Detected intent
            **kwargs: Additional interaction context
        """
        # Anonymize phone number for privacy
        anonymized_phone = self._anonymize_phone(user_phone) if user_phone else None
        
        self.info(
            f"User interaction: {action}",
            operation="user_interaction",
            trip_id=trip_id,
            user_phone=anonymized_phone,
            action=action,
            message_length=message_length,
            intent=intent,
            category="user_interaction",
            **kwargs
        )
    
    def cost_tracking(
        self,
        service: str,
        operation: str,
        tokens_used: int = None,
        estimated_cost: float = None,
        trip_id: str = None,
        model_used: str = None,
        **kwargs
    ) -> None:
        """
        Log cost-related metrics for AI and API usage.
        
        Args:
            service: Service name (e.g., 'openai', 'aero_api')
            operation: Operation type
            tokens_used: Number of tokens used
            estimated_cost: Estimated cost in USD
            trip_id: Trip ID for correlation
            model_used: AI model used
            **kwargs: Additional cost context
        """
        self.info(
            f"Cost tracking: {service} {operation}",
            operation="cost_tracking",
            trip_id=trip_id,
            service=service,
            tokens_used=tokens_used,
            estimated_cost=estimated_cost,
            model_used=model_used,
            category="cost_tracking",
            **kwargs
        )
    
    def _should_include_stacktrace(self) -> bool:
        """Determine if stack traces should be included based on environment"""
        env = os.getenv('ENVIRONMENT', 'development').lower()
        return env in ['development', 'staging']
    
    def _anonymize_phone(self, phone: str) -> str:
        """Anonymize phone number for privacy (show last 4 digits only)"""
        if not phone or len(phone) < 4:
            return "***"
        return f"***{phone[-4:]}"


# Agent-specific logger instances
def get_agent_logger(agent_name: str, component: str = None) -> AgentLogger:
    """
    Factory function to get agent-specific logger.
    
    Args:
        agent_name: Name of the agent
        component: Optional component name
        
    Returns:
        Configured AgentLogger instance
    """
    return AgentLogger(agent_name, component)


# Pre-configured loggers for common agents
concierge_logger = get_agent_logger("concierge")
notifications_logger = get_agent_logger("notifications") 
itinerary_logger = get_agent_logger("itinerary")
scheduler_logger = get_agent_logger("scheduler")
api_logger = get_agent_logger("api")


class PerformanceTimer:
    """
    Context manager for measuring operation performance.
    
    Usage:
        logger = get_agent_logger("concierge")
        with PerformanceTimer(logger, "generate_response", trip_id="123"):
            # ... operation ...
    """
    
    def __init__(
        self, 
        logger: AgentLogger, 
        operation: str, 
        trip_id: str = None,
        **context
    ):
        self.logger = logger
        self.operation = operation
        self.trip_id = trip_id
        self.context = context
        self.start_time = None
        self.success = True
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration_ms = (time.time() - self.start_time) * 1000
        
        if exc_type is not None:
            self.success = False
            self.logger.error(
                f"{self.operation} failed",
                error=exc_val,
                operation=self.operation,
                trip_id=self.trip_id,
                duration_ms=duration_ms,
                **self.context
            )
        else:
            self.logger.performance(
                self.operation,
                duration_ms=duration_ms,
                trip_id=self.trip_id,
                success=self.success,
                **self.context
            ) 