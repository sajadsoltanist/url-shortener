"""FastAPI rate limiting middleware setup."""

from fastapi import FastAPI
from ratelimit import RateLimitMiddleware, Rule
from loguru import logger

from app.core.config import settings
from app.core.rate_limit.backends import ResilientRateLimitBackend
from app.core.rate_limit.auth import simple_auth, custom_on_blocked

# Global variable to store the rate limit backend for access during shutdown
rate_limit_backend = None

def setup_rate_limiting(app: FastAPI) -> ResilientRateLimitBackend:
    """Configure rate limiting middleware with Redis backend.
    
    Args:
        app: FastAPI application instance
        
    Returns:
        ResilientRateLimitBackend for shutdown handling
    """
    global rate_limit_backend
    
    # Create resilient backend that can handle Redis outages
    backend = ResilientRateLimitBackend(settings.REDIS_URI)
    rate_limit_backend = backend
    
    # Define rate limit rules
    rate_limit_config = {
        # API endpoints: 1 request per second per IP
        r"^/api/": [
            Rule(second=1, group="api"),  # 1 request per second for API endpoints
            Rule(group="admin")  # No limits for admin group
        ],
        # Public endpoints: 5 requests per minute per IP
        r"^/": [
            Rule(minute=5, group="public"),  # 5 requests per minute for public endpoints
            Rule(group="admin")  # No limits for admin group
        ]
    }
    
    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        authenticate=simple_auth,
        backend=backend,
        config=rate_limit_config
    )
    
    logger.info("Rate limiting middleware added with Redis backend")
    
    return backend

async def initialize_rate_limiting() -> None:
    """Initialize rate limiting backend during application startup."""
    global rate_limit_backend
    if rate_limit_backend:
        await rate_limit_backend.initialize()
        logger.info("Rate limiting backend initialized")

async def close_rate_limiting() -> None:
    """Close rate limiting backend during application shutdown."""
    global rate_limit_backend
    if rate_limit_backend:
        await rate_limit_backend.close()
        logger.info("Rate limiting backend closed") 