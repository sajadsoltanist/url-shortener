"""
Redis client management module.

This module provides a Redis client manager with connection pooling
and error handling for async Redis operations.
"""

import asyncio
from typing import Optional, Dict, Any, List
import time

import redis.asyncio as redis
from loguru import logger
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from app.core.config import settings


class RedisClientManager:
    """
    Async Redis client manager with connection pooling.
    
    Features:
    - Automatic connection pooling
    - Connection health checking
    - Reconnection with exponential backoff
    - Error handling and recovery
    """
    
    _instance: Optional["RedisClientManager"] = None
    _connection_pool: Optional[ConnectionPool] = None
    _client: Optional[redis.Redis] = None
    _is_connected: bool = False
    
    def __new__(cls):
        """Singleton pattern to ensure only one Redis client manager exists."""
        if cls._instance is None:
            cls._instance = super(RedisClientManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Initialize the Redis connection pool."""
        try:
            self._connection_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URI,
                max_connections=20,
                decode_responses=True
            )
            logger.debug(f"Redis connection pool created for {settings.REDIS_URI}")
        except Exception as e:
            logger.error(f"Failed to create Redis connection pool: {str(e)}")
            self._connection_pool = None
    
    @property
    def is_enabled(self) -> bool:
        """
        Check if Redis is enabled in the application.
        
        Returns:
            bool: True if Redis is configured and enabled
        """
        # Check if Redis URI is configured and not empty
        return bool(settings.REDIS_URI and settings.REDIS_URI != "redis://localhost:6379")
    
    async def get_client(self) -> redis.Redis:
        """
        Get a Redis client instance from the connection pool.
        
        Returns:
            redis.Redis: Redis client instance
        """
        if self._client is None:
            if self._connection_pool is None:
                self._initialize()
                
            if self._connection_pool:
                self._client = redis.Redis(connection_pool=self._connection_pool)
            else:
                raise ConnectionError("Redis connection pool is not available")
                
        return self._client
    
    async def ping(self) -> bool:
        """
        Test the Redis connection with a ping command.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            client = await self.get_client()
            result = await client.ping()
            self._is_connected = True
            return result
        except RedisError as e:
            logger.error(f"Redis ping failed: {str(e)}")
            self._is_connected = False
            return False
    
    async def is_connected(self) -> bool:
        """
        Check if Redis is connected.
        
        Returns:
            bool: Connection status
        """
        if not self._is_connected:
            return await self.ping()
        return self._is_connected
    
    async def reconnect(self, max_retries: int = 3, delay: float = 1.0) -> bool:
        """
        Attempt to reconnect to Redis with exponential backoff.
        
        Args:
            max_retries: Maximum number of reconnection attempts
            delay: Initial delay between attempts (seconds)
            
        Returns:
            bool: True if reconnection was successful
        """
        # Close existing client if any
        if self._client:
            await self._client.close()
            self._client = None
            
        # Create a new connection pool
        if self._connection_pool:
            self._connection_pool.disconnect()
            self._connection_pool = None
            
        self._initialize()
        
        # Try to reconnect with exponential backoff
        for attempt in range(max_retries):
            logger.debug(f"Redis reconnection attempt {attempt + 1}/{max_retries}")
            
            try:
                client = await self.get_client()
                if await client.ping():
                    self._is_connected = True
                    logger.info("Redis reconnection successful")
                    return True
            except RedisError as e:
                logger.warning(f"Redis reconnection failed (attempt {attempt + 1}): {str(e)}")
                
            # Exponential backoff with jitter
            backoff_time = delay * (2 ** attempt) * (0.9 + 0.2 * (time.time() % 1))
            await asyncio.sleep(backoff_time)
            
        self._is_connected = False
        logger.error(f"Redis reconnection failed after {max_retries} attempts")
        return False
    
    async def close(self) -> None:
        """Close the Redis client and connection pool."""
        if self._client:
            await self._client.close()
            self._client = None
            
        if self._connection_pool:
            self._connection_pool.disconnect()
            self._connection_pool = None
            
        self._is_connected = False
        logger.debug("Redis connections closed")


# Singleton instance
redis_manager = RedisClientManager() 