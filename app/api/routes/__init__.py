"""Routes package initialization.

This module exports the route collection for the application.
"""

from fastapi import APIRouter

from app.api.routes import shortener, redirect, health
from app.core.config import settings

# Create root router
api_router = APIRouter()

# Include shortener routes with API prefix
api_router.include_router(
    shortener.router,
    prefix=settings.API_PREFIX
)

# Include health check routes with API prefix
api_router.include_router(
    health.router,
    prefix=settings.API_PREFIX
)

# Include redirect routes at the root path (no prefix)
# This makes short URLs available directly at /{short_code}
api_router.include_router(
    redirect.router
)

__all__ = ["api_router"] 