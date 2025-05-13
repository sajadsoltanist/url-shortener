# URL Shortener Docker Setup

This directory contains Docker configuration files for the URL Shortener application.

## Directory Structure

- `Dockerfile`: Multi-stage build configuration for the application container
- `docker-compose.yaml`: Production deployment configuration
- `docker-compose.dev.yaml`: Development configuration with hot reloading
- `entrypoint.sh`: Container entrypoint script with initialization logic
- `Makefile`: Helper commands for development and deployment

## Key Features

- **Multi-stage builds** to separate build and runtime environments
- **Dependency caching** for faster builds
- **Health checks** for all services
- **Non-root users** for improved security
- **Automatic migrations** on startup
- **Graceful shutdown** handling
- **Service dependency** management with health checks
- **Volume management** for persistent storage
- **Development environment** with hot reloading
- **Comprehensive Makefile** with helpful commands

## Environment Configuration

The containers are configured primarily via environment variables. Key variables include:

### Database Configuration
- `DATABASE_HOST`: PostgreSQL hostname (default: `db`)
- `DATABASE_PORT`: PostgreSQL port (default: `5432`) 
- `DATABASE_USER`: PostgreSQL username (default: `postgres`)
- `DATABASE_PASSWORD`: PostgreSQL password (default: `postgres`)
- `DATABASE_NAME`: PostgreSQL database name (default: `url_shortener`)

### Redis Configuration
- `REDIS_HOST`: Redis hostname (default: `redis`)
- `REDIS_PORT`: Redis port (default: `6379`)

### Application Configuration
- `ENVIRONMENT`: Deployment environment (`development`, `staging`, `production`)
- `DEBUG`: Enable debug mode (`true`, `false`)
- `LOG_LEVEL`: Logging level (`debug`, `info`, `warning`, `error`, `critical`)
- `API_PREFIX`: API route prefix (default: `/api`)
- `SECRET_KEY`: Secret key for security

## Getting Started

The easiest way to work with this setup is using the included Makefile commands:

```bash
# Show all available commands
make help

# Set up development environment
make setup

# Start development environment
make up-dev

# Run database migrations
make migrate

# View logs
make logs

# Stop everything
make down-dev
```

## Development vs Production

The setup includes separate configurations for development and production:

### Development (`docker-compose.dev.yaml`)
- Hot reloading of code changes
- Exposed ports for direct database access
- Database utilities (pgAdmin)
- Mounted volumes for direct code editing

### Production (`docker-compose.yaml`)
- Optimized performance
- Minimal image size
- Security hardening
- Volume persistence 