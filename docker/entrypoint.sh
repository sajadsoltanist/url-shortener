#!/bin/bash
set -e

# Print message with timestamp
log() {
    echo "$(date +"%Y-%m-%d %H:%M:%S") - $1"
}

# Function to wait for PostgreSQL to be ready
wait_for_postgres() {
    log "Waiting for PostgreSQL to be ready..."
    
    # Use PGPASSWORD environment variable for authentication
    export PGPASSWORD="$DATABASE_PASSWORD"
    
    # Wait for PostgreSQL to be ready
    until psql -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" -c '\q'; do
        log "PostgreSQL is unavailable - sleeping 2 seconds"
        sleep 2
    done
    
    log "PostgreSQL is up and ready!"
}

# Function to wait for Redis to be ready
wait_for_redis() {
    log "Waiting for Redis to be ready..."
    
    # Wait for Redis to be ready
    until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -q "PONG"; do
        log "Redis is unavailable - sleeping 2 seconds"
        sleep 2
    done
    
    log "Redis is up and ready!"
}

# Function to run database migrations
run_migrations() {
    log "Running database migrations..."
    
    # Run Alembic migrations
    alembic upgrade head
    
    log "Migrations completed successfully!"
}

# Function to handle graceful shutdown
graceful_shutdown() {
    log "Received shutdown signal, shutting down gracefully..."
    kill -TERM "$child" 2>/dev/null
    wait "$child"
    log "Application shut down."
    exit 0
}

# Set up trap for graceful shutdown
trap graceful_shutdown SIGTERM SIGINT

# Check if database host is set, otherwise skip waiting
if [ -n "$DATABASE_HOST" ]; then
    wait_for_postgres
    run_migrations
else
    log "DATABASE_HOST not set, skipping database checks and migrations"
fi

# Check if Redis host is set, otherwise skip waiting
if [ -n "$REDIS_HOST" ]; then
    wait_for_redis
else
    log "REDIS_HOST not set, skipping Redis checks"
fi

# Start application based on provided command or default to uvicorn
log "Starting application..."
if [ "$1" = "uvicorn" ] || [ -z "$1" ]; then
    # Default command if none provided
    uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@" &
else
    # Run whatever command was provided
    exec "$@" &
fi

child=$!
wait "$child" 