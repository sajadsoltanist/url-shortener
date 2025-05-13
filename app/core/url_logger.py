"""URL access logging using Loguru's built-in async features."""

from loguru import logger
import sys
import os
from datetime import datetime

from app.core.config import settings

# Create a new logger instance specifically for URL access logs
url_access_logger = None

def setup_url_logging():
    """Configure the URL access logger with async processing."""
    global url_access_logger
    
    # Ensure log directory exists
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    
    # Create a separate logger instance for URL access logs
    url_access_logger = logger.bind(event_type="url_access")
    
    # Remove any existing handlers to avoid duplication
    logger.configure(handlers=[])
    
    # Add specific handlers for URL access logging
    logger.add(
        f"{settings.LOG_DIR}/url_access.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | IP:{extra[ip]} | Code:{extra[short_code]} | {message}",
        rotation="10 MB", 
        retention="7 days",
        enqueue=True,  # This enables Loguru's internal queue
        level="INFO",
        backtrace=False,
        diagnose=False,
        filter=lambda record: record["extra"].get("event_type") == "url_access"
    )
    
    # Add JSON format handler
    logger.add(
        f"{settings.LOG_DIR}/url_access.json",
        serialize=True,
        enqueue=True,
        level="INFO",
        filter=lambda record: record["extra"].get("event_type") == "url_access"
    )
    
    return url_access_logger

def log_url_access(short_code: str, ip_address: str, user_agent: str = ""):
    """
    Log a URL access event using Loguru's non-blocking logging.
    
    Args:
        short_code: The shortened URL code that was accessed
        ip_address: The client's IP address
        user_agent: Optional user agent string
    """
    if url_access_logger is None:
        setup_url_logging()
        
    # Use bound logger with contextual data
    url_access_logger.bind(
        ip=ip_address,
        short_code=short_code,
        user_agent=user_agent,
        timestamp=datetime.utcnow().isoformat()
    ).info(f"URL accessed: {short_code}") 