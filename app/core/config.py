"""Application configuration module.

This module contains settings for the URL shortener application,
loaded from environment variables with appropriate defaults.
"""

from __future__ import annotations

import os
import string
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pathlib import Path
import logging

from pydantic import Field, field_validator, computed_field, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

# Set up basic logger for config module
logger = logging.getLogger(__name__)

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings loaded from environment variables with defaults.
    
    Settings are loaded from environment variables, with fallback to
    values in .env file if present, and finally to the default values
    specified here.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Environment setting
    ENVIRONMENT: EnvironmentType = EnvironmentType.DEVELOPMENT
    
    # App Information
    APP_NAME: str = "URL Shortener"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "A clean architecture URL shortening service"
    
    # API Configuration
    BASE_URL: str = "http://localhost:8000"  # Used for generating short URLs
    API_PREFIX: str = "/api"
    DEBUG: bool = False
    
    # CORS settings
    CORS_ORIGINS: Union[List[str], str] = ["*"]  # Allow all origins by default
    
    # URL Shortening Configuration
    URL_CODE_LENGTH: int = 6  # Default length for short codes
    URL_CODE_CHARS: str = string.ascii_letters + string.digits  # Characters used for short codes
    URL_CUSTOM_CODE_MAX_LENGTH: int = 20  # Maximum length for custom codes
    
    # Default URL expiration (in days)
    DEFAULT_EXPIRATION_DAYS: Optional[int] = None  # None means never expire
    
    # Rate limiting settings (requests per minute per IP)
    RATE_LIMIT_SHORTEN: int = 10  # Rate limit for URL shortening
    RATE_LIMIT_REDIRECT: int = 60  # Rate limit for redirects
      # PostgreSQL settings
    POSTGRES_SERVER: str = Field(default="localhost", env="DATABASE_HOST")
    POSTGRES_PORT: int = Field(default=5432, env="DATABASE_PORT")
    POSTGRES_USER: str = Field(default="postgres", env="DATABASE_USER")
    POSTGRES_PASSWORD: str = Field(default="postgres", env="DATABASE_PASSWORD")
    POSTGRES_DB: str = Field(default="url_shortener", env="DATABASE_NAME")
    
    # PostgreSQL pool settings
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_POOL_MAX_OVERFLOW: int = 10
    POSTGRES_POOL_TIMEOUT: int = 30
    POSTGRES_POOL_RECYCLE: int = 300
    DB_ECHO: bool = False
    
    # Database connection resilience settings
    DB_CONNECT_RETRY_ATTEMPTS: int = 5  # Max number of connection attempts during startup
    DB_CONNECT_RETRY_INITIAL_DELAY: float = 1.0  # Initial delay in seconds
    DB_CONNECT_RETRY_MAX_DELAY: float = 30.0  # Maximum delay in seconds
    DB_CONNECT_RETRY_JITTER: float = 0.1  # Jitter factor (0.0-1.0) to add randomness to backoff
    
    # Database circuit breaker settings
    DB_CIRCUIT_BREAKER_ENABLED: bool = True
    DB_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5  # Failures before circuit opens
    DB_CIRCUIT_BREAKER_RECOVERY_TIME: float = 30.0  # Seconds before trying half-open state
    DB_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 3  # Successes in half-open to close circuit
    DB_CIRCUIT_BREAKER_TIMEOUT: float = 3.0  # Seconds before timing out a database operation
      # Redis settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    # Cache settings
    CACHE_TIMEOUT: int = 3600
    CACHE_ENABLED: bool = True
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 1  # Default requests per minute
    RATE_LIMIT_STRATEGY: str = "moving-window"
    RATE_LIMIT_ADMIN_IPS: Union[List[str], str] = []  # IPs that bypass rate limits
    RATE_LIMIT_ADMIN_API_KEYS: Union[List[str], str] = []  # API keys that bypass rate limits
    
    # Rate limiting backend resilience configuration
    RATE_LIMIT_REDIS_CHECK_INTERVAL: int = 10  # Seconds between Redis health checks
    RATE_LIMIT_REDIS_MAX_ERRORS: int = 3  # Max Redis errors before switching to memory backend
    
    # Advanced rate limiting configuration
    # This can be overridden with environment variables
    RATE_LIMIT_CONFIG: Dict[str, List[Dict[str, Any]]] = {
        r"^/api/": [
            {"second": 30, "group": "default"},  # Strict 1 req/sec for most APIs
            {"group": "admin"},  # No limit for admin group
        ],
        r"^/api/shorten": [
            {"second": 30, "group": "default"},  # Strict 1 req/sec for shortening
            {"group": "admin"},
        ],
        r"^/api/urls": [
            {"second": 30, "group": "default"},  # Strict 1 req/sec for URL info
            {"group": "admin"},
        ],
    }
    
    # Security
    SECRET_KEY: str = "change_this_to_a_secure_random_string_in_production"
    TOKEN_EXPIRE_MINUTES: int = 10080
    
    # Logging configuration
    LOG_LEVEL: str = "DEBUG"  # Changed from INFO to DEBUG for testing
    LOG_DIR: str = "logs"
    LOG_FILENAME: str = "app.log"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "7 days"
    LOG_FORMAT: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}"
    LOG_JSON: bool = True
    REQUEST_LOGGING_ENABLED: bool = True  # Enable request logging middleware
    
    # Redis logging configuration
    REDIS_LOGGING_ENABLED: bool = True
    REDIS_LOGGING_QUEUE: str = "app:logs"
    REDIS_LOGGING_BATCH_SIZE: int = 100
    REDIS_LOGGING_FLUSH_INTERVAL: float = 5.0  # seconds
    LOG_PROCESSING_INTERVAL: int = 5  # Interval for the log processing job in seconds
    REDIS_LOGGING_RECONNECT_DELAY: float = 1.0  # seconds
    REDIS_LOGGING_MAX_RETRIES: int = 3
    REDIS_LOGGING_FALLBACK_LOCAL: bool = True
    
    # Metrics configuration
    METRICS_ENABLED: bool = True
    
    # URL Cleanup settings
    CLEANUP_BATCH_SIZE: int = 1000  # Number of URLs to process in each batch
    CLEANUP_INTERVAL_HOURS: int = 24  # How often to run the cleanup task (24 hours)
    CLEANUP_START_ON_STARTUP: bool = False  # Whether to run cleanup on app startup
    
    # Scheduler settings
    SCHEDULER_JOBSTORE_URL: str = "sqlite:///jobs.sqlite"  # URL for job store database
    SCHEDULER_JOB_COALESCE: bool = True  # Combine multiple pending executions of a job into a single execution
    SCHEDULER_JOB_MAX_INSTANCES: int = 1  # Maximum instances of the same job to run concurrently
    SCHEDULER_MISFIRE_GRACE_TIME: int = 15 * 60  # Seconds to still run misfired job after scheduled time
    
    # OpenTelemetry configuration
    OTEL_ENABLED: bool = True  # Enable/disable OpenTelemetry instrumentation
    OTEL_SERVICE_NAME: str = "url-shortener"  # Service name for traces
    OTEL_RESOURCE_ATTRIBUTES: str = "service.namespace=url-shortener,deployment.environment=development"  # Resource attributes
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"  # OTLP exporter endpoint for traces/metrics
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: str = "http://localhost:4317"  # OTLP metrics endpoint
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: str = "http://localhost:4318"  # OTLP logs endpoint
    OTEL_TRACES_SAMPLER: str = "parentbased_traceidratio"  # Sampling strategy
    OTEL_TRACES_SAMPLER_ARG: float = 1.0  # Sample 100% of traces by default
    OTEL_PROPAGATORS: str = "tracecontext,baggage"  # Propagators to use
    OTEL_PYTHON_LOG_CORRELATION: bool = True  # Enable log correlation
    OTEL_PYTHON_LOG_LEVEL: str = "INFO"  # Log level for OpenTelemetry
    OTEL_METRICS_EXPORT_INTERVAL_MILLIS: int = 60000  # Export metrics every 60 seconds
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "grpc"  # Protocol to use for OTLP export (grpc or http/protobuf)
    
    # Validators
    @field_validator("DEFAULT_EXPIRATION_DAYS", mode="before")
    def validate_expiration_days(cls, v: Any) -> Optional[int]:
        """Convert empty string to None for DEFAULT_EXPIRATION_DAYS."""
        if v == "":
            return None
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None
    
    @field_validator("SECRET_KEY")
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        default_value = "change_this_to_a_secure_random_string_in_production"
        # Get the environment value from the data dictionary instead of using cls.ENVIRONMENT
        env_value = info.data.get('ENVIRONMENT', EnvironmentType.DEVELOPMENT)
        
        # Check if the environment is production and we're using the default key
        if v == default_value and (env_value == EnvironmentType.PRODUCTION or str(env_value) == "production"):
            # Only warn during validation, don't block startup
            # In a real production app, you might want to raise an error here
            logger.warning("Using default SECRET_KEY in production environment! This is a security risk.")
        return v
    
    @field_validator("CORS_ORIGINS", "RATE_LIMIT_ADMIN_IPS", "RATE_LIMIT_ADMIN_API_KEYS")
    def validate_list_or_string(cls, v: Union[List[str], str]) -> List[str]:
        """Convert comma-separated string to list if needed."""
        if isinstance(v, str):
            # If it's an empty string, return an empty list
            if not v.strip():
                return []
            # If it's a single "*", keep it as a list with one element
            if v == "*":
                return ["*"]
            # Otherwise split by comma and strip whitespace
            return [item.strip() for item in v.split(",")]
        return v
    
    # Computed fields
    @computed_field
    def PG_DSN(self) -> str:
        """Construct the PostgreSQL DSN from individual components."""
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @computed_field
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Construct the SQLAlchemy database URI from settings or use override."""
        # Check if there's an explicit override in environment variables
        if hasattr(self, "_env_SQLALCHEMY_DATABASE_URI") and self._env_SQLALCHEMY_DATABASE_URI:
            return self._env_SQLALCHEMY_DATABASE_URI
            
        # Construct the URI from individual components
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @computed_field
    def REDIS_URI(self) -> str:
        """Construct the Redis URI from settings or use override."""
        # Check if there's an explicit override in environment variables
        if hasattr(self, "_env_REDIS_URI") and self._env_REDIS_URI:
            return self._env_REDIS_URI
            
        # Use empty string if no password is provided
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else "@"
        return f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# Create a singleton instance of the settings
settings = Settings() 