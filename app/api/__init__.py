"""API package for the URL shortener application.

This package contains the API layer components including routes,
request/response schemas, and dependency providers.
"""

from app.api.routes import api_router

__all__ = ["api_router"]
