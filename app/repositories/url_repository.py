"""URL Repository for the URL shortener application.

This module provides the URLRepository class for database operations related to ShortURL models.
Following the Repository pattern, it abstracts database interactions for URL shortening operations.
"""

from datetime import datetime
from typing import List, Optional, Union, Dict, Any, Tuple

from sqlalchemy import select, update, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.url import ShortURL, ShortURLCreate, ShortURLUpdate
from app.repositories.base import BaseRepository, RepositoryError, DuplicateEntityError


class URLRepository(BaseRepository[ShortURL, ShortURLCreate, ShortURLUpdate]):
    """
    Repository for ShortURL model database operations.
    
    This repository provides methods for creating, retrieving, updating, and
    deleting shortened URLs, as well as specialized operations like click counting
    and cleaning up expired URLs.
    """
    
    def __init__(self):
        """Initialize the repository with the ShortURL model type."""
        super().__init__(ShortURL)
    
    async def create_short_url(
        self, 
        db: AsyncSession, 
        data: Union[ShortURLCreate, Dict[str, Any]]
    ) -> ShortURL:
        """
        Create a new shortened URL entry.
        
        Args:
            db: Database session
            data: Short URL data (either as a ShortURLCreate model or dictionary)
            
        Returns:
            The created ShortURL entity
            
        Raises:
            DuplicateEntityError: If the short code already exists
            RepositoryError: On other database errors
        """
        try:
            # Check if short_code already exists (if provided)
            if isinstance(data, ShortURLCreate):
                short_code = data.short_code
            else:
                short_code = data.get("short_code")
                
            if short_code and await self.check_short_code_exists(db, short_code):
                raise DuplicateEntityError(self.model_type, "short_code", short_code)
                
            # Proceed with creation
            return await self.create(db, data)
        except IntegrityError as e:
            # Check for duplicate key violation
            if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                if isinstance(data, ShortURLCreate):
                    short_code = data.short_code
                else:
                    short_code = data.get("short_code", "unknown")
                raise DuplicateEntityError(self.model_type, "short_code", short_code)
            raise RepositoryError(f"Database error creating short URL: {e}") from e
    
    async def get_by_short_code(self, db: AsyncSession, short_code: str) -> Optional[ShortURL]:
        """
        Find a URL by its short code.
        
        Args:
            db: Database session
            short_code: The unique short code to look up
            
        Returns:
            The ShortURL if found, None otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type).where(self.model_type.short_code == short_code)
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            raise RepositoryError(f"Error retrieving URL by short code: {e}") from e
    
    async def get_active_by_short_code(self, db: AsyncSession, short_code: str) -> Optional[ShortURL]:
        """
        Find a non-expired URL by its short code.
        
        Args:
            db: Database session
            short_code: The unique short code to look up
            
        Returns:
            The ShortURL if found and not expired, None otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            now = datetime.utcnow()
            query = select(self.model_type).where(
                and_(
                    self.model_type.short_code == short_code,
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
            )
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            raise RepositoryError(f"Error retrieving active URL by short code: {e}") from e
    
    async def increment_click_count(self, db: AsyncSession, url_id: int) -> Optional[ShortURL]:
        """
        Increment the click count for a URL.
        
        This is designed to be efficient for high-traffic scenarios, using a direct
        UPDATE statement rather than loading and modifying the entity.
        
        Args:
            db: Database session
            url_id: The ID of the ShortURL to update
            
        Returns:
            The updated ShortURL if found, None otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Use an efficient UPDATE statement with counter increment
            stmt = (
                update(self.model_type)
                .where(self.model_type.id == url_id)
                .values(click_count=self.model_type.click_count + 1)
                .execution_options(synchronize_session=False)  # Optimization: skip Python-side synchronization
                .returning(self.model_type)
            )
            
            result = await db.execute(stmt)
            updated_url = result.scalar_one_or_none()
            
            # No need to refresh as we used RETURNING
            return updated_url
        except Exception as e:
            raise RepositoryError(f"Error incrementing click count: {e}") from e
    
    async def check_short_code_exists(self, db: AsyncSession, short_code: str) -> bool:
        """
        Check if a custom short code already exists.
        
        Args:
            db: Database session
            short_code: The short code to check
            
        Returns:
            True if the short code exists, False otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        return await self.exists(db, short_code=short_code)
    
    async def get_top_urls(
        self, 
        db: AsyncSession, 
        limit: int = 10, 
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get top URLs by click count.
        
        Args:
            db: Database session
            limit: Maximum number of URLs to return
            include_expired: Whether to include expired URLs
            
        Returns:
            List of ShortURL entities ordered by click count (descending)
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type).order_by(desc(self.model_type.click_count)).limit(limit)
            
            if not include_expired:
                now = datetime.utcnow()
                query = query.where(
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
                
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving top URLs: {e}") from e
    
    async def delete_expired_urls(self, db: AsyncSession) -> int:
        """
        Clean up expired URLs.
        
        This method is useful for maintenance tasks or scheduled cleanup jobs.
        
        Args:
            db: Database session
            
        Returns:
            Number of deleted URLs
            
        Raises:
            RepositoryError: On database errors
        """
        now = datetime.utcnow()
        # Pass the complex condition directly. The key ('complex_filter') is a placeholder 
        # as bulk_delete will use the value directly if it's a SQLAlchemy expression.
        complex_filter_condition = and_(
            self.model_type.expires_at.isnot(None), 
            self.model_type.expires_at < now
        )
        return await self.bulk_delete(
            db,
            # The key here is arbitrary since the value is a SQLAlchemy expression
            filter_condition=complex_filter_condition 
        )
    
    async def get_recent_urls(
        self, 
        db: AsyncSession, 
        limit: int = 10, 
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get recently created URLs.
        
        Args:
            db: Database session
            limit: Maximum number of URLs to return
            include_expired: Whether to include expired URLs
            
        Returns:
            List of ShortURL entities ordered by creation date (descending)
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type).order_by(desc(self.model_type.created_at)).limit(limit)
            
            if not include_expired:
                now = datetime.utcnow()
                query = query.where(
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
                
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving recent URLs: {e}") from e
    
    async def search_urls(
        self, 
        db: AsyncSession, 
        search_term: str, 
        limit: int = 10,
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Search URLs by original URL or short code.
        
        Args:
            db: Database session
            search_term: Term to search for in original_url or short_code
            limit: Maximum number of results to return
            include_expired: Whether to include expired URLs
            
        Returns:
            List of matching ShortURL entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Use ILIKE for case-insensitive search in PostgreSQL
            conditions = [
                self.model_type.original_url.ilike(f"%{search_term}%"),
                self.model_type.short_code.ilike(f"%{search_term}%")
            ]
            
            query = select(self.model_type).where(or_(*conditions)).limit(limit)
            
            if not include_expired:
                now = datetime.utcnow()
                query = query.where(
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
                
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error searching URLs: {e}") from e
    
    async def get_urls_expiring_soon(
        self, 
        db: AsyncSession, 
        days: int = 1, 
        limit: int = 100
    ) -> List[ShortURL]:
        """
        Get URLs that are expiring soon (within the specified number of days).
        
        Args:
            db: Database session
            days: Number of days to consider as "expiring soon"
            limit: Maximum number of results to return
            
        Returns:
            List of ShortURL entities that will expire soon
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            now = datetime.utcnow()
            expiry_threshold = text(f"NOW() + INTERVAL '{days} days'")
            
            query = select(self.model_type).where(
                and_(
                    self.model_type.expires_at.isnot(None),
                    self.model_type.expires_at > now,
                    self.model_type.expires_at < expiry_threshold
                )
            ).limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving URLs expiring soon: {e}") from e
    
    async def get_url_with_clicks(
        self, 
        db: AsyncSession, 
        short_code: str,
        clicks_limit: int = 100
    ) -> Optional[ShortURL]:
        """
        Get a URL by short code with its recent clicks preloaded.
        
        This avoids N+1 queries when accessing the URL's clicks.
        
        Args:
            db: Database session
            short_code: The unique short code to look up
            clicks_limit: Maximum number of click events to load
            
        Returns:
            The ShortURL with preloaded clicks if found, None otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = (
                select(self.model_type)
                .options(
                    selectinload(
                        self.model_type.clicks
                    ).limit(clicks_limit).order_by(desc("clicked_at"))
                )
                .where(self.model_type.short_code == short_code)
            )
            
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            raise RepositoryError(f"Error retrieving URL by short code with clicks: {e}") from e
    
    async def get_short_url_for_redirect(
        self, 
        db: AsyncSession, 
        short_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get minimal URL data needed for redirect.
        
        This is optimized to only retrieve the columns needed for redirecting,
        reducing data transfer and serialization overhead.
        
        Args:
            db: Database session
            short_code: The unique short code to look up
            
        Returns:
            Dict with original_url and id if found, None otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            now = datetime.utcnow()
            query = (
                select(
                    self.model_type.id,
                    self.model_type.original_url,
                )
                .where(
                    and_(
                        self.model_type.short_code == short_code,
                        or_(
                            self.model_type.expires_at.is_(None),
                            self.model_type.expires_at > now
                        )
                    )
                )
            )
            
            result = await db.execute(query)
            row = result.one_or_none()
            
            if not row:
                return None
                
            return {
                "id": row[0],
                "original_url": row[1]
            }
        except Exception as e:
            raise RepositoryError(f"Error retrieving URL for redirect: {e}") from e
    
    async def get_recent_urls_keyset(
        self,
        db: AsyncSession,
        limit: int = 10,
        last_created_at: Optional[datetime] = None,
        last_id: Optional[int] = None,
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get recently created URLs using keyset pagination.
        
        This is more efficient than offset pagination for deep result sets.
        
        Args:
            db: Database session
            limit: Maximum number of URLs to return
            last_created_at: Timestamp of the last URL from previous page
            last_id: ID of the last URL from previous page
            include_expired: Whether to include expired URLs
            
        Returns:
            List of ShortURL entities ordered by creation date (descending)
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type)
            
            # Apply keyset pagination if we have a previous page cursor
            if last_created_at is not None and last_id is not None:
                query = query.where(
                    or_(
                        self.model_type.created_at < last_created_at,
                        and_(
                            self.model_type.created_at == last_created_at,
                            self.model_type.id < last_id
                        )
                    )
                )
            
            # Apply expiration filter if needed
            if not include_expired:
                now = datetime.utcnow()
                query = query.where(
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
                
            # Order and limit
            query = query.order_by(desc(self.model_type.created_at), desc(self.model_type.id)).limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving recent URLs with keyset pagination: {e}") from e
    
    async def get_top_urls_keyset(
        self,
        db: AsyncSession,
        limit: int = 10,
        last_click_count: Optional[int] = None,
        last_id: Optional[int] = None,
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get top URLs by click count using keyset pagination.
        
        This is more efficient than offset pagination for deep result sets.
        
        Args:
            db: Database session
            limit: Maximum number of URLs to return
            last_click_count: Click count of the last URL from previous page
            last_id: ID of the last URL from previous page
            include_expired: Whether to include expired URLs
            
        Returns:
            List of ShortURL entities ordered by click count (descending)
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(self.model_type)
            
            # Apply keyset pagination if we have a previous page cursor
            if last_click_count is not None and last_id is not None:
                query = query.where(
                    or_(
                        self.model_type.click_count < last_click_count,
                        and_(
                            self.model_type.click_count == last_click_count,
                            self.model_type.id < last_id
                        )
                    )
                )
            
            # Apply expiration filter if needed
            if not include_expired:
                now = datetime.utcnow()
                query = query.where(
                    or_(
                        self.model_type.expires_at.is_(None),
                        self.model_type.expires_at > now
                    )
                )
                
            # Order and limit
            query = query.order_by(desc(self.model_type.click_count), desc(self.model_type.id)).limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            raise RepositoryError(f"Error retrieving top URLs with keyset pagination: {e}") from e 