"""Decorators for the URL shortener application.

This module contains reusable decorators for common functionality
across the application.
"""

import functools
from fastapi import Request
from app.core.url_logger import log_url_access


def log_url_access_decorator():
    """URL access logging decorator that preserves route function signature.
    
    Returns:
        callable: Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(request: Request, short_code: str, *args, **kwargs):
            # Extract user information from request
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "")
            
            # Log the access using the non-blocking logger
            log_url_access(
                short_code=short_code,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Call the original function
            return await func(request=request, short_code=short_code, *args, **kwargs)
        return wrapper
    return decorator 