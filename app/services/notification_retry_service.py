"""
Notification retry service with exponential backoff.

Handles failed notification attempts with intelligent retry logic,
preventing message loss while avoiding spam.
"""

import asyncio
import structlog
from typing import Callable, Dict, Any, Optional, Awaitable
from datetime import datetime, timezone
from ..models.database import DatabaseResult

logger = structlog.get_logger()


class NotificationRetryService:
    """
    Service for handling notification retries with exponential backoff.
    
    Features:
    - Exponential backoff (5s, 10s, 20s, 40s, ...)
    - Configurable max attempts
    - Structured logging for observability
    - Graceful failure handling
    
    Usage:
        retry_service = NotificationRetryService()
        result = await retry_service.send_with_retry(send_func, max_attempts=3)
    """
    
    def __init__(self):
        """Initialize the retry service."""
        logger.info("notification_retry_service_initialized")
    
    async def send_with_retry(
        self,
        send_func: Callable[[], Awaitable[DatabaseResult]],
        max_attempts: int = 3,
        initial_delay: float = 5.0,
        backoff_factor: float = 2.0,
        max_delay: float = 300.0,  # 5 minutes max
        context: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Execute send function with exponential backoff retry.
        
        Args:
            send_func: Async function that returns DatabaseResult
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay after each failure
            max_delay: Maximum delay between retries
            context: Optional context for logging
            
        Returns:
            DatabaseResult with final status
        """
        context = context or {}
        last_error = None
        delay = initial_delay
        
        logger.info("notification_retry_started",
            max_attempts=max_attempts,
            initial_delay=initial_delay,
            backoff_factor=backoff_factor,
            **context
        )
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info("notification_send_attempt",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    **context
                )
                
                # Execute the send function
                result = await send_func()
                
                if result.success:
                    logger.info("notification_send_success",
                        attempt=attempt,
                        final_success=True,
                        **context
                    )
                    return result
                else:
                    last_error = result.error
                    logger.warning("notification_send_attempt_failed",
                        attempt=attempt,
                        error=result.error,
                        **context
                    )
                    
            except Exception as e:
                last_error = str(e)
                logger.error("notification_send_attempt_exception",
                    attempt=attempt,
                    error=str(e),
                    **context
                )
            
            # Wait before retry (except on last attempt)
            if attempt < max_attempts:
                # Calculate delay with jitter to avoid thundering herd
                actual_delay = min(delay, max_delay)
                jitter = actual_delay * 0.1  # 10% jitter
                final_delay = actual_delay + (jitter * (0.5 - asyncio.get_event_loop().time() % 1))
                
                logger.info("notification_retry_waiting",
                    delay_seconds=final_delay,
                    next_attempt=attempt + 1,
                    **context
                )
                
                await asyncio.sleep(final_delay)
                delay *= backoff_factor
        
        # All attempts failed
        logger.error("notification_send_final_failure",
            max_attempts=max_attempts,
            final_error=last_error,
            **context
        )
        
        return DatabaseResult(
            success=False,
            error=f"Failed after {max_attempts} attempts: {last_error}"
        )
    
    async def send_with_circuit_breaker(
        self,
        send_func: Callable[[], Awaitable[DatabaseResult]],
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        context: Optional[Dict[str, Any]] = None
    ) -> DatabaseResult:
        """
        Execute send function with circuit breaker pattern.
        
        This is useful for protecting against cascading failures when
        external services (like Twilio) are down.
        
        Args:
            send_func: Async function that returns DatabaseResult
            failure_threshold: Number of failures before opening circuit
            reset_timeout: Time to wait before trying again
            context: Optional context for logging
            
        Returns:
            DatabaseResult with status
        """
        context = context or {}
        
        # TODO: Implement circuit breaker state management
        # For now, just delegate to retry logic
        logger.info("circuit_breaker_passthrough", **context)
        
        return await self.send_with_retry(
            send_func=send_func,
            max_attempts=3,
            context=context
        )
    
    def get_retry_metrics(self) -> Dict[str, Any]:
        """
        Get retry service metrics for monitoring.
        
        Returns:
            Dict with retry statistics
        """
        # TODO: Implement metrics collection
        # For now, return placeholder
        return {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "average_attempts": 0.0,
            "circuit_breaker_opens": 0
        } 