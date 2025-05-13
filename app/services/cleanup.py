"""Cleanup service for the URL shortener application.

This module contains the CleanupService class which implements business logic
for cleanup operations like expired URL removal and database maintenance.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.url_repository import URLRepository
from app.repositories.base import RepositoryError
from app.services.exceptions import ExpiredURLCleanupError

logger = logging.getLogger(__name__)


class CleanupService:
    """
    Service for cleanup operations in the URL shortener.
    
    This service handles cleanup tasks like expired URL removal,
    analytics data pruning, and other maintenance operations.
    """
    
    def __init__(self, url_repository: URLRepository):
        """
        Initialize the cleanup service.
        
        Args:
            url_repository: Repository for URL data access
        """
        self.url_repository = url_repository
    
    async def cleanup_expired_urls(
        self,
        db: AsyncSession,
        # delete parameter is no longer needed as we always delete
        # batch_size is also not directly used here as repository handles it
    ) -> Dict[str, Any]:
        """
        Clean up expired URLs by directly calling the repository's delete method.
        
        Args:
            db: Database session
            
        Returns:
            Dict with statistics about the cleanup operation
            
        Raises:
            ExpiredURLCleanupError: If cleanup fails
        """
        try:
            start_time = datetime.utcnow()
            
            # Directly delete expired URLs using the repository method
            # The repository method should handle batching if necessary, or delete all at once.
            # For now, assuming it deletes all expired ones based on its current signature.
            deleted_count = await self.url_repository.delete_expired_urls(db)
            
            end_time = datetime.utcnow()
            execution_time = (end_time - start_time).total_seconds()
            
            logger.info(
                f"Cleanup completed: {deleted_count} URLs deleted in {execution_time:.2f}s"
            )
            
            # Return statistics
            return {
                "processed": deleted_count, # Assuming all processed were attempted deletes
                "deleted": deleted_count,
                "errors": 0, # If delete_expired_urls raises an error, it will be caught below
                "execution_time": execution_time
            }
        except RepositoryError as e:
            logger.error(f"Error during expired URL cleanup: {e}", exc_info=True)
            raise ExpiredURLCleanupError(f"Failed to cleanup expired URLs: {str(e)}")
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error during expired URL cleanup: {e}", exc_info=True)
            raise ExpiredURLCleanupError(f"An unexpected error occurred: {str(e)}")
    
    async def prune_old_analytics(
        self,
        db: AsyncSession,
        days_to_keep: int = 90,
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Prune old analytics data to manage database size.
        
        This is important for systems with high traffic where the click logs
        can grow very large over time.
        
        Args:
            db: Database session
            days_to_keep: Number of days of analytics data to preserve
            batch_size: Number of records to process in a single batch
            
        Returns:
            Dict with statistics about the pruning operation
            
        Raises:
            ExpiredURLCleanupError: If pruning fails
        """
        # This is a placeholder implementation. In a real application,
        # you'd implement a method to delete old click records from the database.
        try:
            logger.info(f"Analytics pruning would remove data older than {days_to_keep} days")
            
            # In actual implementation, you would:
            # 1. Calculate the cutoff date
            # 2. Delete click records older than that date
            # 3. Return statistics about how many records were deleted
            
            # Placeholder return
            return {
                "pruned": 0,
                "execution_time": 0,
                "status": "not_implemented"
            }
        except Exception as e:
            logger.error(f"Error during analytics pruning: {e}")
            raise ExpiredURLCleanupError(f"Failed to prune old analytics: {str(e)}")
    
    async def run_maintenance(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Run all maintenance tasks as a scheduled job.
        
        This is designed to be called periodically by a scheduler.
        
        Args:
            db: Database session
            
        Returns:
            Dict with combined statistics about all maintenance operations
            
        Raises:
            ExpiredURLCleanupError: If maintenance fails
        """
        try:
            start_time = datetime.utcnow()
            
            # Run individual maintenance tasks
            expired_cleanup_stats = await self.cleanup_expired_urls(db)
            analytics_pruning_stats = await self.prune_old_analytics(db)
            
            end_time = datetime.utcnow()
            total_execution_time = (end_time - start_time).total_seconds()
            
            # Combine and return statistics
            return {
                "expired_cleanup": expired_cleanup_stats,
                "analytics_pruning": analytics_pruning_stats,
                "total_execution_time": total_execution_time,
                "timestamp": end_time.isoformat()
            }
        except Exception as e:
            logger.error(f"Error during maintenance: {e}")
            raise ExpiredURLCleanupError(f"Failed to run maintenance: {str(e)}")
    
    async def get_cleanup_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Get statistics about data that needs cleanup.
        
        This can be used in admin dashboards to show how much cleanup is needed.
        
        Args:
            db: Database session
            
        Returns:
            Dict with statistics about cleanup candidates
            
        Raises:
            ExpiredURLCleanupError: If retrieval fails
        """
        try:
            # Count expired URLs
            expired_count = await self.url_repository.count_expired_urls(db)
            
            # Count URLs expiring soon (next 24 hours)
            expiring_soon_count = await self.url_repository.count_urls_expiring_soon(
                db, timedelta(hours=24)
            )
            
            return {
                "expired_urls": expired_count,
                "expiring_soon_urls": expiring_soon_count,
                "timestamp": datetime.utcnow().isoformat()
            }
        except RepositoryError as e:
            logger.error(f"Error getting cleanup stats: {e}")
            raise ExpiredURLCleanupError(f"Failed to get cleanup statistics: {str(e)}") 