"""URL shortener data models.

This module defines the ShortURL model for storing shortened URLs in the database.
"""
from datetime import datetime, timedelta
from typing import List, Optional, TYPE_CHECKING
from pydantic import HttpUrl, validator

from sqlalchemy import Index, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.core.config import settings

if TYPE_CHECKING:
    from .click import ClickEvent


class ShortURLBase(SQLModel):
    """Base model for short URL data."""
    
    original_url: str = Field(
        description="The original (long) URL to redirect to"
    )
    short_code: str = Field(
        description="Unique code for the shortened URL",
        unique=True,   # Creates necessary index
    )
    is_custom: bool = Field(
        default=False,
        description="Whether the short code was custom-defined by the user"
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="When this short URL expires (null means no expiration)"
    )
    click_count: int = Field(
        default=0,
        description="Counter for the number of clicks"
    )

    # Validator to ensure original_url is stored as string
    @validator('original_url', pre=True)
    def ensure_str_url(cls, v):
        if hasattr(v, '__str__'):
            return str(v)
        return v


class ShortURL(ShortURLBase, table=True):
    """
    Short URL model for storing shortened URLs in the database.
    
    This model stores the mapping between short codes and original URLs,
    along with metadata such as creation date, expiration, and click statistics.
    The short_code field is used in the URL path to redirect users.
    """
    
    __tablename__ = "short_urls"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when this short URL was created"
    )
    
    # Define relationship to ClickEvent
    clicks: List["ClickEvent"] = Relationship(
        back_populates="url",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",  # Handle child records on deletion
            "passive_deletes": True,  # Let the database handle deletions
            "lazy": "selectin"  # Efficient loading of collections
        }
    )
    
    # Additional table configurations
    __table_args__ = (
        # Create a composite index on short_code and expires_at for efficient lookups
        Index("ix_short_urls_code_expiry", "short_code", "expires_at"),
        # Add index for recent URLs queries
        Index("ix_short_urls_created_at", "created_at"),
        # Add index for improved sorting operations
        Index("ix_short_urls_click_count", "click_count"),  # For get_top_urls
    )
    
    def is_expired(self) -> bool:
        """Check if the short URL has expired.
        
        Returns:
            bool: True if the URL has expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.utcnow()
    
    @classmethod
    def generate_expiration(cls, days: Optional[int] = None) -> Optional[datetime]:
        """Generate an expiration date based on the given number of days.
        
        Args:
            days: Number of days until expiration, or None for no expiration
            
        Returns:
            Optional[datetime]: Expiration date or None if days is None
        """
        if days is None: 
            # Use the default from settings if available 
            days = settings.DEFAULT_EXPIRATION_DAYS 
            
        if days is None: 
            return None
        return datetime.utcnow() + timedelta(days=days)


class ShortURLCreate(ShortURLBase):
    """Schema for creating a new short URL."""
    pass


class ShortURLRead(ShortURLBase):
    """Schema for reading a short URL."""
    id: int
    created_at: datetime
    click_count: int


class ShortURLUpdate(SQLModel):
    """Schema for updating a short URL."""
    original_url: Optional[str] = None
    expires_at: Optional[datetime] = None 
