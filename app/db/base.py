"""Database base configuration for SQLAlchemy with SQLModel.

This module provides base database configuration for async SQLAlchemy with SQLModel.
It includes:
- Engine configuration
- Base model setup
- Metadata management
- Health check functionality
"""

from typing import AsyncGenerator, Dict, Optional
import asyncio
import logging
import warnings
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import text
from sqlmodel import SQLModel

from app.core.config import settings

logger = logging.getLogger(__name__)

# Mapping of environment to SQLAlchemy engine configurations
ENGINE_CONFIGS: Dict[str, Dict] = {
    "development": {
        "echo": True,
        "pool_size": settings.POSTGRES_POOL_SIZE,
        "max_overflow": settings.POSTGRES_POOL_MAX_OVERFLOW,
        "pool_timeout": settings.POSTGRES_POOL_TIMEOUT,
        "pool_recycle": settings.POSTGRES_POOL_RECYCLE,
        "pool_pre_ping": True,
    },
    "production": {
        "echo": False,
        "pool_size": settings.POSTGRES_POOL_SIZE,
        "max_overflow": settings.POSTGRES_POOL_MAX_OVERFLOW,
        "pool_timeout": settings.POSTGRES_POOL_TIMEOUT,
        "pool_recycle": settings.POSTGRES_POOL_RECYCLE,
        "pool_pre_ping": True,
    },
    "testing": {
        "echo": False,
        "poolclass": NullPool,  # Use NullPool for tests to avoid connection issues
    },
}


def get_engine_config() -> Dict:
    """Get the appropriate engine configuration based on the environment.
    
    Returns:
        Dict: Engine configuration parameters for the current environment.
    """
    env = settings.ENVIRONMENT.value
    return ENGINE_CONFIGS.get(env, ENGINE_CONFIGS["development"])


def get_engine() -> AsyncEngine:
    """Create and configure an async SQLAlchemy engine.
    
    Returns:
        AsyncEngine: Configured SQLAlchemy async engine instance.
    """
    engine_url = str(settings.SQLALCHEMY_DATABASE_URI)
    engine_config = get_engine_config()
    
    logger.info(f"Creating database engine with URL: {engine_url}")
    
    return create_async_engine(
        engine_url,
        future=True,
        **engine_config,
    )


# Shared async engine instance
engine = get_engine()

# Async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async session with proper error handling and cleanup.
    
    Yields:
        AsyncSession: SQLAlchemy async session
    """
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


class DatabaseHealthCheck:
    """Health check functionality for the database connection."""
    
    @staticmethod
    async def check_connection() -> Dict:
        """Check database connectivity and return status.
        
        Returns:
            Dict: Health check result containing status and latency information
        """
        start_time = asyncio.get_event_loop().time()
        status = "healthy"
        error_message = None
        latency_ms = 0
        
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            latency_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        except Exception as e:
            status = "unhealthy"
            error_message = str(e)
            logger.error(f"Database health check failed: {e}")
        
        return {
            "status": status,
            "latency_ms": latency_ms,
            "error": error_message,
        }
