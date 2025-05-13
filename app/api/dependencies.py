"""API dependencies for FastAPI.

This module provides dependency injection functions for FastAPI endpoints
to access database sessions and service instances.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.url_repository import URLRepository
from app.repositories.stats_repository import StatsRepository
from app.services.shortener import ShortenedURLService
from app.services.stats import StatsService
from app.services.cleanup import CleanupService
from app.core.config import settings


async def get_url_repository():
    """Get an instance of the URL repository."""
    return URLRepository()


async def get_stats_repository():
    """Get an instance of the stats repository."""
    return StatsRepository()


async def get_shortener_service(
    url_repo: URLRepository = Depends(get_url_repository),
) -> ShortenedURLService:
    """Get an instance of the URL shortening service."""
    return ShortenedURLService(url_repository=url_repo)


async def get_stats_service(
    stats_repo: StatsRepository = Depends(get_stats_repository),
    url_repo: URLRepository = Depends(get_url_repository),
) -> StatsService:
    """Get an instance of the statistics service."""
    return StatsService(stats_repository=stats_repo, url_repository=url_repo)


async def get_cleanup_service(
    url_repo: URLRepository = Depends(get_url_repository),
) -> CleanupService:
    """Get an instance of the cleanup service."""
    return CleanupService(url_repository=url_repo)


def get_base_url():
    """Get the base URL for shortened links."""
    return settings.BASE_URL
