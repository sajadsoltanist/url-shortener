"""Base repository implementation for the URL shortener application.

This module provides a generic BaseRepository class that follows the Repository pattern
for database operations, serving as a foundation for more specific repositories.
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
import logging
from datetime import datetime

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

# Type variable for model types
T = TypeVar("T", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

logger = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Base exception for repository errors."""
    pass


class EntityNotFoundError(RepositoryError):
    """Exception raised when an entity cannot be found."""
    
    def __init__(self, model_type: Type[SQLModel], entity_id: Any):
        self.model_type = model_type
        self.entity_id = entity_id
        model_name = getattr(model_type, "__name__", "Entity")
        super().__init__(f"{model_name} with id {entity_id} not found")


class DuplicateEntityError(RepositoryError):
    """Exception raised when a unique constraint is violated."""
    
    def __init__(self, model_type: Type[SQLModel], field_name: str, value: Any):
        self.model_type = model_type
        self.field_name = field_name
        self.value = value
        model_name = getattr(model_type, "__name__", "Entity")
        super().__init__(f"{model_name} with {field_name}={value} already exists")


class BaseRepository(Generic[T, CreateSchemaType, UpdateSchemaType]):
    """
    Base repository implementing common CRUD operations for SQLModel entities.
    
    This generic class provides a foundation for specific repositories,
    implementing standard database operations and error handling.
    
    Type parameters:
        T: The SQLModel type this repository manages
        CreateSchemaType: The Pydantic model type for creation operations
        UpdateSchemaType: The Pydantic model type for update operations
    """
    
    def __init__(self, model_type: Type[T]):
        """
        Initialize the repository with a specific model type.
        
        Args:
            model_type: The SQLModel class this repository will work with
        """
        self.model_type = model_type
    
    async def get_by_id(self, db: AsyncSession, id: Any) -> Optional[T]:
        """
        Get an entity by its ID.
        
        Args:
            db: Database session
            id: Entity ID
            
        Returns:
            The entity if found, None otherwise
        """
        try:
            return await db.get(self.model_type, id)
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving {self.model_type.__name__} with id {id}: {e}")
            raise RepositoryError(f"Database error retrieving entity: {e}") from e
    
    async def get_by_id_or_404(self, db: AsyncSession, id: Any) -> T:
        """
        Get an entity by its ID or raise a 404 error if not found.
        
        Args:
            db: Database session
            id: Entity ID
            
        Returns:
            The entity if found
            
        Raises:
            HTTPException: If the entity is not found
        """
        entity = await self.get_by_id(db, id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model_type.__name__} with id {id} not found"
            )
        return entity
    
    async def get_all(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        order_by: Optional[Any] = None
    ) -> List[T]:
        """
        Get all entities with pagination support.
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            order_by: SQLAlchemy column to order by
            
        Returns:
            List of entities
        """
        try:
            query = select(self.model_type).offset(skip).limit(limit)
            if order_by is not None:
                query = query.order_by(order_by)
            
            result = await db.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving {self.model_type.__name__} list: {e}")
            raise RepositoryError(f"Database error retrieving entities: {e}") from e
    
    async def create(self, db: AsyncSession, data: Union[CreateSchemaType, Dict[str, Any]]) -> T:
        """
        Create a new entity.
        
        Args:
            db: Database session
            data: Entity data (either as a Pydantic model or dictionary)
            
        Returns:
            The created entity
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            # Convert Pydantic model to dict if needed
            if isinstance(data, BaseModel):
                data_dict = data.dict(exclude_unset=True)
            else:
                data_dict = data
            
            # Create the entity
            entity = self.model_type(**data_dict)
            db.add(entity)
            await db.flush()  # Flush to generate ID but don't commit yet
            
            # Refresh to get any default values or generated columns
            await db.refresh(entity)
            return entity
        except SQLAlchemyError as e:
            logger.error(f"Error creating {self.model_type.__name__}: {e}")
            await db.rollback()
            raise RepositoryError(f"Database error creating entity: {e}") from e
    
    async def update(
        self, 
        db: AsyncSession, 
        id: Any, 
        data: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> Optional[T]:
        """
        Update an existing entity.
        
        Args:
            db: Database session
            id: Entity ID
            data: Updated entity data (either as a Pydantic model or dictionary)
            
        Returns:
            The updated entity, or None if not found
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            entity = await self.get_by_id(db, id)
            if entity is None:
                return None
            
            # Convert Pydantic model to dict if needed
            if isinstance(data, BaseModel):
                data_dict = data.dict(exclude_unset=True)
            else:
                data_dict = data
            
            # Update the entity
            for key, value in data_dict.items():
                setattr(entity, key, value)
            
            await db.flush()
            await db.refresh(entity)
            return entity
        except SQLAlchemyError as e:
            logger.error(f"Error updating {self.model_type.__name__} with id {id}: {e}")
            raise RepositoryError(f"Database error updating entity: {e}") from e
    
    async def delete(self, db: AsyncSession, id: Any) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            db: Database session
            id: Entity ID
            
        Returns:
            True if entity was deleted, False if not found
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            entity = await self.get_by_id(db, id)
            if entity is None:
                return False
            
            await db.delete(entity)
            await db.flush()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model_type.__name__} with id {id}: {e}")
            raise RepositoryError(f"Database error deleting entity: {e}") from e
    
    async def count(self, db: AsyncSession) -> int:
        """
        Count the total number of entities.
        
        Args:
            db: Database session
            
        Returns:
            Total count of entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            query = select(func.count()).select_from(self.model_type)
            result = await db.execute(query)
            return result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model_type.__name__} records: {e}")
            raise RepositoryError(f"Database error counting entities: {e}") from e
    
    async def exists(self, db: AsyncSession, **kwargs) -> bool:
        """
        Check if an entity exists with the given filters.
        
        Args:
            db: Database session
            **kwargs: Field=value pairs to filter by
            
        Returns:
            True if entity exists, False otherwise
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            conditions = []
            for field, value in kwargs.items():
                conditions.append(getattr(self.model_type, field) == value)
            
            if not conditions:
                raise ValueError("No conditions provided for exists check")
            
            query = select(func.count()).select_from(self.model_type).where(*conditions)
            result = await db.execute(query)
            count = result.scalar_one()
            return count > 0
        except SQLAlchemyError as e:
            logger.error(f"Error checking existence of {self.model_type.__name__}: {e}")
            raise RepositoryError(f"Database error checking entity existence: {e}") from e
    
    async def bulk_create(self, db: AsyncSession, items: List[Union[CreateSchemaType, Dict[str, Any]]]) -> List[T]:
        """
        Create multiple entities in a single transaction.
        
        Args:
            db: Database session
            items: List of entity data (either as Pydantic models or dictionaries)
            
        Returns:
            List of created entities
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            entities = []
            for item in items:
                # Convert Pydantic model to dict if needed
                if isinstance(item, BaseModel):
                    data_dict = item.dict(exclude_unset=True)
                else:
                    data_dict = item
                
                entity = self.model_type(**data_dict)
                db.add(entity)
                entities.append(entity)
            
            await db.flush()
            return entities
        except SQLAlchemyError as e:
            logger.error(f"Error bulk creating {self.model_type.__name__} records: {e}")
            raise RepositoryError(f"Database error bulk creating entities: {e}") from e
    
    async def bulk_update(self, db: AsyncSession, filters: Dict[str, Any], data: Dict[str, Any]) -> int:
        """
        Update multiple entities matching filters.
        
        Args:
            db: Database session
            filters: Field=value pairs to filter by
            data: Field=value pairs to update
            
        Returns:
            Number of rows updated
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            conditions = []
            for field, value in filters.items():
                conditions.append(getattr(self.model_type, field) == value)
            
            if not conditions:
                raise ValueError("No conditions provided for bulk update")
            
            stmt = (
                update(self.model_type)
                .where(*conditions)
                .values(**data)
            )
            
            result = await db.execute(stmt)
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error bulk updating {self.model_type.__name__} records: {e}")
            raise RepositoryError(f"Database error bulk updating entities: {e}") from e
    
    async def bulk_delete(self, db: AsyncSession, **filters) -> int:
        """
        Delete multiple entities matching filters.
        
        Args:
            db: Database session
            **filters: Field=value pairs to filter by. 
                       If a value is a SQLAlchemy ClauseElement, it's used directly as a condition.
            
        Returns:
            Number of rows deleted
            
        Raises:
            RepositoryError: On database errors
        """
        try:
            conditions = []
            for field, value in filters.items():
                # If the value is already a SQLAlchemy ClauseElement (like an `and_` or `or_` expression),
                # use it directly. Otherwise, create an equality comparison.
                if hasattr(value, '__clause_element__') or hasattr(value, '_sa_BOOLEAN_OPERATORS'): # Check if it's a SQLAlchemy expression
                    conditions.append(value)
                else:
                    conditions.append(getattr(self.model_type, field) == value)
            
            if not conditions:
                raise ValueError("No conditions provided for bulk delete")
            
            stmt = delete(self.model_type).where(*conditions)
            result = await db.execute(stmt)
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error bulk deleting {self.model_type.__name__} records: {e}", exc_info=True)
            raise RepositoryError(f"Database error bulk deleting entities: {e}") from e 