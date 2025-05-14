
### 📄 `README.md`


# 🔗 URL Shortener – Python FastAPI Interview Task

This is a simple, scalable URL shortening service built with **FastAPI**, **SQLModel**, and **Alembic**.

This project is part of a technical interview process and is designed to showcase:
- Clean architecture & maintainable code
- Performance & scalability considerations
- Logging and observability practices
- Experience with SQLAlchemy / SQLModel, Alembic, and REST APIs

---

## 🧩 Features

- Create short URLs (`POST /shorten`)
- Redirect to original URL (`GET /{short_code}`)
- Track and view visit statistics (`GET /stats/{short_code}`)
- Custom logging with middleware
- Modular and scalable codebase structure

---

## 🚀 Getting Started

### Option 1: Using Docker (Recommended)

The application comes with a fully configured Docker setup:

```bash
# Show available commands
make help

# Quick setup for development
make setup

# Access the API at http://localhost:8000/docs
```

### Option 2: Manual Setup

#### 1. Clone the repo

```bash
git clone https://github.com/mahdimmr/url-shortener.git
cd url-shortener
```

#### 2. Create virtual environment & install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

#### 3. Setup the database

> By default, it uses PostgreSQL, Look at in `sample.env` PG_DSN.

```bash
cp sample.env .env
alembic upgrade head
```

#### 4. Run the app

```bash
uvicorn app.main:app --reload
```

Open your browser at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🐳 Docker Setup

The project includes a comprehensive Docker setup with both production and development configurations:

### Key Features

- **Multi-stage builds** for optimized container images
- **Automatic database migrations** on startup
- **Health checks** for service dependencies
- **Development mode** with hot reloading
- **Comprehensive Makefile** with helpful commands

### Makefile Commands

```bash
# Show all available commands
make help

# Development
make build-dev    # Build development images
make up-dev       # Start development environment
make logs         # View logs from all containers
make shell        # Open a shell in the API container
make migrate      # Run database migrations

# Production
make build        # Build production images 
make up           # Start production environment
make down         # Stop production environment
```

For more details, see the [Docker README](docker/README.md).

---

## 🧪 Running Tests

```bash
# Using Docker
make test

# Manually
pytest
```

---

## 📁 Project Structure

```
app/
├── api/           # FastAPI routers
├── core/          # Configuration, shared utilities
├── db/            # Models, session, CRUD, migrations
├── middleware/    # Logging or custom middleware
├── main.py        # FastAPI app entrypoint

docker/            # Docker configuration files
├── Dockerfile     # Multi-stage build configuration
├── docker-compose.yaml
├── docker-compose.dev.yaml
├── entrypoint.sh  # Container initialization script
├── Makefile       # Helper commands
```

---

## 📌 Notes for Interviewers

- The implementation is scoped to take ~1 working day.
- Logging is implemented using a custom middleware.
- Visit tracking is minimal; can be extended to store timestamps/user-agent/etc.
- Add any modules, files, or dependencies you find necessary.
- In short: you're free to treat this as a real project.
- For production: add rate limiting, background jobs for analytics, async DB access, etc.
- We're more interested in how you think and structure your work than in having one "correct" answer. Good luck, and
  enjoy the process!

---

## 🧠 Bonus Ideas (if you have time)

- Custom short code support
- Expiration time for URLs
- Admin dashboard to view top URLs
- Dockerfile & deployment configs

---

# URL Shortener with Non-Blocking Redis Logging

A URL shortening service built with FastAPI, SQLModel, PostgreSQL, and Redis.

## Logging System Architecture

This application features a high-performance, non-blocking logging middleware designed for production environments:

### Key Features

- **Completely Non-Blocking**: Logging operations have zero impact on request latency
- **Redis-Backed Message Queue**: Uses Redis for storing log messages before processing
- **Structured Logging with Loguru**: Rich, structured log output with proper rotation and retention
- **Batch Processing**: Efficient batch processing of logs for optimal performance
- **Rich Contextual Data**: Captures detailed request information for comprehensive logging
- **Graceful Degradation**: Automatic fallback to local memory queue when Redis is unavailable

### Architecture

1. **Middleware Layer**: 
   - Captures request/response data
   - Publishes to Redis queue without blocking
   - Falls back to local queue when Redis is unavailable

2. **Worker Process**:
   - Consumes logs from Redis in batches
   - Efficiently writes logs to files using Loguru
   - Handles reconnections and retries when Redis is down

3. **Redis Connection Management**:
   - Connection pooling for optimal performance
   - Automatic reconnection with exponential backoff
   - Health monitoring and recovery

## Running the Application

### With Docker Compose

```bash
# Start all services (API, Redis, DB)
make up-dev

# Check logs
make logs
```

### Configuration

Key environment variables:

```
# Redis Logging Settings
REDIS_LOGGING_ENABLED=true            # Enable/disable Redis logging
REDIS_LOGGING_QUEUE=app:logs          # Redis queue name
REDIS_LOGGING_BATCH_SIZE=100          # Batch size for log processing
REDIS_LOGGING_FLUSH_INTERVAL=5.0      # Max seconds between batch flushes
REDIS_LOGGING_FALLBACK_LOCAL=true     # Enable fallback to local memory
```

## Log File Configuration

Logs are written to:
- Location: `./logs/app.log`
- Format: JSON (structured logging)
- Rotation: 10MB file size
- Retention: 7 days

## Implementation Details

The logging system follows SOLID principles:

- **Single Responsibility**: Each component handles one aspect of logging
- **Open/Closed**: Components are extensible without modification
- **Liskov Substitution**: Proper abstractions for logging interfaces
- **Interface Segregation**: Focused interfaces for logging operations
- **Dependency Inversion**: Dependencies are injected for flexibility

---
