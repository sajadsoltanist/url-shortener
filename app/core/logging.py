"""
Core logging module.

This module configures the application logging with Loguru.
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings


class InterceptHandler(logging.Handler):
    """
    Intercept standard logging and redirect to loguru.
    
    This handler intercepts all standard library logging calls
    and redirects them to loguru's more powerful logging system.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Try to get corresponding Loguru level or use level number
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """
    Configure application logging using Loguru.
    
    This sets up Loguru with proper formatting, log levels, and handlers,
    and also intercepts standard library logging.
    """
    # Create logs directory if it doesn't exist
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    
    # Remove default handlers
    logger.remove()
    
    # Add stderr handler for development/debugging
    if settings.DEBUG:
        logger.add(
            sys.stderr,
            level=settings.LOG_LEVEL.upper(),  # Convert to uppercase to handle case-insensitivity
            format=settings.LOG_FORMAT,
            backtrace=True,
            diagnose=True,
        )
    
    # Add file handler with proper log rotation
    log_file_path = os.path.join(settings.LOG_DIR, settings.LOG_FILENAME)
    
    if settings.LOG_JSON:
        # Use built-in serialization instead of custom formatter
        logger.add(
            log_file_path,
            level=settings.LOG_LEVEL.upper(),
            serialize=True,  # This enables JSON serialization
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="gz",
        )
    else:
        # Text formatter
        logger.add(
            log_file_path,
            level=settings.LOG_LEVEL.upper(),
            format=settings.LOG_FORMAT,
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="gz",
        )
    
    # Register custom log level for request logs
    logger.level("REQUEST", no=25, color="<green>")
    
    # Intercept standard library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Modify existing loggers to use InterceptHandler
    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    
    # Set log levels for relevant libraries
    for log_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
        logging_logger = logging.getLogger(log_name)
        logging_logger.handlers = [InterceptHandler()]
    
    return logger 