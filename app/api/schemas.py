"""API request and response schemas.

This module contains Pydantic models for API request validation
and response serialization.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from pydantic import BaseModel, HttpUrl, Field, validator
from pydantic.networks import AnyHttpUrl


class Timeframe(str, Enum):
    """Timeframe options for statistics aggregation."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class URLCreateRequest(BaseModel):
    """Request schema for creating a shortened URL."""
    original_url: HttpUrl
    custom_code: Optional[str] = None
    expiration_days: Optional[int] = Field(None, ge=1)
    
    # Convert HttpUrl to string for SQLAlchemy compatibility
    @validator('original_url')
    def convert_url_to_str(cls, v):
        return str(v)


class URLResponse(BaseModel):
    """Response schema for URL information."""
    short_code: str
    original_url: str
    short_url: str  # Full URL including base domain
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_custom: bool
    click_count: int
    
    class Config:
        from_attributes = True


class URLListResponse(BaseModel):
    """Response schema for listing multiple URLs."""
    urls: List[URLResponse]
    page_count: int


class ClickData(BaseModel):
    """Schema for click event data."""
    clicked_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class TimelinePoint(BaseModel):
    """Schema for a point in a timeline chart."""
    date: str
    count: int


class URLStatsResponse(BaseModel):
    """Response schema for URL statistics."""
    url_id: str
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    total_clicks: int
    clicks_24h: int
    clicks_7d: int
    timeline: List[TimelinePoint]
    hourly_distribution: Dict[str, int]
    recent_clicks: List[ClickData]


class ErrorResponse(BaseModel):
    """Enhanced response schema for errors."""
    detail: str
    error_code: Optional[str] = None  # Machine-readable error code
    field_errors: Optional[Dict[str, List[str]]] = None  # For validation errors 