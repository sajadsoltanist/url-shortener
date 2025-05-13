"""Scheduler implementation for the URL shortener application.

This module provides a scheduler service that manages background tasks
like cleanup of expired URLs using APScheduler.
"""

import logging
from datetime import datetime
import os
import asyncio
from typing import Optional, Dict, Any, List, Callable
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_session
from app.services.cleanup import CleanupService
from app.repositories.url_repository import URLRepository

# No longer using Redis-based log processing
# Logging is now handled by Loguru directly

logger = logging.getLogger(__name__)


# Standalone context manager for database sessions
@asynccontextmanager
async def get_db_session():
    """
    Get a database session for use in scheduled jobs.
    
    This uses the application's session factory to create a session
    with proper lifecycle management.
    
    Yields:
        AsyncSession: An async database session
    """
    async with get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error in scheduled job: {e}", exc_info=True)
            raise


# Standalone function for cleanup job
async def cleanup_expired_urls_job():
    """
    Job to cleanup expired URLs.
    
    This is a standalone function that gets scheduled.
    It creates its own database session and repository instances.
    """
    logger.info("Starting scheduled cleanup of expired URLs")
    try:
        # Get a new session for this job
        async with get_db_session() as session:
            logger.debug(f"Acquired database session for cleanup job: {session}")
            # Create repository and service for this job
            url_repository = URLRepository()
            cleanup_service = CleanupService(url_repository)
            
            # Execute the cleanup
            result = await cleanup_service.cleanup_expired_urls(db=session)
            
            logger.info(f"Scheduled cleanup completed: Processed={result.get('processed', 0)}, Deleted={result.get('deleted', 0)}, Errors={result.get('errors', 0)}")
            return result
    except Exception as e:
        logger.error(f"Error in scheduled URL cleanup job: {e}", exc_info=True)
        # Return error information
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class SchedulerService:
    """
    Scheduler service for managing background tasks.
    
    This service provides a wrapper around APScheduler to handle
    scheduling and execution of background tasks like URL cleanup.
    """
    
    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.is_running = False
        self.jobs: List[Dict[str, Any]] = []
    
    def initialize(self) -> None:
        """
        Initialize the scheduler.
        
        This sets up the APScheduler with appropriate job stores and executors,
        but does not start it yet.
        """
        if self.scheduler:
            logger.warning("Scheduler already initialized")
            return
        
        try:
            jobstores = {
                'default': SQLAlchemyJobStore(url=settings.SCHEDULER_JOBSTORE_URL)
            }
            
            # Let AsyncIOScheduler use its default executor suitable for asyncio
            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                job_defaults={
                    'coalesce': settings.SCHEDULER_JOB_COALESCE,  
                    'max_instances': settings.SCHEDULER_JOB_MAX_INSTANCES, 
                    'misfire_grace_time': settings.SCHEDULER_MISFIRE_GRACE_TIME  
                }
            )
            
            logger.info("Scheduler initialized successfully with default executor")
        except Exception as e:
            logger.error(f"Error initializing scheduler: {e}", exc_info=True)
            self.scheduler = None
            raise
    
    def start(self) -> None:
        """
        Start the scheduler and register jobs.
        
        This starts the scheduler and adds all configured jobs.
        """
        if not self.scheduler:
            self.initialize()
            
        if self.is_running:
            logger.warning("Scheduler already running")
            return
            
        try:
            # Add cleanup job directly as a coroutine
            self.scheduler.add_job(
                cleanup_expired_urls_job,
                trigger=IntervalTrigger(
                    hours=settings.CLEANUP_INTERVAL_HOURS,
                    timezone='UTC'
                ),
                id='cleanup_expired_urls',
                name='Cleanup Expired URLs',
                replace_existing=True
            )
            
            self.jobs.append({
                'id': 'cleanup_expired_urls',
                'name': 'Cleanup Expired URLs',
                'interval': f'{settings.CLEANUP_INTERVAL_HOURS} hours',
                'function': 'cleanup_expired_urls_job'
            })

            # Log processing job removed - now using Loguru's built-in async capabilities
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"Scheduler started with {len(self.jobs)} jobs")
            
            if settings.CLEANUP_START_ON_STARTUP:
                logger.info("Running cleanup job on startup")
                self.scheduler.add_job(
                    cleanup_expired_urls_job,
                    id='cleanup_startup',
                    name='Startup Cleanup',
                    replace_existing=True
                )
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}", exc_info=True)
            self.is_running = False
            raise
    
    def shutdown(self) -> None:
        """
        Shutdown the scheduler gracefully.
        
        This stops the scheduler and all running jobs.
        """
        if not self.scheduler or not self.is_running:
            logger.warning("Scheduler not running, nothing to shut down")
            return
            
        try:
            # Shutdown scheduler
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            self.scheduler = None
            logger.info("Scheduler shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {e}", exc_info=True)
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the scheduler.
        
        Returns:
            Dict with information about the scheduler status and jobs
        """
        job_details = []
        if self.scheduler and self.is_running:
            try:
                for job in self.scheduler.get_jobs():
                    job_details.append({
                        'job_id': job.id,
                        'name': job.name,
                        'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
                    })
            except Exception as e:
                logger.error(f"Error retrieving job details: {e}", exc_info=True)

        return {
            'running': self.is_running,
            'jobs': self.jobs,
            'scheduler_jobs_status': job_details
        }


# Create global instance of the scheduler service
scheduler_service = SchedulerService() 