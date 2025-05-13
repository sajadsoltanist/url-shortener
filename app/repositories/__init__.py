"""Repository layer for the URL shortener application.

This module provides repository classes that abstract database operations
and implement the Repository pattern for clean separation of concerns.
"""

from app.repositories.base import (
    BaseRepository, 
    RepositoryError,
    EntityNotFoundError,
    DuplicateEntityError
)
from app.repositories.url_repository import URLRepository
from app.repositories.stats_repository import StatsRepository

__all__ = [
    # Base classes and exceptions
    "BaseRepository",
    "RepositoryError",
    "EntityNotFoundError",
    "DuplicateEntityError",
    
    # Concrete repositories
    "URLRepository",
    "StatsRepository",
] 