"""Database resilience patterns for high-availability environments.

This module implements resilience patterns for database connections:
1. Connection retry with exponential backoff
2. Circuit breaker for database operations

These patterns help make the application more robust in environments
where database connections may be unstable or temporarily unavailable.
"""

import asyncio
import logging
import random
import time
from asyncio import Lock
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar, Optional, Dict, Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text

from app.core.config import settings
from app.db.base import get_session

logger = logging.getLogger(__name__)

# Type variable for generic function return type
T = TypeVar("T")


# ----------------------- #
# Connection Retry Logic  #
# ----------------------- #

async def initialize_database_connection() -> bool:
    """Initialize database connection with retry and exponential backoff.
    
    Attempts to establish a database connection during application startup.
    If the connection fails, retries with exponential backoff.
    
    Returns:
        bool: True if connection was successful, False otherwise
    """
    max_attempts = settings.DB_CONNECT_RETRY_ATTEMPTS
    initial_delay = settings.DB_CONNECT_RETRY_INITIAL_DELAY
    max_delay = settings.DB_CONNECT_RETRY_MAX_DELAY
    jitter_factor = settings.DB_CONNECT_RETRY_JITTER
    
    logger.info(f"Initializing database connection (max attempts: {max_attempts})")
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Try to establish a connection by running a simple query
            async with get_session() as session:
                await session.execute(text("SELECT 1"))
                
            logger.info(f"Database connection established successfully on attempt {attempt}")
            return True
            
        except Exception as e:
            # Calculate backoff time with jitter
            delay = min(initial_delay * (2 ** (attempt - 1)), max_delay)
            jitter = delay * jitter_factor
            backoff_time = delay + random.uniform(-jitter, jitter) if jitter > 0 else delay
            
            if attempt < max_attempts:
                logger.warning(
                    f"Database connection attempt {attempt}/{max_attempts} failed: {str(e)}. "
                    f"Retrying in {backoff_time:.2f} seconds..."
                )
                await asyncio.sleep(backoff_time)
            else:
                logger.error(
                    f"Failed to connect to database after {max_attempts} attempts. "
                    f"Last error: {str(e)}"
                )
                return False
    
    return False


# ----------------------- #
# Circuit Breaker Pattern #
# ----------------------- #

class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation, requests go through
    OPEN = "open"           # Failure threshold reached, requests fail fast
    HALF_OPEN = "half-open" # Recovery period, limited requests to test system


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class DatabaseCircuitBreaker:
    """Circuit breaker for database operations.
    
    Implements the circuit breaker pattern to prevent cascading failures
    when the database is experiencing issues. In the OPEN state, requests
    fail fast without attempting to reach the database.
    """
    _instance = None
    
    def __new__(cls):
        """Singleton pattern to ensure only one circuit breaker exists."""
        if cls._instance is None:
            cls._instance = super(DatabaseCircuitBreaker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the circuit breaker if not already initialized."""
        if self._initialized:
            return
            
        # Circuit state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0
        
        # Configuration
        self._failure_threshold = settings.DB_CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self._recovery_time = settings.DB_CIRCUIT_BREAKER_RECOVERY_TIME
        self._success_threshold = settings.DB_CIRCUIT_BREAKER_SUCCESS_THRESHOLD
        
        # Lock for thread safety in async environment
        self._lock = Lock()
        
        # Metadata for monitoring
        self._total_failures = 0
        self._total_successes = 0
        self._total_bypassed = 0
        self._circuit_trip_count = 0
        
        logger.info(
            f"Database circuit breaker initialized (failure_threshold={self._failure_threshold}, "
            f"recovery_time={self._recovery_time}s, success_threshold={self._success_threshold})"
        )
        
        self._initialized = True
    
    async def execute(self, operation: Callable[..., T], *args, **kwargs) -> T:
        """Execute an operation with circuit breaker protection.
        
        Args:
            operation: Async callable to execute
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            The result of the operation
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by the operation
        """
        await self._check_state()
        
        try:
            result = await operation(*args, **kwargs)
            await self._handle_success()
            return result
            
        except Exception as e:
            await self._handle_failure(e)
            raise
    
    async def _check_state(self):
        """Check and potentially update the circuit breaker state.
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery time has elapsed to transition to half-open
                if time.time() - self._last_failure_time > self._recovery_time:
                    logger.info("Circuit breaker transitioning from OPEN to HALF-OPEN state")
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    self._total_bypassed += 1
                    recovery_time_left = self._recovery_time - (time.time() - self._last_failure_time)
                    raise CircuitBreakerError(
                        f"Circuit breaker is open. "
                        f"Automatic retry in {recovery_time_left:.1f} seconds."
                    )
    
    async def _handle_success(self):
        """Handle successful operation, potentially closing the circuit."""
        if self._state == CircuitState.HALF_OPEN:
            async with self._lock:
                self._success_count += 1
                self._total_successes += 1
                
                if self._success_count >= self._success_threshold:
                    logger.info(
                        f"Circuit breaker transitioning from HALF-OPEN to CLOSED state "
                        f"after {self._success_count} successful operations"
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
        
        elif self._state == CircuitState.CLOSED:
            self._total_successes += 1
    
    async def _handle_failure(self, exception):
        """Handle operation failure, potentially opening the circuit."""
        async with self._lock:
            self._last_failure_time = time.time()
            self._total_failures += 1
            
            if self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    logger.warning(
                        f"Circuit breaker transitioning from CLOSED to OPEN state "
                        f"after {self._failure_count} failures. Last error: {str(exception)}"
                    )
                    self._state = CircuitState.OPEN
                    self._circuit_trip_count += 1
            
            elif self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker transitioning from HALF-OPEN back to OPEN state "
                    f"due to failure: {str(exception)}"
                )
                self._state = CircuitState.OPEN
                self._circuit_trip_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics.
        
        Returns:
            Dict containing circuit breaker stats
        """
        return {
            "state": self._state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self._failure_threshold,
            "success_threshold": self._success_threshold,
            "recovery_time": self._recovery_time,
            "last_failure_time": self._last_failure_time,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_bypassed": self._total_bypassed,
            "circuit_trip_count": self._circuit_trip_count,
        }
    
    def reset(self):
        """Reset the circuit breaker to closed state."""
        logger.warning("Circuit breaker manually reset to CLOSED state")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0


# Singleton instance
circuit_breaker = DatabaseCircuitBreaker()


async def get_db_with_circuit_breaker() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions with circuit breaker protection.
    
    This should be used in routes that need circuit breaker protection.
    
    Yields:
        AsyncSession: A SQLAlchemy async session object
        
    Raises:
        CircuitBreakerError: If circuit breaker is open
    """
    # First check if circuit is open before even attempting to get a session
    await circuit_breaker._check_state()
    
    async with get_session() as session:
        try:
            # Test the connection
            await circuit_breaker.execute(session.execute, text("SELECT 1"))
            
            try:
                yield session
            except SQLAlchemyError as e:
                logger.exception("Database error occurred")
                await session.rollback()
                # Record failure in circuit breaker
                await circuit_breaker._handle_failure(e)
                raise
            except Exception as e:
                logger.exception("Unexpected error during database session")
                await session.rollback()
                raise
                
        except Exception as e:
            # This will handle connection errors and circuit breaker errors
            # but let them propagate up to the caller
            raise


def db_circuit_breaker(func):
    """Decorator to wrap async database operations with circuit breaker.
    
    Example:
        ```python
        @db_circuit_breaker
        async def get_user(user_id: int) -> User:
            async with get_session() as session:
                return await session.get(User, user_id)
        ```
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await circuit_breaker.execute(func, *args, **kwargs)
    return wrapper 