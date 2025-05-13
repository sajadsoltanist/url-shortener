"""Health check endpoints for monitoring application status."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import time
import os
import sys
import asyncio

from app.core.config import settings
from app.db.session import get_db
from app.core.redis import redis_manager

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Get system health status",
    response_description="Health status of all system components"
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check health of all system components."""
    health_status = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time(),
        "components": {}
    }
    
    # Check database connection
    try:
        # Simple query to verify DB connection
        result = await db.execute(text("SELECT 1"))
        await db.commit()
        if result.scalar_one() == 1:
            health_status["components"]["database"] = {
                "status": "healthy",
                "latency_ms": 0  # We'll calculate this below
            }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Redis connection if enabled
    if redis_manager.is_enabled:
        try:
            # Measure Redis ping latency
            start_time = time.time()
            result = await redis_manager.ping()
            end_time = time.time()
            
            if result:
                latency = round((end_time - start_time) * 1000, 2)
                health_status["components"]["redis"] = {
                    "status": "healthy",
                    "latency_ms": latency
                }
            else:
                health_status["status"] = "degraded"
                health_status["components"]["redis"] = {
                    "status": "unhealthy",
                    "error": "Redis ping failed"
                }
        except Exception as e:
            health_status["status"] = "degraded"
            health_status["components"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
    
    # Check disk space
    try:
        total, used, free = os.statvfs(os.getcwd()).f_frsize, os.statvfs(os.getcwd()).f_blocks, os.statvfs(os.getcwd()).f_bfree
        disk_usage_percent = (used - free) / used * 100
        health_status["components"]["disk"] = {
            "status": "healthy" if disk_usage_percent < 90 else "warning",
            "usage_percent": round(disk_usage_percent, 2),
            "free_mb": round(free * os.statvfs(os.getcwd()).f_frsize / (1024 * 1024), 2)
        }
        if disk_usage_percent > 90:
            health_status["status"] = "degraded"
    except Exception:
        # Ignore disk space errors
        pass
    
    # Return appropriate status code based on overall health
    return health_status


@router.get(
    "/health/ready",
    status_code=status.HTTP_200_OK, 
    summary="Readiness probe",
    response_description="Application readiness status"
)
async def readiness_probe(db: AsyncSession = Depends(get_db)):
    """Check if application is ready to handle requests."""
    # Check critical components needed for the application to function
    components_status = {"api": True, "database": False}
    
    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        await db.commit()
        components_status["database"] = result.scalar_one() == 1
    except Exception:
        components_status["database"] = False
    
    # Overall readiness status
    is_ready = all(components_status.values())
    
    return {
        "ready": is_ready,
        "components": components_status
    }


@router.get(
    "/health/live", 
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    response_description="Application liveness status"
)
async def liveness_probe():
    """Simple check that application is running."""
    return {"alive": True} 