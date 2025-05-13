"""Main application module.

This module initializes the FastAPI application, includes routes,
and configures middleware and exception handlers.
"""

import os
import sys
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import asyncio
import traceback
import json

from app.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis import redis_manager
from app.core.url_logger import setup_url_logging
# Database resilience imports are disabled for now
# from app.db import initialize_database_connection, circuit_breaker

# Rate limiting imports
from app.core.rate_limit import (
    ResilientRateLimitBackend,
    setup_rate_limiting,
    initialize_rate_limiting,
    custom_on_blocked
)

# Scheduler import
from app.scheduler import SchedulerService
from app.scheduler.scheduler import scheduler_service

# Ensure logs directory exists
os.makedirs(settings.LOG_DIR, exist_ok=True)

# Setup logging
logger = setup_logging()

# We'll initialize URL logging later in the startup event to avoid affecting global logging

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store the rate limit backend for access in startup/shutdown events
rate_limit_backend = None

# Setup rate limiting
if settings.RATE_LIMIT_ENABLED:
    try:
        logger.info("Setting up rate limiting middleware")
        rate_limit_backend = setup_rate_limiting(app)
        logger.info("Rate limiting middleware added successfully")
    except Exception as e:
        logger.error("Error applying rate limit middleware", error=str(e))
        logger.error(f"Exception traceback: {traceback.format_exc()}")
        logger.warning("Rate limiting could not be enabled")
else:
    logger.info("Rate limiting is disabled in settings")

# Include API router
app.include_router(api_router)

# Add exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed information."""
    logger.error(f"Request validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to catch and log all unhandled exceptions."""
    error_id = f"error-{time.time()}"
    error_msg = f"Unhandled exception: {str(exc)}"
    error_location = f"{request.method} {request.url.path}"
    
    # Log detailed exception information with traceback
    logger.error(
        f"Unhandled exception in {error_location}",
        exc_info=True,
        error_id=error_id,
        url=str(request.url),
        method=request.method,
        path_params=request.path_params,
        query_params=dict(request.query_params),
        client_host=request.client.host if request.client else None
    )
    
    # Return a 500 response with error information
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error occurred",
            "error_id": error_id,
            "message": str(exc) if settings.DEBUG else "Internal server error"
        }
    )


# Circuit breaker status endpoint is disabled for now
# @app.get("/api/status/db-circuit-breaker")
# async def db_circuit_breaker_status():
#     """Get the current status of the database circuit breaker."""
#     return {
#         "circuit_breaker": "enabled" if settings.DB_CIRCUIT_BREAKER_ENABLED else "disabled",
#         "stats": circuit_breaker.get_stats()
#     }


# Add startup and shutdown event handlers
@app.on_event("startup")
async def startup_event():
    """Run startup tasks."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    # Initialize URL access logging
    from app.core.url_logger import setup_url_logging
    setup_url_logging()
    logger.info("URL access logging initialized")
    
    # Database connection retry is disabled for now
    # logger.info("Initializing database connection with retry")
    # db_connected = await initialize_database_connection()
    # if not db_connected:
    #     logger.critical("Failed to connect to database after multiple attempts")
    #     sys.exit(1)
    # else:
    #     logger.info("Database connection established successfully")
    
    # Initialize the rate limit backend if it exists
    global rate_limit_backend
    if rate_limit_backend is not None:
        logger.info("Initializing rate limit backend")
        await initialize_rate_limiting()
    
    # Log rate limit settings at debug level
    logger.debug(
        "Rate limit configuration", 
        enabled=settings.RATE_LIMIT_ENABLED,
        admin_ips=getattr(settings, "RATE_LIMIT_ADMIN_IPS", [])
    )
    
    # Initialize and start the scheduler
    try:
        logger.info("Initializing scheduler")
        scheduler_service.initialize()
        scheduler_service.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error("Error starting scheduler", error=str(e))
        logger.error(f"Exception traceback: {traceback.format_exc()}")
        logger.critical("Scheduler could not be started")

@app.on_event("shutdown")
async def shutdown_event():
    """Run cleanup tasks."""
    logger.info(f"Shutting down {settings.APP_NAME}")
    
    # Close rate limiting backend if it exists
    from app.core.rate_limit.middleware import close_rate_limiting
    await close_rate_limiting()
    
    # Shutdown the scheduler
    try:
        logger.info("Shutting down scheduler")
        scheduler_service.shutdown()
        logger.info("Scheduler shut down successfully")
    except Exception as e:
        logger.error("Error shutting down scheduler", error=str(e))
