"""
Non-blocking logging middleware for FastAPI using Redis and Loguru.

This middleware captures HTTP request metrics without impacting request latency
by using Redis as a message queue and batch processing with Loguru.
"""

import asyncio
import json
import time
import uuid
from contextvars import ContextVar
from typing import Dict, Optional, Any, List, Callable, Union, Tuple

from fastapi import Request, Response
from loguru import logger
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Scope, Receive, Send, Message

from app.core.config import settings
from app.core.redis import redis_manager

# Context variable to store request ID across async context
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Background tasks
_bg_tasks: Dict[str, asyncio.Task] = {}

# In-memory fallback queue for when Redis is not available
_fallback_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Non-blocking logging middleware using Redis as a message queue.
    
    Features:
    - Zero impact on request latency
    - Completely non-blocking log publishing
    - Redis-backed for durability
    - Automatic fallback to local memory when Redis is unavailable
    - Rich contextual logging with request details
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the middleware and ensure background tasks are started."""
        super().__init__(app)
        
        # Start background processor tasks if not already running
        self._ensure_background_tasks()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and log metrics in a completely non-blocking manner.
        """
        # Generate unique request ID and set it in context
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        
        # Start timing the request
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Add request ID to response headers for traceability
        response.headers["X-Request-ID"] = request_id
        
        # Calculate request processing time
        process_time = time.time() - start_time
        
        # Get client IP with forwarded headers consideration
        client_ip = request.client.host if request.client else "unknown"
        if "X-Forwarded-For" in request.headers:
            forwarded_ips = request.headers["X-Forwarded-For"].split(",")
            if forwarded_ips:
                client_ip = forwarded_ips[0].strip()
        
        # Create the log record with all required information
        log_record = {
            "timestamp": time.time(),
            "request_id": request_id,
            "client_ip": client_ip,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time_ms": round(process_time * 1000, 2)
        }
        
        # Add query params if present
        if request.query_params:
            log_record["query_params"] = dict(request.query_params)
        
        # Asynchronously publish the log record without blocking
        asyncio.create_task(self._publish_log_record(log_record))
        
        return response
    
    async def _publish_log_record(self, log_record: Dict[str, Any]) -> None:
        """
        Non-blocking function to publish log record to Redis.
        
        Falls back to local queue if Redis is unavailable.
        """
        try:
            if not settings.REDIS_LOGGING_ENABLED:
                # If Redis logging is disabled, log directly to Loguru
                logger.log("REQUEST", "{method} {path} {status_code} {process_time_ms}ms", **log_record)
                return
                
            # Try to publish to Redis queue first
            redis_client = await redis_manager.get_client()
            await redis_client.lpush(
                settings.REDIS_LOGGING_QUEUE,
                json.dumps(log_record)
            )
        except (RedisError, ConnectionError) as e:
            # If Redis fails, use fallback queue
            if settings.REDIS_LOGGING_FALLBACK_LOCAL:
                try:
                    _fallback_queue.put_nowait(log_record)
                except asyncio.QueueFull:
                    # Fallback queue is full, log the error but don't block request
                    logger.warning(f"Fallback log queue full, dropping log: {log_record['request_id']}")
            else:
                # Log the error but continue processing the request
                logger.error(f"Failed to publish log record to Redis: {str(e)}")
    
    def _ensure_background_tasks(self) -> None:
        """Ensure all required background tasks are running."""
        # Log consumer task
        if "log_consumer" not in _bg_tasks or _bg_tasks["log_consumer"].done():
            _bg_tasks["log_consumer"] = asyncio.create_task(process_logs_from_redis())
        
        # Fallback processor task
        if "fallback_processor" not in _bg_tasks or _bg_tasks["fallback_processor"].done():
            _bg_tasks["fallback_processor"] = asyncio.create_task(process_fallback_queue())
            
        # Redis health check task
        if "redis_health" not in _bg_tasks or _bg_tasks["redis_health"].done():
            _bg_tasks["redis_health"] = asyncio.create_task(monitor_redis_health())


async def process_logs_from_redis() -> None:
    """
    Background task that processes logs from Redis.
    
    Features:
    - Batch processing for efficiency
    - Error handling with retry
    - Periodic flushing based on time or batch size
    """
    batch_size = settings.REDIS_LOGGING_BATCH_SIZE
    flush_interval = settings.REDIS_LOGGING_FLUSH_INTERVAL
    last_flush_time = time.time()
    log_batch: List[Dict[str, Any]] = []
    
    logger.info(f"Starting Redis log consumer (batch size: {batch_size}, flush interval: {flush_interval}s)")
    
    try:
        while True:
            try:
                # Check if Redis is available
                if not await redis_manager.is_connected():
                    await asyncio.sleep(1.0)
                    continue
                
                # Get Redis client
                redis_client = await redis_manager.get_client()
                
                # Determine how many logs to fetch based on batch size
                remaining_capacity = batch_size - len(log_batch)
                
                # Pop multiple items from Redis at once (more efficient)
                if remaining_capacity > 0:
                    # Use RPOP to get logs in FIFO order
                    raw_logs = await redis_client.rpop(
                        settings.REDIS_LOGGING_QUEUE, 
                        count=remaining_capacity
                    )
                    
                    if raw_logs:
                        # Parse logs and add to batch
                        for raw_log in raw_logs:
                            try:
                                log_record = json.loads(raw_log)
                                log_batch.append(log_record)
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse log record: {raw_log}")
                
                # Check if we should flush based on batch size or time
                time_since_flush = time.time() - last_flush_time
                should_flush = (len(log_batch) >= batch_size) or (time_since_flush >= flush_interval and log_batch)
                
                if should_flush:
                    await flush_log_batch(log_batch)
                    log_batch = []
                    last_flush_time = time.time()
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.01)
                
            except RedisError as e:
                logger.error(f"Redis error in log consumer: {str(e)}")
                # Flush any pending logs 
                if log_batch:
                    await flush_log_batch(log_batch)
                    log_batch = []
                
                # Wait before trying again
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"Error in Redis log consumer: {str(e)}")
                # Don't lose logs in case of error
                if log_batch:
                    await flush_log_batch(log_batch)
                    log_batch = []
                
                # Wait before trying again
                await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        # Flush any remaining logs
        if log_batch:
            await flush_log_batch(log_batch)
        logger.info("Redis log consumer stopped")
        raise


async def process_fallback_queue() -> None:
    """
    Process logs from the fallback queue when Redis is unavailable.
    
    This provides graceful degradation when Redis is down.
    """
    batch_size = settings.REDIS_LOGGING_BATCH_SIZE
    flush_interval = settings.REDIS_LOGGING_FLUSH_INTERVAL
    last_flush_time = time.time()
    log_batch: List[Dict[str, Any]] = []
    
    logger.info(f"Starting fallback log processor")
    
    try:
        while True:
            try:
                # Try to get logs from the fallback queue
                try:
                    # Determine timeout based on remaining flush interval
                    wait_time = max(0.01, flush_interval - (time.time() - last_flush_time))
                    log_record = await asyncio.wait_for(_fallback_queue.get(), timeout=wait_time)
                    log_batch.append(log_record)
                    _fallback_queue.task_done()
                except asyncio.TimeoutError:
                    # This is expected when waiting for the queue
                    pass
                
                # Check if we should flush based on batch size or time
                time_since_flush = time.time() - last_flush_time
                should_flush = (len(log_batch) >= batch_size) or (time_since_flush >= flush_interval and log_batch)
                
                if should_flush:
                    await flush_log_batch(log_batch)
                    log_batch = []
                    last_flush_time = time.time()
                
                # Try to move logs back to Redis if it's available
                if not _fallback_queue.empty() and await redis_manager.is_connected():
                    await _migrate_fallback_to_redis()
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in fallback log processor: {str(e)}")
                # Don't lose logs in case of error
                if log_batch:
                    await flush_log_batch(log_batch)
                    log_batch = []
                
                # Wait before trying again
                await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        # Flush any remaining logs
        if log_batch:
            await flush_log_batch(log_batch)
        logger.info("Fallback log processor stopped")
        raise


async def _migrate_fallback_to_redis() -> None:
    """
    Migrate logs from the fallback queue back to Redis.
    
    This is called when Redis becomes available again.
    """
    try:
        redis_client = await redis_manager.get_client()
        batch_size = min(_fallback_queue.qsize(), 100)  # Process in batches of 100 max
        
        if batch_size > 0:
            logger.info(f"Migrating {batch_size} logs from fallback queue to Redis")
            
            # Create a pipeline for efficiency
            pipeline = redis_client.pipeline()
            
            # Process up to batch_size items
            for _ in range(batch_size):
                try:
                    log_record = _fallback_queue.get_nowait()
                    pipeline.lpush(settings.REDIS_LOGGING_QUEUE, json.dumps(log_record))
                    _fallback_queue.task_done()
                except asyncio.QueueEmpty:
                    break
            
            # Execute the pipeline
            await pipeline.execute()
            
            logger.info(f"Successfully migrated logs to Redis")
    except (RedisError, ConnectionError) as e:
        logger.error(f"Failed to migrate logs to Redis: {str(e)}")


async def monitor_redis_health() -> None:
    """
    Periodically check Redis health and attempt reconnection if needed.
    """
    logger.info("Starting Redis health monitor")
    
    try:
        while True:
            try:
                if not await redis_manager.is_connected():
                    logger.warning("Redis is disconnected, attempting to reconnect")
                    await redis_manager.reconnect(
                        max_retries=settings.REDIS_LOGGING_MAX_RETRIES,
                        delay=settings.REDIS_LOGGING_RECONNECT_DELAY
                    )
                
                # Check every 30 seconds
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in Redis health monitor: {str(e)}")
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info("Redis health monitor stopped")
        raise


async def flush_log_batch(batch: List[Dict[str, Any]]) -> None:
    """
    Flush a batch of logs to Loguru for file output.
    
    Args:
        batch: List of log records to flush
    """
    try:
        # Process each log record
        for record in batch:
            # Extract request information
            method = record.get("method", "UNKNOWN")
            path = record.get("path", "UNKNOWN")
            status_code = record.get("status_code", 0)
            process_time_ms = record.get("process_time_ms", 0)
            client_ip = record.get("client_ip", "unknown")
            request_id = record.get("request_id", "unknown")
            
            # Log to Loguru with REQUEST level
            logger.log(
                "REQUEST",
                "{method} {path} {status_code} {process_time_ms}ms {client_ip} {request_id}",
                method=method,
                path=path,
                status_code=status_code,
                process_time_ms=process_time_ms,
                client_ip=client_ip,
                request_id=request_id,
            )
    except Exception as e:
        # Ensure logging never breaks the application
        logger.error(f"Error flushing log batch: {str(e)}")


def add_logging_middleware(app) -> None:
    """
    Add the non-blocking logging middleware to the FastAPI application.
    
    This also registers startup and shutdown handlers.
    """
    # Add middleware
    app.add_middleware(LoggingMiddleware)
    
    # Register startup handler
    @app.on_event("startup")
    async def startup_logging():
        logger.info("Initializing Redis logging middleware")
        # Check Redis connection
        is_connected = await redis_manager.ping()
        if is_connected:
            logger.info("Successfully connected to Redis")
        else:
            logger.warning("Failed to connect to Redis, will use fallback logging")
    
    # Register shutdown handler to ensure all logs are processed
    @app.on_event("shutdown")
    async def shutdown_logging():
        logger.info("Shutting down logging middleware")
        
        # Cancel all background tasks
        for task_name, task in _bg_tasks.items():
            if not task.done():
                logger.debug(f"Cancelling {task_name} task")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Wait for fallback queue to be processed
        if not _fallback_queue.empty():
            logger.info(f"Processing {_fallback_queue.qsize()} remaining logs in fallback queue")
            await _fallback_queue.join()
        
        # Close Redis connections
        await redis_manager.close()
