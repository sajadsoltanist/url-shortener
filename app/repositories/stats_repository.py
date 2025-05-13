"""Stats Repository for click event tracking in the URL shortener application.

This module provides the StatsRepository class for database operations related to ClickEvent models.
Following the Repository pattern, it abstracts database interactions for click tracking and analytics.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union, Tuple

from sqlalchemy import select, func, desc, cast, Date, extract, text, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import and_, or_

from app.models.click import ClickEvent, ClickEventCreate, ClickEventRead
from app.repositories.base import BaseRepository, RepositoryError


class StatsRepository(BaseRepository[ClickEvent, ClickEventCreate, ClickEventRead]):
    """
    Repository for ClickEvent model database operations.
    
    This repository provides methods for creating and querying click events,
    with a focus on analytics and aggregation capabilities for tracking
    URL performance.
    """
    
    def __init__(self):
        """Initialize the repository with the ClickEvent model type."""
        super().__init__(ClickEvent)
    
    async def create_click_event(
        self, 
        db: AsyncSession, 
        data: Union[ClickEventCreate, Dict[str, Any]]
    ) -> ClickEvent:
        """
        Record a new click event.
        
        This method is designed to be called asynchronously in a background task
        after redirecting the user, to avoid adding latency to the redirect flow.
        
        Args:
            db: Database session
            data: Click event data (either as a ClickEventCreate model or dictionary)
            
        Returns:
            The created ClickEvent entity
            
        Raises:
            RepositoryError: On database errors
        """
        return await self.create(db, data)
    
    async def create_click_events_batch(
        self,
        db: AsyncSession,
        events_data: List[Union[ClickEventCreate, Dict[str, Any]]]
    ) -> None:
        """
        Record multiple click events in a single batch operation.
        
        This is much more efficient than creating events one at a time
        for high-traffic scenarios.
        
        Args:
            db: Database session
            events_data: List of click event data
        
        Raises:
            RepositoryError: On database errors
        """
        try:
            if not events_data:
                return
                
            # Convert to dicts if needed
            values = []
            for data in events_data:
                if isinstance(data, ClickEventCreate):
                    values.append(data.dict())
                else:
                    values.append(data)
            
            # Use Core insert for optimal performance
            await db.execute(insert(self.model_type), values)
        except Exception as e:
            raise RepositoryError(f"Error batch creating click events: {e}") from e
    
    async def get_clicks_for_url(
        self, 
        db: AsyncSession, 
        url_id: int, 
        limit: int = 100, 
        skip: int = 0
    ) -> List[ClickEvent]:
        """
        Get all click events for a specific URL.
        
        Args:
            db: Database session
            url_id: ID of the ShortURL
            limit: Maximum number of records to return
            skip: Number of records to skip (for pagination)
            
        Returns:
            List of ClickEvent entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = (
                select(self.model_type)
                .where(self.model_type.url_id == url_id)
                .order_by(desc(self.model_type.clicked_at))
                .offset(skip)
                .limit(limit)
            )
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving clicks for URL {url_id}: {e}") from e
    
    async def get_clicks_for_url_keyset(
        self, 
        db: AsyncSession, 
        url_id: int, 
        limit: int = 100,
        last_clicked_at: Optional[datetime] = None,
        last_id: Optional[int] = None
    ) -> List[ClickEvent]:
        """
        Get click events for a specific URL using keyset pagination.
        
        This is more efficient than offset pagination for deep result sets.
        
        Args:
            db: Database session
            url_id: ID of the ShortURL
            limit: Maximum number of records to return
            last_clicked_at: Timestamp of the last click from previous page
            last_id: ID of the last click from previous page
            
        Returns:
            List of ClickEvent entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type).where(self.model_type.url_id == url_id)
            
            # Apply keyset pagination if we have a previous page cursor
            if last_clicked_at is not None and last_id is not None:
                query = query.where(
                    or_(
                        self.model_type.clicked_at < last_clicked_at,
                        and_(
                            self.model_type.clicked_at == last_clicked_at,
                            self.model_type.id < last_id
                        )
                    )
                )
            
            # Order by clicked_at and id (to handle events with same timestamp)
            query = query.order_by(desc(self.model_type.clicked_at), desc(self.model_type.id)).limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving clicks for URL {url_id} with keyset pagination: {e}") from e
    
    async def get_clicks_by_timeframe(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        timeframe: str = "daily",
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get click counts aggregated by time periods.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            timeframe: Aggregation period ('daily', 'weekly', 'monthly')
            days: Number of days to look back
            
        Returns:
            List of dictionaries with date and count fields
            
        Raises:
            RepositoryError: On database errors
            ValueError: For invalid timeframe values
        """
        try:
            # Calculate the start date based on days parameter
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Base query conditions
            conditions = [self.model_type.clicked_at >= start_date]
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
                
            # Set up the date grouping based on the timeframe
            if timeframe == "daily":
                date_trunc = func.date_trunc('day', self.model_type.clicked_at)
                date_format = "%Y-%m-%d"
            elif timeframe == "weekly":
                date_trunc = func.date_trunc('week', self.model_type.clicked_at)
                date_format = "%Y-%m-%d"  # Week start date
            elif timeframe == "monthly":
                date_trunc = func.date_trunc('month', self.model_type.clicked_at)
                date_format = "%Y-%m"
            else:
                raise ValueError(f"Invalid timeframe: {timeframe}. Must be daily, weekly, or monthly")
            
            # Build and execute the query
            query = (
                select(
                    date_trunc.label("date"),
                    func.count().label("count")
                )
                .where(and_(*conditions))
                .group_by(date_trunc)
                .order_by(date_trunc)
            )
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format the results for easier consumption
            return [
                {
                    "date": row.date.strftime(date_format) if row.date else None,
                    "count": row.count
                }
                for row in rows
            ]
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise RepositoryError(f"Error retrieving click statistics by timeframe: {e}") from e
    
    async def get_clicks_by_country(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get click counts grouped by country.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            limit: Maximum number of countries to return
            
        Returns:
            List of dictionaries with country_code and count fields
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Set up conditions
            conditions = [self.model_type.country_code.isnot(None)]
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            # Build and execute the query
            query = (
                select(
                    self.model_type.country_code,
                    func.count().label("count")
                )
                .where(and_(*conditions))
                .group_by(self.model_type.country_code)
                .order_by(desc("count"))
                .limit(limit)
            )
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format the results
            return [
                {
                    "country_code": row.country_code,
                    "count": row.count
                }
                for row in rows
            ]
        except Exception as e:
            raise RepositoryError(f"Error retrieving click statistics by country: {e}") from e
    
    async def get_clicks_by_device(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get click counts grouped by device type.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            limit: Maximum number of device types to return
            
        Returns:
            List of dictionaries with device_type and count fields
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Set up conditions
            conditions = [self.model_type.device_type.isnot(None)]
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            # Build and execute the query
            query = (
                select(
                    self.model_type.device_type,
                    func.count().label("count")
                )
                .where(and_(*conditions))
                .group_by(self.model_type.device_type)
                .order_by(desc("count"))
                .limit(limit)
            )
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format the results
            return [
                {
                    "device_type": row.device_type,
                    "count": row.count
                }
                for row in rows
            ]
        except Exception as e:
            raise RepositoryError(f"Error retrieving click statistics by device: {e}") from e
    
    async def get_recent_clicks(
        self, 
        db: AsyncSession, 
        limit: int = 10
    ) -> List[ClickEvent]:
        """
        Get most recent clicks across all URLs.
        
        Args:
            db: Database session
            limit: Maximum number of records to return
            
        Returns:
            List of ClickEvent entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = (
                select(self.model_type)
                .order_by(desc(self.model_type.clicked_at))
                .limit(limit)
            )
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving recent clicks: {e}") from e
    
    async def get_referrer_stats(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top referrers for clicks.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            limit: Maximum number of referrers to return
            
        Returns:
            List of dictionaries with referrer and count fields
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Set up conditions
            conditions = [self.model_type.referrer.isnot(None)]
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            # Build and execute the query
            query = (
                select(
                    self.model_type.referrer,
                    func.count().label("count")
                )
                .where(and_(*conditions))
                .group_by(self.model_type.referrer)
                .order_by(desc("count"))
                .limit(limit)
            )
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format the results
            return [
                {
                    "referrer": row.referrer,
                    "count": row.count
                }
                for row in rows
            ]
        except Exception as e:
            raise RepositoryError(f"Error retrieving referrer statistics: {e}") from e
    
    async def get_hourly_distribution(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get click distribution by hour of day.
        
        This is useful for identifying peak usage times.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            days: Number of days to look back
            
        Returns:
            List of dictionaries with hour and count fields
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Calculate the start date based on days parameter
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Set up conditions
            conditions = [self.model_type.clicked_at >= start_date]
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            # Extract hour of day and count clicks
            query = (
                select(
                    extract('hour', self.model_type.clicked_at).label("hour"),
                    func.count().label("count")
                )
                .where(and_(*conditions))
                .group_by("hour")
                .order_by("hour")
            )
            
            result = await db.execute(query)
            rows = result.all()
            
            # Format the results
            return [
                {
                    "hour": int(row.hour),
                    "count": row.count
                }
                for row in rows
            ]
        except Exception as e:
            raise RepositoryError(f"Error retrieving hourly distribution: {e}") from e
    
    async def get_total_clicks(
        self, 
        db: AsyncSession, 
        url_id: Optional[int] = None,
        days: Optional[int] = None
    ) -> int:
        """
        Get total click count, optionally filtered by URL and time period.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            days: Optional number of days to look back (None for all time)
            
        Returns:
            Total click count
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Set up conditions
            conditions = []
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            if days is not None:
                start_date = datetime.utcnow() - timedelta(days=days)
                conditions.append(self.model_type.clicked_at >= start_date)
            
            # Build and execute the query
            query = select(func.count()).select_from(self.model_type)
            if conditions:
                query = query.where(and_(*conditions))
            
            result = await db.execute(query)
            return result.scalar_one()
        except Exception as e:
            raise RepositoryError(f"Error retrieving total click count: {e}") from e
    
    async def get_time_based_metrics(
        self,
        db: AsyncSession,
        url_id: Optional[int] = None,
        days_list: List[int] = [1, 7, 30, 365]
    ) -> Dict[str, int]:
        """
        Get click counts for multiple time periods in a single query.
        
        This method optimizes database access by constructing a more efficient query
        that can retrieve counts for multiple time periods in a single database roundtrip.
        
        Args:
            db: Database session
            url_id: Optional ID of the ShortURL (None for all URLs)
            days_list: List of day periods to count (e.g., [1, 7, 30])
            
        Returns:
            Dictionary with day counts mapped to click counts
        """
        try:
            now = datetime.utcnow()
            
            # If using PostgreSQL, we can optimize this with a single query using CASE statements
            # to count multiple time periods at once
            conditions = []
            if url_id is not None:
                conditions.append(self.model_type.url_id == url_id)
            
            # Build a query that counts for all time periods at once
            selects = [func.count().label("total")]
            
            for days in days_list:
                start_date = now - timedelta(days=days)
                selects.append(
                    func.count(
                        func.case(
                            [(self.model_type.clicked_at >= start_date, 1)],
                            else_=None
                        )
                    ).label(f"days_{days}")
                )
            
            # Build and execute the query
            query = select(*selects).select_from(self.model_type)
            if conditions:
                query = query.where(and_(*conditions))
            
            result = await db.execute(query)
            row = result.one()
            
            # Convert row to dictionary
            metrics = {"total": row.total}
            for days in days_list:
                metrics[f"days_{days}"] = getattr(row, f"days_{days}")
            
            return metrics
        except Exception as e:
            raise RepositoryError(f"Error retrieving time-based metrics: {e}") from e 