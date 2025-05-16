"""Test utilities for URL shortener tests."""

import random
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.models.url import ShortURL


def random_string(length: int = 10) -> str:
    """Generate a random alphanumeric string."""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def random_url() -> str:
    """Generate a random URL for testing."""
    domain = f"{random_string(8)}.com"
    path = random_string(12)
    return f"https://{domain}/{path}"


def create_test_url_data(
    original_url: Optional[str] = None,
    short_code: Optional[str] = None,
    is_custom: bool = False,
    expires_at: Optional[datetime] = None,
    click_count: int = 0
) -> Dict[str, Any]:
    """Create test data dict for a ShortURL."""
    return {
        "original_url": original_url or random_url(),
        "short_code": short_code or random_string(6),
        "is_custom": is_custom,
        "expires_at": expires_at,
        "click_count": click_count
    }


async def create_test_url(
    db,
    original_url: Optional[str] = None,
    short_code: Optional[str] = None,
    is_custom: bool = False,
    expires_at: Optional[datetime] = None,
    click_count: int = 0
) -> ShortURL:
    """Create and persist a test ShortURL in the database."""
    url_data = create_test_url_data(
        original_url=original_url,
        short_code=short_code,
        is_custom=is_custom,
        expires_at=expires_at,
        click_count=click_count
    )
    
    url = ShortURL(**url_data)
    db.add(url)
    await db.flush()
    await db.refresh(url)
    return url 