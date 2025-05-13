"""Rate limiting backends with Redis failover to memory."""

import asyncio
import time
from typing import Callable, Awaitable, Any

from loguru import logger
from redis.asyncio import StrictRedis
from redis.exceptions import RedisError, ConnectionError
from ratelimit.backends.base import BaseBackend
from ratelimit.backends.simple import MemoryBackend
from ratelimit.backends.redis import RedisBackend

from app.core.config import settings

# Store the Redis client in a global variable for shutdown access
redis_rate_limit_client = None

class ResilientRateLimitBackend(BaseBackend):
    """Rate limit backend with Redis and memory fallback."""
    def __init__(self, redis_uri):
        self.redis_uri = redis_uri
        self.redis_client = None
        self.redis_backend = None
        self.memory_backend = MemoryBackend()
        self.using_redis = False
        self.last_redis_check = 0
        # Load configuration from settings instead of hardcoding
        self.redis_check_interval = settings.RATE_LIMIT_REDIS_CHECK_INTERVAL
        self.redis_errors = 0
        self.max_redis_errors = settings.RATE_LIMIT_REDIS_MAX_ERRORS
        # Lock only used for backend switching and state changes
        self._state_lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize Redis connection or fall back to memory.
        
        Returns:
            bool: True if Redis connection successful
        """
        # Acquire lock for state change
        async with self._state_lock:
            try:
                logger.info("Connecting to Redis rate limiting backend", uri=self.redis_uri)
                self.redis_client = StrictRedis.from_url(self.redis_uri)
                # Test connection
                await self.redis_client.ping()
                self.redis_backend = RedisBackend(self.redis_client)
                self.using_redis = True
                self.redis_errors = 0
                logger.info("Redis rate limiting backend initialized successfully")
                # Set global client for shutdown
                global redis_rate_limit_client
                redis_rate_limit_client = self.redis_client
                return True
            except (RedisError, ConnectionError) as e:
                logger.warning("Redis connection failed, using memory backend", error=str(e))
                self.redis_client = None
                self.redis_backend = None
                self.using_redis = False
                # Ensure memory backend is initialized
                if not hasattr(self, 'memory_backend') or self.memory_backend is None:
                    self.memory_backend = MemoryBackend()
                return False
    
    async def check_redis_health(self):
        """Check Redis availability and switch backends if needed.
        
        Returns:
            bool: True if using Redis backend
        """
        # Skip if we checked recently - no lock needed here as this is just a read of immutable data
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_redis_check < self.redis_check_interval:
            return self.using_redis
        
        # Only acquire lock when we're actually going to check Redis health and potentially switch backends
        async with self._state_lock:
            # Check again after acquiring lock in case another task already did the check
            if current_time - self.last_redis_check < self.redis_check_interval:
                return self.using_redis
                
            self.last_redis_check = current_time
            logger.debug("Checking Redis health", current_status="using_redis" if self.using_redis else "using_memory")
            
            # If already using Redis, verify it's still available
            if self.using_redis and self.redis_client is not None:
                try:
                    await self.redis_client.ping()
                    logger.debug("Redis connection verified OK")
                    return True
                except (RedisError, ConnectionError) as e:
                    logger.warning("Redis connection lost, switching to memory backend", error=str(e))
                    self.using_redis = False
                    return False
                    
            # Already using memory, try to reconnect to Redis
            elif not self.using_redis:
                try:
                    # Try to reconnect
                    logger.info("Attempting to reconnect to Redis")
                    if self.redis_client is None:
                        # Full initialization needed
                        result = await self.initialize()
                        if result:
                            logger.info("Redis reconnected and backend initialized")
                        return result
                    else:
                        # Just verify connection
                        await self.redis_client.ping()
                        # Create Redis backend if needed
                        if self.redis_backend is None:
                            self.redis_backend = RedisBackend(self.redis_client)
                        self.using_redis = True
                        self.redis_errors = 0
                        logger.info("Reconnected to Redis, switching back to Redis backend")
                        return True
                except (RedisError, ConnectionError) as e:
                    logger.warning("Redis still unavailable", error=str(e))
                    self.using_redis = False
                    return False
                    
            return self.using_redis
    
    async def _handle_redis_error(self, e):
        """Handle Redis error and switch to memory if threshold exceeded."""
        # Only lock when we're changing state
        async with self._state_lock:
            self.redis_errors += 1
            if self.redis_errors >= self.max_redis_errors:
                logger.warning(
                    "Redis error threshold reached, switching to memory backend",
                    errors=self.redis_errors,
                    max_errors=self.max_redis_errors
                )
                self.using_redis = False
            else:
                logger.warning(
                    "Redis operation failed",
                    error=str(e),
                    errors=f"{self.redis_errors}/{self.max_redis_errors}"
                )
    
    async def _with_fallback(self, redis_func, memory_func, *args, **kwargs):
        """Execute function with Redis, falling back to memory on failure."""
        # Check Redis health periodically - this internally uses locking only when needed
        await self.check_redis_health()
        
        # Read current state without locking
        current_using_redis = self.using_redis and self.redis_backend is not None
        
        # Only log backend changes, not every operation
        if current_using_redis:
            try:
                # Use Redis backend without locking
                return await redis_func(*args, **kwargs)
            except (RedisError, ConnectionError) as e:
                # Redis failed, log and use memory backend
                await self._handle_redis_error(e)
                # Immediately switch to memory for this request
                logger.warning("Switching to memory backend for this request due to Redis error", error=str(e))
                return await memory_func(*args, **kwargs)
        else:
            # Use memory backend without locking
            return await memory_func(*args, **kwargs)
    
    async def is_allowed(self, rule, user, group):
        """Check if request is allowed by rate limits."""
        # No lock needed for regular operations, only for backend switching
        result = await self._with_fallback(
            lambda: self.redis_backend.is_allowed(rule, user, group),
            lambda: self.memory_backend.is_allowed(rule, user, group)
        )
        
        # Only log when a request is blocked, not for every check
        if not result:
            logger.info(
                "Rate limit exceeded", 
                user=user, 
                group=group, 
                backend="redis" if self.using_redis else "memory"
            )
            
        return result
    
    async def is_blocking(self, user):
        """Check if the user is blocked."""
        # No lock needed for regular operations
        return await self._with_fallback(
            lambda: self.redis_backend.is_blocking(user),
            lambda: self.memory_backend.is_blocking(user)
        )
    
    async def retry_after(self, rule, user, group):
        """Get retry-after time in seconds."""
        # No lock needed for regular operations
        result = await self._with_fallback(
            lambda: self.redis_backend.retry_after(rule, user, group),
            lambda: self.memory_backend.retry_after(rule, user, group)
        )
        
        # Only log significant retry periods
        if result > 5:  # Only log if retry is more than 5 seconds
            logger.info(
                "Rate limit retry period", 
                user=user, 
                retry_seconds=result,
                backend="redis" if self.using_redis else "memory"
            )
            
        return result
    
    async def fallback_to_memory(self):
        """Explicitly switch to memory backend."""
        # Lock for state change
        async with self._state_lock:
            logger.info("Explicitly switching to memory backend")
            self.redis_client = None
            self.redis_backend = None
            self.using_redis = False
            
            # Ensure memory backend is initialized
            if not hasattr(self, 'memory_backend') or self.memory_backend is None:
                self.memory_backend = MemoryBackend()
            
            logger.info("Memory backend ready")
            return False
    
    async def close(self):
        """Close Redis and memory backends."""
        # Lock for closing resources
        async with self._state_lock:
            if self.redis_client:
                try:
                    await self.redis_client.close()
                    logger.info("Redis connection closed")
                except Exception as e:
                    logger.error("Error closing Redis connection", error=str(e))
            
            # Close memory backend as well
            try:
                await self.memory_backend.close()
            except Exception as e:
                logger.debug("Error closing memory backend", error=str(e)) 