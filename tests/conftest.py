"""Test fixtures for the URL shortener application."""

import asyncio
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict, Generator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text
from sqlmodel import SQLModel

from app.core.config import settings
from app.db.base import get_engine, get_session
from app.db.session import get_db
from app.main import app as main_app
# Import models to ensure they're registered with SQLModel metadata
from app.models.url import ShortURL
from app.models.click import ClickEvent


# Test database URL - using SQLite in-memory
TEST_SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine with in-memory SQLite."""
    engine = create_async_engine(
        TEST_SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated test database session."""
    async_session = sessionmaker(
        bind=test_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture
def override_get_db(test_db):
    """Override the get_db dependency for testing."""
    async def _override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    return _override_get_db


@pytest.fixture
def test_app(override_get_db) -> FastAPI:
    """Create FastAPI test app with overridden dependencies."""
    app = main_app
    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(test_app) -> Generator[TestClient, None, None]:
    """Return FastAPI TestClient instance."""
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set testing environment variables."""
    original_env = os.environ.copy()
    
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    os.environ["CACHE_ENABLED"] = "false"
    
    yield
    
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for pytest-asyncio."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def setup_test_data(test_db):
    """Setup placeholder for test data seeding."""
    pass


@pytest.fixture
def mock_redis():
    """Mock Redis for testing."""
    class MockRedis:
        def __init__(self):
            self.data = {}
            self.expiry = {}
        
        async def get(self, key):
            return self.data.get(key)
        
        async def set(self, key, value, ex=None):
            self.data[key] = value
            if ex:
                self.expiry[key] = ex
        
        async def delete(self, key):
            if key in self.data:
                del self.data[key]
                if key in self.expiry:
                    del self.expiry[key]
        
        async def exists(self, key):
            return key in self.data
        
        async def close(self):
            pass
    
    return MockRedis() 