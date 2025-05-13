"""Core module for the URL shortener application."""

from app.core.config import settings
from app.core import alembic

__all__ = ["settings", "alembic"]
