"""Basic tests to verify test DB setup."""

import pytest
import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import select, text
from app.models.url import ShortURL


@pytest.mark.asyncio
async def test_create_tables(test_db):
    """Verify tables are created correctly in test database."""
    # Check table schema
    result = await test_db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='short_urls'"))
    tables = [row[0] for row in result.fetchall()]
    assert "short_urls" in tables
    
    # Create a simple ShortURL
    url = ShortURL(
        original_url="https://example.com",
        short_code="test123",
        is_custom=True,
        created_at=datetime.utcnow(),
        click_count=0
    )
    
    test_db.add(url)
    await test_db.commit()
    
    # Verify retrieval works
    result = await test_db.execute(select(ShortURL).where(ShortURL.short_code == "test123"))
    retrieved_url = result.scalars().first()
    
    assert retrieved_url is not None
    assert retrieved_url.original_url == "https://example.com"
    assert retrieved_url.short_code == "test123"
    assert retrieved_url.is_custom is True


@pytest.mark.asyncio
async def test_table_exists(test_engine):
    """Verify ShortURL table exists in database."""
    async with test_engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result.fetchall()]
        
    assert "short_urls" in tables
    print(f"Tables in test database: {tables}")


@pytest.mark.asyncio
async def test_click_events_table(test_db):
    """Verify ClickEvent table exists with proper relationship to ShortURL."""
    # Check table exists
    result = await test_db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='click_events'"))
    tables = [row[0] for row in result.fetchall()]
    assert "click_events" in tables
    
    # Check foreign key relationship
    result = await test_db.execute(text("PRAGMA foreign_key_list('click_events')"))
    fk_info = result.fetchall()
    
    assert any(fk[2] == 'short_urls' for fk in fk_info) 