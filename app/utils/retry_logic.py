"""
TC-004 Retry Logic - Simple but Effective
MVP approach: Handle the 80% of failures with 20% of the complexity
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import TypeVar, Callable, Any, Optional, List
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

T = TypeVar('T')

@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    
    # Which exceptions should trigger retries
    retryable_exceptions: tuple = (
        # Network issues
        ConnectionError,
        TimeoutError,
        # HTTP library timeouts
        Exception,  # We'll be more specific in practice
    )

class RetryableError(Exception):
    """Indicates an operation should be retried"""
    pass

class NonRetryableError(Exception):
    """Indicates an operation should NOT be retried"""
    pass

async def retry_async(
    func: Callable[..., T],
    config: RetryConfig = None,
    context: str = "unknown_operation"
) -> T:
    """
    Simple async retry decorator with exponential backoff.
    
    TC-004 Design Principles:
    - Simple to use and understand
    - Effective for common failure patterns
    - Proper logging for debugging
    - Configurable but sensible defaults
    
    Args:
        func: Async function to retry
        config: Retry configuration (optional)
        context: Context for logging (operation name)
    
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            start_time = datetime.now(timezone.utc)
            result = await func()
            
            # Log successful call (especially if it was a retry)
            if attempt > 0:
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.info("retry_success",
                    context=context,
                    attempt=attempt + 1,
                    duration_ms=duration * 1000,
                    total_attempts=attempt + 1
                )
            
            return result
            
        except NonRetryableError:
            # Don't retry these - re-raise immediately
            raise
            
        except Exception as e:
            last_exception = e
            is_last_attempt = attempt == config.max_attempts - 1
            
            # Check if this exception type is retryable
            if not _is_retryable_exception(e, config):
                logger.error("non_retryable_error",
                    context=context,
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                raise e
            
            if is_last_attempt:
                logger.error("retry_exhausted",
                    context=context,
                    total_attempts=config.max_attempts,
                    final_error=str(e),
                    error_type=type(e).__name__
                )
                raise e
            
            # Calculate delay with exponential backoff + jitter
            delay = _calculate_delay(attempt, config)
            
            logger.warning("retry_attempt",
                context=context,
                attempt=attempt + 1,
                max_attempts=config.max_attempts,
                error_type=type(e).__name__,
                error_message=str(e)[:200],
                next_delay_seconds=delay
            )
            
            await asyncio.sleep(delay)
    
    # This should never be reached, but just in case
    raise last_exception

def _is_retryable_exception(exception: Exception, config: RetryConfig) -> bool:
    """Determine if an exception should trigger a retry"""
    
    # Check for specific HTTP status codes (if using httpx)
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        status_code = exception.response.status_code
        
        # Retryable HTTP status codes
        retryable_status_codes = {
            429,  # Rate limit
            500,  # Internal server error
            502,  # Bad gateway
            503,  # Service unavailable
            504,  # Gateway timeout
        }
        
        if status_code in retryable_status_codes:
            return True
        
        # Non-retryable HTTP status codes
        if 400 <= status_code < 500 and status_code != 429:
            return False  # Client errors (except rate limit)
    
    # Check against configured exception types
    return isinstance(exception, config.retryable_exceptions)

def _calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay with exponential backoff and optional jitter"""
    
    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = config.base_delay * (config.exponential_base ** attempt)
    
    # Cap at max_delay
    delay = min(delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        jitter_factor = random.uniform(0.5, 1.5)  # ±50% jitter
        delay *= jitter_factor
    
    return delay

# Pre-configured retry configs for common use cases
class RetryConfigs:
    """Pre-configured retry settings for different APIs"""
    
    AERO_API = RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True
    )
    
    OPENAI_API = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True
    )
    
    TWILIO_API = RetryConfig(
        max_attempts=2,  # Shorter for user-facing operations
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0,
        jitter=True
    )
    
    DATABASE = RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False  # DB operations should be more predictable
    )

# Convenience decorators for common patterns
def with_aero_retry(func):
    """Decorator for AeroAPI calls"""
    async def wrapper(*args, **kwargs):
        return await retry_async(
            lambda: func(*args, **kwargs),
            config=RetryConfigs.AERO_API,
            context=f"aero_api_{func.__name__}"
        )
    return wrapper

def with_openai_retry(func):
    """Decorator for OpenAI calls"""
    async def wrapper(*args, **kwargs):
        return await retry_async(
            lambda: func(*args, **kwargs),
            config=RetryConfigs.OPENAI_API,
            context=f"openai_{func.__name__}"
        )
    return wrapper

def with_twilio_retry(func):
    """Decorator for Twilio calls"""
    async def wrapper(*args, **kwargs):
        return await retry_async(
            lambda: func(*args, **kwargs),
            config=RetryConfigs.TWILIO_API,
            context=f"twilio_{func.__name__}"
        )
    return wrapper 