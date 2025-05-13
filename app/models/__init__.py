"""
Data models for the URL shortener application.

This module imports and exports all SQLModel models used in the application.
"""

# First import SQLModel itself to ensure metadata is initialized
from sqlmodel import SQLModel

# Import non-table models to avoid circular import issues
from app.models.url import (
    ShortURLBase, 
    ShortURLCreate, 
    ShortURLRead, 
    ShortURLUpdate
)
from app.models.click import (
    ClickEventBase, 
    ClickEventCreate, 
    ClickEventRead
)

# Then import table models in correct order (parent before child)
from app.models.url import ShortURL
from app.models.click import ClickEvent

__all__ = [
    # Click event models
    "ClickEvent",
    "ClickEventBase",
    "ClickEventCreate",
    "ClickEventRead",
    
    # Short URL models
    "ShortURL",
    "ShortURLBase",
    "ShortURLCreate",
    "ShortURLRead",
    "ShortURLUpdate",
]
