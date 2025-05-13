"""URL shortening service for the URL shortener application.

This module contains the ShortenedURLService class which implements business logic
for URL shortening, retrieval, and management.
"""

import logging
import random
import re
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.url import ShortURL, ShortURLUpdate
from app.repositories.url_repository import URLRepository
from app.repositories.base import RepositoryError, DuplicateEntityError, EntityNotFoundError
from app.services.exceptions import (
    InvalidURLError,
    URLCreationError,
    CustomCodeAlreadyExistsError,
    CustomCodeValidationError,
    ShortCodeGenerationError,
    URLNotFoundError,
    URLExpiredError,
    URLUpdateError,
)
from app.core.config import settings
from app.db.session import db_transaction

logger = logging.getLogger(__name__)


class ShortenedURLService:
    """
    Service for URL shortening business logic.
    
    This service handles URL shortening operations including short code generation,
    URL creation, retrieval, and validation.
    """
    
    def __init__(self, url_repository: URLRepository):
        """
        Initialize the URL shortening service.
        
        Args:
            url_repository: Repository for URL data access
        """
        self.url_repository = url_repository
    
    # TODO: Add idempotency support to URL creation
    # To implement truly idempotent URL creation, we would need to:
    # 1. Accept an optional idempotency key parameter
    # 2. Check for existing URLs with the same original URL and parameters
    # 3. Return the existing URL if found instead of creating a new one
    # 4. This would prevent duplicate entries when the same URL is shortened
    #    multiple times with the same parameters
    @db_transaction(db_param_name="db")
    async def create_short_url(
        self,
        db: AsyncSession,
        original_url: str,
        custom_code: Optional[str] = None,
        expiration_days: Optional[int] = None
    ) -> ShortURL:
        """
        Create a shortened URL with optional custom code and expiration.
        
        Args:
            db: Database session
            original_url: The original URL to shorten
            custom_code: Optional custom code for the shortened URL
            expiration_days: Optional number of days until expiration
            
        Returns:
            ShortURL: The created shortened URL
            
        Raises:
            InvalidURLError: If URL format is invalid
            CustomCodeValidationError: If custom code format is invalid
            CustomCodeAlreadyExistsError: If custom code is already in use
            ShortCodeGenerationError: If a unique short code cannot be generated
            URLCreationError: If URL creation fails for other reasons
        """
        # Ensure original_url is a string
        if hasattr(original_url, '__str__'):
            original_url = str(original_url)
            
        # Validate URL format
        if not self._is_valid_url(original_url):
            raise InvalidURLError(f"Invalid URL format: {original_url}")
        
        # Handle custom code or generate a new one
        if custom_code:
            # Validate custom code format
            if not self._is_valid_custom_code(custom_code):
                raise CustomCodeValidationError(
                    f"Custom code '{custom_code}' does not meet requirements. "
                    f"Must be {settings.URL_CUSTOM_CODE_MAX_LENGTH} chars or less, "
                    f"containing only letters, numbers, and hyphens."
                )
            
            try:
                # Check if code already exists
                if await self.url_repository.check_short_code_exists(db, custom_code):
                    raise CustomCodeAlreadyExistsError(f"Custom code '{custom_code}' is already in use")
                short_code = custom_code
            except RepositoryError as e:
                logger.error(f"Error checking if custom code exists: {e}")
                raise URLCreationError(f"Failed to validate custom code: {str(e)}")
        else:
            # Try to generate a unique code, increasing length if needed
            try:
                short_code = await self._generate_unique_short_code(db)
            except ShortCodeGenerationError as e:
                logger.error(f"Failed to generate short code: {e}")
                raise
        
        # Set expiration date if provided
        expires_at = ShortURL.generate_expiration(expiration_days)
        
        # Create URL data
        url_data = {
            "original_url": original_url,
            "short_code": short_code,
            "expires_at": expires_at,
            "is_custom": bool(custom_code)
        }
        
        # Create URL in repository
        try:
            return await self.url_repository.create_short_url(db, url_data)
        except DuplicateEntityError as e:
            logger.error(f"Duplicate entity error: {e}")
            raise CustomCodeAlreadyExistsError(f"Short code '{short_code}' is already in use")
        except RepositoryError as e:
            logger.error(f"Error creating short URL: {e}")
            raise URLCreationError(f"Failed to create short URL: {str(e)}")
    
    async def get_url_by_code(self, db: AsyncSession, short_code: str) -> ShortURL:
        """
        Retrieve a URL by its short code with a single database call.
        
        Args:
            db: Database session
            short_code: The short code to look up
            
        Returns:
            ShortURL: The found URL object
            
        Raises:
            URLNotFoundError: If no URL with this code exists
            URLExpiredError: If the URL exists but has expired
        """
        try:
            # Get the URL with a single call - no separate active check
            url = await self.url_repository.get_by_short_code(db, short_code)
            
            if not url:
                raise URLNotFoundError(f"URL with code '{short_code}' not found")
            
            # Check expiration in-memory after retrieval
            if url.is_expired():
                raise URLExpiredError(f"URL with code '{short_code}' has expired")
            
            return url
        except RepositoryError as e:
            logger.error(f"Error retrieving URL by code: {e}")
            raise URLNotFoundError(f"Failed to retrieve URL with code '{short_code}'")
    
    async def get_url_for_redirect(self, db: AsyncSession, short_code: str) -> Dict[str, Any]:
        """
        Retrieve minimal URL data needed for redirection with optimized query.
        
        Args:
            db: Database session
            short_code: The short code to look up
            
        Returns:
            Dict containing original_url and id
            
        Raises:
            URLNotFoundError: If no URL with this code exists
            URLExpiredError: If the URL exists but has expired
        """
        try:
            # Use optimized repository method that only retrieves needed columns
            url_data = await self.url_repository.get_short_url_for_redirect(db, short_code)
            
            if not url_data:
                # Check if URL exists but is expired
                url = await self.url_repository.get_by_short_code(db, short_code)
                if url and url.is_expired():
                    raise URLExpiredError(f"URL with code '{short_code}' has expired")
                else:
                    raise URLNotFoundError(f"URL with code '{short_code}' not found")
            
            return url_data
        except RepositoryError as e:
            logger.error(f"Error retrieving URL for redirect: {e}")
            raise URLNotFoundError(f"Failed to retrieve URL with code '{short_code}'")
    
    @db_transaction(db_param_name="db")
    async def update_url(
        self, 
        db: AsyncSession, 
        short_code: str, 
        update_data: Dict[str, Any]
    ) -> ShortURL:
        """
        Update properties of an existing URL.
        
        Args:
            db: Database session
            short_code: The short code of the URL to update
            update_data: Dictionary of fields to update
            
        Returns:
            ShortURL: The updated URL
            
        Raises:
            URLNotFoundError: If no URL with this code exists
            URLUpdateError: If the update operation fails
            InvalidURLError: If the updated original_url is invalid
        """
        try:
            # Get the URL to update
            url = await self.url_repository.get_by_short_code(db, short_code)
            if not url:
                raise URLNotFoundError(f"URL with code '{short_code}' not found")
            
            # Validate updated original_url if provided
            if "original_url" in update_data and not self._is_valid_url(update_data["original_url"]):
                raise InvalidURLError(f"Invalid URL format: {update_data['original_url']}")
            
            # Create a proper update model
            update_model = ShortURLUpdate(**update_data)
            
            # Perform the update
            updated_url = await self.url_repository.update(db, url.id, update_model)
            if not updated_url:
                raise URLUpdateError(f"Failed to update URL with code '{short_code}'")
            
            return updated_url
        except (RepositoryError, EntityNotFoundError) as e:
            logger.error(f"Error updating URL: {e}")
            raise URLUpdateError(f"Failed to update URL: {str(e)}")
    
    async def get_url_info(self, db: AsyncSession, short_code: str) -> Dict[str, Any]:
        """
        Get detailed information about a shortened URL.
        
        Args:
            db: Database session
            short_code: The short code to look up
            
        Returns:
            Dict: Information about the URL
            
        Raises:
            URLNotFoundError: If no URL with this code exists
        """
        url = await self.get_url_by_code(db, short_code)
        
        # Create a dictionary with URL information
        is_expired = url.is_expired()
        expiration_status = "expired" if is_expired else (
            "never" if url.expires_at is None else "active"
        )
        
        time_left = None
        if url.expires_at and not is_expired:
            time_left = (url.expires_at - datetime.utcnow()).total_seconds()
        
        return {
            "id": url.id,
            "original_url": url.original_url,
            "short_code": url.short_code,
            "created_at": url.created_at,
            "expires_at": url.expires_at,
            "is_custom": url.is_custom,
            "click_count": url.click_count,
            "is_expired": is_expired,
            "expiration_status": expiration_status,
            "time_left_seconds": time_left,
        }
    
    @db_transaction(db_param_name="db")
    async def delete_url(self, db: AsyncSession, short_code: str) -> bool:
        """
        Delete a shortened URL by its code.
        
        Args:
            db: Database session
            short_code: The short code of the URL to delete
            
        Returns:
            bool: True if deleted, False otherwise
            
        Raises:
            URLNotFoundError: If no URL with this code exists
            URLUpdateError: If the delete operation fails
        """
        try:
            # Get the URL to delete
            url = await self.url_repository.get_by_short_code(db, short_code)
            if not url:
                raise URLNotFoundError(f"URL with code '{short_code}' not found")
            
            # Delete the URL
            deleted = await self.url_repository.delete(db, url.id)
            if not deleted:
                raise URLUpdateError(f"Failed to delete URL with code '{short_code}'")
            
            return True
        except RepositoryError as e:
            logger.error(f"Error deleting URL: {e}")
            raise URLUpdateError(f"Failed to delete URL: {str(e)}")
    
    async def get_urls_list(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get a paginated list of shortened URLs.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            include_expired: Whether to include expired URLs
            
        Returns:
            List[ShortURL]: List of shortened URLs
        """
        try:
            if include_expired:
                return await self.url_repository.get_all(
                    db, skip=skip, limit=limit
                )
            else:
                # Only get non-expired URLs
                return await self.url_repository.get_recent_urls(
                    db, limit=limit, include_expired=False
                )
        except RepositoryError as e:
            logger.error(f"Error retrieving URLs list: {e}")
            return []
    
    async def get_urls_list_keyset(
        self,
        db: AsyncSession,
        limit: int = 20,
        last_created_at: Optional[datetime] = None,
        last_id: Optional[int] = None,
        include_expired: bool = False
    ) -> List[ShortURL]:
        """
        Get a paginated list of shortened URLs using keyset pagination.
        
        This is more efficient than offset pagination for deep result sets.
        
        Args:
            db: Database session
            limit: Maximum number of records to return
            last_created_at: Timestamp of the last URL from previous page
            last_id: ID of the last URL from previous page
            include_expired: Whether to include expired URLs
            
        Returns:
            List[ShortURL]: List of shortened URLs
        """
        try:
            return await self.url_repository.get_recent_urls_keyset(
                db, limit, last_created_at, last_id, include_expired
            )
        except RepositoryError as e:
            logger.error(f"Error retrieving URLs list with keyset pagination: {e}")
            return []
    
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
            List[ShortURL]: List of top URLs
        """
        try:
            return await self.url_repository.get_top_urls(
                db, limit, include_expired
            )
        except RepositoryError as e:
            logger.error(f"Error retrieving top URLs: {e}")
            return []
    
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
            List[ShortURL]: List of top URLs
        """
        try:
            return await self.url_repository.get_top_urls_keyset(
                db, limit, last_click_count, last_id, include_expired
            )
        except RepositoryError as e:
            logger.error(f"Error retrieving top URLs with keyset pagination: {e}")
            return []
    
    async def _generate_unique_short_code(self, db: AsyncSession) -> str:
        """
        Generate a unique short code that isn't already in use.
        
        Args:
            db: Database session
            
        Returns:
            str: A unique short code
            
        Raises:
            ShortCodeGenerationError: If unable to generate a unique code
        """
        max_attempts = 3  # Number of length increases to try
        for attempt in range(max_attempts):
            length = settings.URL_CODE_LENGTH + attempt  # Increase length on subsequent attempts
            for _ in range(5):  # Try 5 times at each length
                candidate_code = self._generate_short_code(length)
                exists = await self.url_repository.check_short_code_exists(db, candidate_code)
                if not exists:
                    return candidate_code
        
        # If we get here, we couldn't generate a unique code
        raise ShortCodeGenerationError(
            "Failed to generate unique short code after multiple attempts. "
            "Try again later or use a custom code."
        )
    
    def _generate_short_code(self, length: int = 6) -> str:
        """
        Generate a random short code of specified length.
        
        Uses a mix of lowercase letters, uppercase letters, and digits for maximum
        information density while maintaining readability.
        
        Args:
            length: Length of the code to generate
            
        Returns:
            str: A random short code
        """
        chars = settings.URL_CODE_CHARS
        if not chars:
            chars = string.ascii_letters + string.digits
            
        return ''.join(random.choice(chars) for _ in range(length))
    
    def _is_valid_url(self, url) -> bool:
        """
        Check if a URL is valid.
        
        Args:
            url: URL to validate (can be string or Pydantic HttpUrl)
            
        Returns:
            bool: True if the URL is valid, False otherwise
        """
        # Convert to string if it's a Pydantic HttpUrl object
        url_str = str(url)
        
        # Simple URL validation regex
        # This is a basic check, might want to use a library like validators for production
        pattern = r'^(https?|ftp)://'  # Ensure URL starts with http://, https://, or ftp://
        pattern += r'([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?'  # domain
        pattern += r'(/[a-zA-Z0-9._~:/?#[\]@!$&\'()*+,;=%-]*)?$'  # path, query, fragment
        
        return bool(re.match(pattern, url_str))
    
    def _is_valid_custom_code(self, code: str) -> bool:
        """
        Check if a custom short code is valid.
        
        Args:
            code: Custom code to validate
            
        Returns:
            bool: True if the code is valid, False otherwise
        """
        # Check length
        if not code or len(code) > settings.URL_CUSTOM_CODE_MAX_LENGTH:
            return False
        
        # Check allowed characters (letters, numbers, hyphens)
        pattern = r'^[a-zA-Z0-9-]+$'
        return bool(re.match(pattern, code)) 