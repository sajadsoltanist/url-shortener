"""Session management for database operations.

This module provides utilities for handling SQLAlchemy async sessions
with proper lifecycle management, error handling, and transaction support.
It includes dependency injection patterns optimized for FastAPI.
"""

from typing import AsyncGenerator, Callable, Optional, TypeVar, Any, Dict, List
import logging
import inspect
from contextlib import asynccontextmanager
from functools import wraps

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import async_session_factory, get_session

logger = logging.getLogger(__name__)

# Generic return type for function decorators
T = TypeVar("T")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.
    
    This is the primary dependency to inject a database session into route handlers.
    It properly manages the session lifecycle, handling cleanup even in case of exceptions.
    
    Yields:
        AsyncSession: A SQLAlchemy async session object.
    
    Example:
        ```python
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            # Use the session for database operations
            return await repository.get_all(db)
        ```
    """
    async with get_session() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.exception("Database error occurred")
            await session.rollback()
            raise
        except Exception as e:
            logger.exception("Unexpected error during database session")
            await session.rollback()
            raise


def db_transaction(db_param_name: Optional[str] = None) -> Callable:
    """Decorator to wrap functions in a database transaction.
    
    Automatically finds the database session parameter, commits on success or 
    rolls back on error. This decorator uses function signature inspection to
    reliably identify the database session parameter based on type annotations.
    
    Args:
        db_param_name: Optional name of the database session parameter.
            If provided, will look for a parameter with this name.
            If not provided, will look for any parameter annotated as AsyncSession.
            The recommended convention is to always name database session parameters 'db'.
    
    Returns:
        Callable: Decorator function
        
    Example:
        ```python
        # Standard usage - will automatically find the parameter annotated as AsyncSession
        @db_transaction()
        async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
            user = User(**user_data.dict())
            db.add(user)
            return user
            
        # Explicitly specifying the parameter name
        @db_transaction(db_param_name="session")
        async def update_user(user_id: int, session: AsyncSession, user_data: UserUpdate) -> User:
            user = await session.get(User, user_id)
            for key, value in user_data.dict(exclude_unset=True).items():
                setattr(user, key, value)
            return user
        ```
    
    Raises:
        ValueError: If no suitable database session parameter is found
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Cache the session parameter information to avoid repeated inspection
        # during each function call for better performance
        func_signature = inspect.signature(func)
        parameters = func_signature.parameters
        db_param_pos = None
        db_param_key = None
        
        # Look for the database session parameter in the function signature
        for i, (param_name, param) in enumerate(parameters.items()):
            # Check if the parameter is annotated as AsyncSession
            annotation = param.annotation
            is_async_session = (
                annotation is AsyncSession or
                (hasattr(annotation, "__origin__") and AsyncSession in getattr(annotation, "__args__", []))
            )
            
            # If a specific parameter name is provided, check for match
            if db_param_name and param_name == db_param_name:
                if not is_async_session:
                    logger.warning(
                        f"Parameter '{db_param_name}' in function '{func.__name__}' is not annotated "
                        f"as AsyncSession. This may cause type-related issues."
                    )
                db_param_pos = i
                db_param_key = param_name
                break
            
            # If no specific name provided, use the first AsyncSession parameter
            elif is_async_session and db_param_name is None:
                db_param_pos = i
                db_param_key = param_name
                break
        
        # If no parameter was found, log the issue for debugging
        if db_param_pos is None and db_param_key is None:
            param_info = ", ".join(f"{name}: {param.annotation}" for name, param in parameters.items())
            logger.warning(
                f"Unable to find database session parameter in function '{func.__name__}'. "
                f"Available parameters: {param_info}"
            )
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Strategy to find the database session:
            # 1. Try to find it via the predetermined position in args
            # 2. Try to find it via the predetermined key in kwargs
            # 3. Fall back to searching through args and kwargs by type
            
            db = None
            
            # 1. Check if the db parameter is in args at the predetermined position
            if db_param_pos is not None and len(args) > db_param_pos:
                db = args[db_param_pos]
            
            # 2. Check if the db parameter is in kwargs with the predetermined key
            elif db_param_key is not None and db_param_key in kwargs:
                db = kwargs[db_param_key]
            
            # 3. Fallback: search for any AsyncSession in args or kwargs
            else:
                # Search in args
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        db = arg
                        break
                
                # Search in kwargs
                if db is None:
                    for key, value in kwargs.items():
                        if isinstance(value, AsyncSession):
                            db = value
                            break
            
            # If no database session is found, raise an error
            if db is None:
                raise ValueError(
                    f"Database session not found in function arguments for '{func.__name__}'. "
                    f"Ensure a parameter of type AsyncSession is passed to the function. "
                    f"Consider using a consistent parameter name (e.g., 'db') for clarity."
                )
                
            # Execute the function within a transaction
            try:
                result = await func(*args, **kwargs)
                await db.commit()
                return result
            except Exception as e:
                await db.rollback()
                logger.exception(f"Transaction failed in '{func.__name__}': {e}")
                raise
                
        return wrapper
    return decorator


class SessionManager:
    """Session manager for managing database operations with context manager support.
    
    Provides a higher-level API for session management with automatic transaction handling.
    """
    
    @staticmethod
    @asynccontextmanager
    async def transaction_context() -> AsyncGenerator[AsyncSession, None]:
        """Context manager for a database session with transaction support.
        
        Automatically commits on successful completion or rolls back on error.
        
        Yields:
            AsyncSession: SQLAlchemy async session
            
        Example:
            ```python
            async with SessionManager.transaction_context() as session:
                # Operations within this block will be in a transaction
                user = User(name="John Doe", email="john@example.com")
                session.add(user)
                # Commits automatically on context exit if no errors
            ```
        """
        async with get_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.exception(f"Transaction failed: {e}")
                raise
    
    @staticmethod
    async def execute_in_transaction(
        operation: Callable[[AsyncSession], T],
        session: Optional[AsyncSession] = None
    ) -> T:
        """Execute a database operation within a transaction.
        
        Args:
            operation: Callable that takes a session and performs database operations
            session: Optional existing session (creates a new one if not provided)
            
        Returns:
            The result of the operation
            
        Example:
            ```python
            async def add_user(session, user_data):
                user = User(**user_data)
                session.add(user)
                return user
            
            new_user = await SessionManager.execute_in_transaction(
                lambda session: add_user(session, {"name": "Jane"})
            )
            ```
        """
        if session:
            # Use existing session
            try:
                result = await operation(session)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
        else:
            # Create new session
            async with SessionManager.transaction_context() as new_session:
                return await operation(new_session)


# Provide the session dependency as a shorthand for FastAPI routes
db_dependency = Depends(get_db)
