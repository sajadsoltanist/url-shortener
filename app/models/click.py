"""
Click event tracking data models.

This module defines the ClickEvent model for tracking and analyzing clicks on shortened URLs.
"""

# from __future__ import annotations the main problem is that it is not supported in python 3.10

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Index, ForeignKey
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .url import ShortURL


class ClickEventBase(SQLModel):
    """Base model for click event data."""
    
    clicked_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the short URL was clicked"
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="IP address of the visitor (may be anonymized)",
        max_length=45  # Support both IPv4 and IPv6 addresses
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="User agent string of the visitor's browser/device",
        max_length=1024
    )


class ClickEvent(ClickEventBase, table=True):
    """
    Click event model for tracking clicks on shortened URLs.
    
    This model stores basic analytics about each click on a shortened URL,
    including timestamp and visitor information. It's designed
    to be created asynchronously in background tasks to avoid slowing down
    the redirect flow for the end user.
    """
    
    __tablename__ = "click_events"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # IMPORTANT: Explicitly define the foreign key relationship with ondelete
    url_id: int = Field(
        foreign_key="short_urls.id",  # Explicit foreign key to short_urls table
        description="Foreign key reference to the shortened URL"
    )
    
    # Define relationship to ShortURL
    url: "ShortURL" = Relationship(
        back_populates="clicks",
        sa_relationship_kwargs={
            "lazy": "joined",  # Eager loading by default
            "passive_deletes": True  # Let the database handle deletions
        }
    )

    # Additional table configurations
    __table_args__ = (
        # Composite index for efficient time-based per-URL analytics queries
        Index("ix_click_events_url_id_clicked_at", "url_id", "clicked_at"),
        # New index for global analytics queries
        Index("ix_click_events_clicked_at", "clicked_at"),
    )


class ClickEventCreate(ClickEventBase):
    """Schema for creating a new click event tracking record."""
    url_id: int


class ClickEventRead(ClickEventBase):
    """Schema for reading a click event."""
    id: int
    url_id: int 