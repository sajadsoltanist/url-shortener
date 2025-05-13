"""Stats service for the URL shortener application.

This module contains the StatsService class which implements business logic
for URL click tracking and analytics.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.click import ClickEvent, ClickEventCreate
from app.repositories.stats_repository import StatsRepository
from app.repositories.url_repository import URLRepository
from app.repositories.base import RepositoryError
from app.db.session import SessionManager, db_transaction
from app.services.exceptions import (
    StatsTrackingError,
    StatsRetrievalError,
    URLNotFoundError,
)

logger = logging.getLogger(__name__)


class StatsService:
    """
    Service for URL click statistics business logic.
    
    This service handles tracking click events and providing analytics
    for URL performance.
    """
    
    def __init__(self, stats_repository: StatsRepository, url_repository: URLRepository):
        """
        Initialize the stats service.
        
        Args:
            stats_repository: Repository for click statistics data access
            url_repository: Repository for URL data access
        """
        self.stats_repository = stats_repository
        self.url_repository = url_repository
    
    @db_transaction(db_param_name="db")
    async def track_click(
        self,
        db: AsyncSession,
        short_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Track a single click event.
        
        For high-traffic scenarios, consider calling track_clicks_batch instead
        or implementing a queue system that buffers clicks and processes them in batches.
        """
        await self.track_clicks_batch(db, [{
            "short_code": short_code,
            "ip_address": ip_address,
            "user_agent": user_agent
        }])
    
    @db_transaction(db_param_name="db")
    async def track_clicks_batch(
        self,
        db: AsyncSession,
        click_events: List[Dict[str, Any]]
    ) -> None:
        """
        Process multiple click events in a batch for efficiency.
        
        Args:
            db: Database session
            click_events: List of click event data dictionaries, each containing:
                         - short_code: The short code that was clicked
                         - ip_address: Optional visitor IP address
                         - user_agent: Optional visitor user agent string
                         - clicked_at: Optional timestamp (defaults to now)
        """
        if not click_events:
            return
            
        # Group events by URL ID to minimize lookups
        events_by_url = {}
        url_ids = {}
        
        try:
            # First, look up all unique short_codes in a single pass
            unique_codes = set(event["short_code"] for event in click_events)
            for code in unique_codes:
                try:
                    url = await self.url_repository.get_by_short_code(db, code)
                    if url:
                        url_ids[code] = url.id
                except RepositoryError as e:
                    logger.error(f"Error retrieving URL by code: {e}")
            
            # Process click events, grouped by URL ID
            click_records = []
            click_counts = {}  # url_id -> count
            
            for event in click_events:
                code = event["short_code"]
                if code not in url_ids:
                    continue  # Skip events for unknown URLs
                    
                url_id = url_ids[code]
                
                # Count clicks per URL for batched increment
                if url_id not in click_counts:
                    click_counts[url_id] = 0
                click_counts[url_id] += 1
                
                # Prepare click event record
                click_records.append({
                    "url_id": url_id,
                    "ip_address": event.get("ip_address"),
                    "user_agent": event.get("user_agent"),
                    "clicked_at": event.get("clicked_at", datetime.utcnow())
                })
            
            # Batch increment click counts
            for url_id, count in click_counts.items():
                # Simple increment for now - could optimize further with custom SQL
                await self.url_repository.bulk_update(
                    db, 
                    {"id": url_id}, 
                    {"click_count": self.url_repository.model_type.click_count + count}
                )
            
            # Batch insert click events
            if click_records:
                await self.stats_repository.create_click_events_batch(db, click_records)
        except Exception as e:
            logger.error(f"Error batch tracking clicks: {e}")
            raise StatsTrackingError(f"Failed to track clicks in batch: {str(e)}")
    
    @db_transaction(db_param_name="db")
    async def get_url_stats(
        self, 
        db: AsyncSession, 
        short_code: str,
        timeframe: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a specific URL with optimized queries.
        
        Args:
            db: Database session
            short_code: The short code of the URL
            timeframe: Aggregation period for time series data ('daily', 'weekly', 'monthly')
            days: Number of days to include in the stats
            
        Returns:
            Dictionary with various statistics metrics
            
        Raises:
            StatsRetrievalError: If retrieval fails
            URLNotFoundError: If no URL with this code exists
        """
        try:
            # Get the URL
            url = await self.url_repository.get_by_short_code(db, short_code)
            if not url:
                raise URLNotFoundError(f"URL with code '{short_code}' not found")
            
            # Gather multiple time-based metrics in a single call
            time_metrics = await self.get_time_based_metrics(db, url.id, [1, 7, 30, 365])
            
            # Execute remaining queries in parallel using asyncio.gather
            timeline_data, hourly_data, recent_clicks = await asyncio.gather(
                self.stats_repository.get_clicks_by_timeframe(db, url.id, timeframe, days),
                self.stats_repository.get_hourly_distribution(db, url.id, days),
                self.stats_repository.get_clicks_for_url(db, url.id, limit=10)
            )
            
            # Return compiled statistics
            return {
                "url_id": str(url.id),
                "short_code": url.short_code,
                "original_url": url.original_url,
                "created_at": url.created_at,
                "expires_at": url.expires_at,
                "total_clicks": time_metrics.get("total", 0),
                "clicks_24h": time_metrics.get("days_1", 0),
                "clicks_7d": time_metrics.get("days_7", 0),
                "clicks_30d": time_metrics.get("days_30", 0),
                "timeline": timeline_data,
                "hourly_distribution": {str(item["hour"]): item["count"] for item in hourly_data},
                "recent_clicks": [
                    {
                        "clicked_at": click.clicked_at,
                        "ip_address": click.ip_address,
                        "user_agent": click.user_agent,
                    }
                    for click in recent_clicks
                ]
            }
        except (RepositoryError, URLNotFoundError) as e:
            logger.error(f"Error retrieving URL stats: {e}")
            if isinstance(e, URLNotFoundError):
                raise
            raise StatsRetrievalError(f"Failed to retrieve URL statistics: {str(e)}")
    
    async def get_time_based_metrics(
        self,
        db: AsyncSession,
        url_id: Optional[int] = None,
        days_list: List[int] = [1, 7, 30, 365]
    ) -> Dict[str, int]:
        """
        Get click counts for multiple time periods.
        
        Args:
            db: Database session
            url_id: Optional URL ID to filter by
            days_list: List of day periods to count
            
        Returns:
            Dictionary with day counts mapped to click counts
        """
        try:
            metrics = {}
            
            # Get total clicks (all time)
            metrics["total"] = await self.stats_repository.get_total_clicks(db, url_id)
            
            # Get clicks for each time period
            for days in days_list:
                count = await self.stats_repository.get_total_clicks(db, url_id, days=days)
                metrics[f"days_{days}"] = count
                
            return metrics
        except Exception as e:
            logger.error(f"Error retrieving time-based metrics: {e}")
            raise StatsRetrievalError(f"Failed to retrieve time-based metrics: {str(e)}")
    
    @db_transaction(db_param_name="db")
    async def get_global_stats(
        self, 
        db: AsyncSession,
        timeframe: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get platform-wide statistics across all URLs.
        
        Args:
            db: Database session
            timeframe: Aggregation period for time series data ('daily', 'weekly', 'monthly')
            days: Number of days to include in the stats
            
        Returns:
            Dictionary with various system-wide statistics
            
        Raises:
            StatsRetrievalError: If retrieval fails
        """
        try:
            # Gather multiple time-based metrics in a single call
            time_metrics = await self.get_time_based_metrics(db, None, [1, 7, 30, 365])
            
            # Execute remaining queries in parallel using asyncio.gather
            timeline_data, hourly_data, recent_clicks = await asyncio.gather(
                self.stats_repository.get_clicks_by_timeframe(db, None, timeframe, days),
                self.stats_repository.get_hourly_distribution(db, None, days),
                self.stats_repository.get_recent_clicks(db)
            )
            
            # Return compiled statistics
            return {
                "total_clicks": time_metrics.get("total", 0),
                "clicks_24h": time_metrics.get("days_1", 0),
                "clicks_7d": time_metrics.get("days_7", 0),
                "clicks_30d": time_metrics.get("days_30", 0),
                "timeline": timeline_data,
                "hourly_distribution": {str(item["hour"]): item["count"] for item in hourly_data},
                "recent_clicks": [
                    {
                        "clicked_at": click.clicked_at,
                        "ip_address": click.ip_address,
                        "user_agent": click.user_agent,
                        "short_code": click.url.short_code if click.url else None
                    }
                    for click in recent_clicks
                ]
            }
        except RepositoryError as e:
            logger.error(f"Error retrieving global stats: {e}")
            raise StatsRetrievalError(f"Failed to retrieve global statistics: {str(e)}")
    
    async def extract_device_info(self, user_agent: Optional[str]) -> Optional[str]:
        """
        Extract device type from user agent string.
        
        This is a simplified implementation. In production, consider using a
        dedicated user-agent parsing library.
        
        Args:
            user_agent: The user agent string
            
        Returns:
            String representing device type or None if undetermined
        """
        if not user_agent:
            return None
            
        user_agent_lower = user_agent.lower()
        
        # Simple detection logic
        if any(keyword in user_agent_lower for keyword in ['mobile', 'android', 'iphone', 'ipod']):
            return 'mobile'
        elif 'tablet' in user_agent_lower or 'ipad' in user_agent_lower:
            return 'tablet'
        elif any(keyword in user_agent_lower for keyword in ['bot', 'crawl', 'spider']):
            return 'bot'
        else:
            return 'desktop' 