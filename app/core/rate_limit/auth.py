"""Authentication functions for rate limiting identification."""

from typing import Tuple
from ratelimit.types import Scope, Receive, Send, ASGIApp
from fastapi.responses import JSONResponse
import ipaddress
import json
from loguru import logger

async def simple_auth(scope: Scope) -> Tuple[str, str]:
    """Identify users by IP address for rate limiting.
    
    Args:
        scope: ASGI connection scope
        
    Returns:
        Tuple of (user_id, group) where user_id is client IP
    """
    # Extract client IP address
    client_host = None
    for header in scope.get("headers", []):
        name, value = header
        if name == b"x-forwarded-for":
            # Get the first IP in X-Forwarded-For
            forwarded_for = value.decode("latin1").split(",")[0].strip()
            try:
                # Validate IP address
                ipaddress.ip_address(forwarded_for)
                client_host = forwarded_for
                break
            except ValueError:
                pass
    
    # If X-Forwarded-For header not found or invalid, use the client address
    if client_host is None:
        client_host = scope.get("client")[0] if scope.get("client") else "unknown"
    
    # Determine group based on path
    path = scope.get("path", "")
    if path.startswith("/api/"):
        group = "api"
    else:
        group = "public"
        
    return client_host, group

def custom_on_blocked(retry_after: int) -> ASGIApp:
    """
    Custom handler for blocked requests due to rate limiting.
    Returns a JSON response with an error message and retry-after information.
    
    Args:
        retry_after: Time in seconds to wait before retrying
        
    Returns:
        ASGI application that handles blocked requests
    """
    async def app_block_handler(scope: Scope, receive: Receive, send: Send) -> None:
        # Extract client info for logging
        client_ip = None
        for header in scope.get("headers", []):
            name, value = header
            if name == b"x-forwarded-for":
                client_ip = value.decode("latin1").split(",")[0].strip()
                break
                
        if client_ip is None:
            client_ip = scope.get("client")[0] if scope.get("client") else "unknown"
            
        path = scope.get("path", "")
        method = scope.get("method", "")
        
        # Log the rate limit block with structured data
        logger.warning(
            "Rate limit exceeded", 
            ip=client_ip, 
            path=path, 
            method=method, 
            retry_after=retry_after
        )
        
        # Prepare JSON response
        response = JSONResponse(
            status_code=429,
            content={
                "error": "Too many requests",
                "detail": f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                "retry_after": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )
        
        # Send HTTP response
        await response(scope, receive, send)
        
    return app_block_handler 