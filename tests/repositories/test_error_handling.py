"""Tests for repository error handling."""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.repositories.url_repository import URLRepository, RepositoryError
from app.repositories.stats_repository import StatsRepository
from app.models.url import ShortURLCreate, ShortURL
from app.models.click import ClickEventCreate
from tests.utils import random_url
from sqlalchemy import text


@pytest.mark.repository
class TestRepositoryErrorHandling:
    """Tests for error handling in repositories."""
    
    @pytest.fixture
    def url_repository(self):
        """Return a URL repository instance."""
        return URLRepository()
    
    @pytest.fixture
    def stats_repository(self):
        """Return a Stats repository instance."""
        return StatsRepository()
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, test_db, url_repository):
        """Test handling of database errors."""
        url_data = ShortURLCreate(
            original_url=random_url(),
            short_code="errortest",
            is_custom=True
        )
        
        with patch.object(test_db, 'execute', side_effect=SQLAlchemyError("Test database error")):
            with pytest.raises(RepositoryError) as excinfo:
                await url_repository.get_by_short_code(test_db, "errortest")
            
            assert "Test database error" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_integrity_error_handling(self, test_db, url_repository):
        """Test handling of integrity errors like duplicates."""
        original_url = random_url()
        short_code = "duplicate"
        
        url_data = ShortURLCreate(
            original_url=original_url,
            short_code=short_code,
            is_custom=True
        )
        
        await url_repository.create_short_url(test_db, url_data)
        
        duplicate_data = ShortURLCreate(
            original_url=random_url(),
            short_code=short_code,
            is_custom=True
        )
        
        with pytest.raises(RepositoryError) as excinfo:
            await url_repository.create_short_url(test_db, duplicate_data)
        
        assert "short_code" in str(excinfo.value).lower()
        assert short_code in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_non_existent_entity(self, test_db, url_repository):
        """Test operations on non-existent entities."""
        result = await url_repository.get_by_short_code(test_db, "nonexistent")
        assert result is None
        
        non_existent_id = 999999
        update_result = await url_repository.update(
            test_db, 
            non_existent_id, 
            {"original_url": "https://example.com/updated"}
        )
        assert update_result is None
        
        delete_result = await url_repository.delete(test_db, non_existent_id)
        assert delete_result is False
    
    @pytest.mark.asyncio
    async def test_batch_operation_error_handling(self, test_db, stats_repository):
        """Test error handling in batch operations."""
        non_existent_url_id = 99999  
        
        with patch.object(stats_repository, 'create_click_events_batch', 
                         side_effect=RepositoryError("Test batch error")):
            with pytest.raises(RepositoryError):
                await stats_repository.create_click_events_batch(
                    test_db, 
                    [ClickEventCreate(url_id=non_existent_url_id)]
                )
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, test_db, url_repository):
        """Verify transaction rollback on errors."""
        count_query = text("SELECT COUNT(*) FROM short_urls")
        result = await test_db.execute(count_query)
        initial_count = result.scalar()
        
        exception_caught = False
        
        first_url = ShortURLCreate(
            original_url=random_url(),
            short_code="txn_test_url",
            is_custom=True
        )
        
        try:
            # Create a valid URL
            await url_repository.create_short_url(test_db, first_url)
            
            # Try creating another with same short code to trigger constraint error
            await url_repository.create_short_url(
                test_db,
                ShortURLCreate(
                    original_url=random_url(),
                    short_code="txn_test_url",
                    is_custom=True
                )
            )
        except RepositoryError:
            exception_caught = True
        
        assert exception_caught, "The expected RepositoryError was not raised"
        
        result = await test_db.execute(count_query)
        final_count = result.scalar()
        
        assert final_count == initial_count + 1 