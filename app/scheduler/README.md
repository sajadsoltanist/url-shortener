# URL Shortener Scheduler

This module provides background scheduled tasks for the URL shortener application using APScheduler.

## Features

- Periodic cleanup of expired URLs
- Configurable batch size and interval
- Database persistence of job information
- Graceful startup and shutdown
- Status monitoring endpoint

## Configuration

The scheduler uses the following settings from `app.core.config`:

- `CLEANUP_BATCH_SIZE`: Number of URLs to process in each batch (default: 1000)
- `CLEANUP_INTERVAL_HOURS`: How often to run the cleanup task (default: 24 hours)
- `CLEANUP_START_ON_STARTUP`: Whether to run cleanup on app startup (default: False)

## Implementation Details

### SchedulerService

The `SchedulerService` class manages the APScheduler instance and provides methods for:

1. **Initialization**: Sets up the APScheduler with job stores and executors
2. **Starting**: Starts the scheduler and registers jobs
3. **Shutdown**: Gracefully shuts down the scheduler
4. **Status**: Returns current scheduler status and job information

### Jobs

The scheduler currently includes the following jobs:

- **URL Cleanup**: Removes expired URLs from the database
  - Runs every `CLEANUP_INTERVAL_HOURS` hours
  - Processes URLs in batches of `CLEANUP_BATCH_SIZE`
  - Optional immediate execution on startup

## Monitoring

The scheduler status can be monitored via the `/api/status/scheduler` endpoint, which returns:

- Whether the scheduler is running
- List of registered jobs
- Next scheduled run times

## Error Handling

The scheduler includes comprehensive error handling:

- Job failures are logged but don't crash the application
- Database errors are caught and reported
- Graceful shutdown on application termination 