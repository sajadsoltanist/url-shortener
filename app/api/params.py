"""Common API parameter definitions.

This module provides reusable parameter definitions for FastAPI endpoints.
"""

from fastapi import Query
from typing import Optional


def LimitParam(default: int = 20) -> int:
    """
    Common limit parameter for pagination.
    
    Args:
        default: Default limit value
        
    Returns:
        A Query parameter with validation
    """
    return Query(
        default, 
        ge=1, 
        le=100, 
        description="Number of records to return"
    )


def SkipParam(default: int = 0) -> int:
    """
    Common skip parameter for pagination.
    
    Args:
        default: Default skip value
        
    Returns:
        A Query parameter with validation
    """
    return Query(
        default, 
        ge=0, 
        description="Number of records to skip"
    ) 