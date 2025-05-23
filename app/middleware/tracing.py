"""Custom tracing middleware for URL Shortener application."""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.responses import Response

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from app.core.telemetry import get_tracer, get_meter

# Get tracer and meter from OpenTelemetry
tracer = get_tracer("url_shortener.middleware")
meter = get_meter("url_shortener.middleware")

# Create metrics for middleware
request_counter = meter.create_counter(
    name="url_shortener.http.requests",
    description="Number of HTTP requests",
    unit="1",
)

request_duration = meter.create_histogram(
    name="url_shortener.http.duration",
    description="Duration of HTTP requests",
    unit="ms",
)


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware that adds custom spans and metrics for each request."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware."""
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and add tracing/metrics."""
        # Record start time
        start_time = time.time()
        
        # Extract path for use in span and metrics
        path = request.url.path
        method = request.method
        
        # Create attributes for span and metrics
        attributes = {
            "http.method": method,
            "http.path": path,
            "http.flavor": request.scope.get("http_version", ""),
            "http.host": request.headers.get("host", ""),
            "http.user_agent": request.headers.get("user-agent", ""),
        }
        # Add custom span for the request processing
        with tracer.start_as_current_span(
            f"{method} {path}",
            attributes=attributes,
            kind=SpanKind.SERVER,
        ):
            # Process the request through the next handler
            response = await call_next(request)
            
            # Add status code to attributes
            attributes["http.status_code"] = response.status_code
            
            # Record metrics
            duration_ms = (time.time() - start_time) * 1000
            request_counter.add(1, attributes)
            request_duration.record(duration_ms, attributes)
            
            return response 