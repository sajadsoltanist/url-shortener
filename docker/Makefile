.PHONY: help build build-dev up up-dev down down-dev ps logs logs-db logs-redis logs-api test lint clean prune migrate makemigrations shell shell-db shell-redis restart stop setup db-backup db-restore

# Colors for terminal output
COLOR_RESET = \033[0m
COLOR_BOLD = \033[1m
COLOR_GREEN = \033[32m
COLOR_YELLOW = \033[33m
COLOR_BLUE = \033[34m
COLOR_CYAN = \033[36m

# Show help
help: ## Display this help
	@echo ""
	@echo "${COLOR_BOLD}URL Shortener Docker Commands${COLOR_RESET}"
	@echo ""
	@echo "${COLOR_BOLD}Usage:${COLOR_RESET}"
	@echo "  make ${COLOR_GREEN}<command>${COLOR_RESET}"
	@echo ""
	@echo "${COLOR_BOLD}Available commands:${COLOR_RESET}"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${COLOR_GREEN}%-25s${COLOR_RESET} %s\n", $$1, $$2}'
	@echo ""

# Build commands
build: ## Build production Docker images
	docker compose -f docker/docker-compose.yaml build

build-dev: ## Build development Docker images
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml build

# Run commands
up: ## Start production environment
	docker compose -f docker/docker-compose.yaml up -d
	@echo "${COLOR_CYAN}URL Shortener is running in production mode!${COLOR_RESET}"
	@echo "${COLOR_CYAN}API is available at http://localhost:8000${COLOR_RESET}"

up-dev: ## Start development environment with hot reloading
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml up -d
	@echo "${COLOR_CYAN}URL Shortener is running in development mode!${COLOR_RESET}"
	@echo "${COLOR_CYAN}API is available at http://localhost:8000${COLOR_RESET}"
	@echo "${COLOR_CYAN}pgAdmin is available at http://localhost:5050${COLOR_RESET}"

down: ## Stop production environment
	docker compose -f docker/docker-compose.yaml down

down-dev: ## Stop development environment
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml down

ps: ## Show running containers
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml ps

# Log commands
logs: ## View logs from all containers
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml logs -f

logs-api: ## View API logs
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml logs -f api

logs-db: ## View database logs
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml logs -f db

logs-redis: ## View Redis logs
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml logs -f redis

# Testing and linting
test: ## Run tests
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec api pytest

lint: ## Run linting
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec api flake8

# Cleanup commands
clean: down ## Stop and remove containers
	@echo "${COLOR_YELLOW}Removing containers...${COLOR_RESET}"

prune: clean ## Remove all containers, volumes and images (DESTRUCTIVE!)
	@echo "${COLOR_YELLOW}WARNING: This will remove all unused containers, networks, volumes and images...${COLOR_RESET}"
	@echo "${COLOR_YELLOW}Are you sure? [y/N] ${COLOR_RESET}" && read ans && [ $${ans:-N} = y ]
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml down -v
	docker system prune -af

# Database commands
migrate: ## Run database migrations
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec api alembic upgrade head

makemigrations: ## Create a new migration
	@echo "${COLOR_BLUE}Creating migration with message: $(m)${COLOR_RESET}"
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec api alembic revision --autogenerate -m "$(m)"

db-backup: ## Backup database
	@mkdir -p ./backups
	@echo "${COLOR_BLUE}Backing up database to ./backups/backup-$$(date +'%Y%m%d-%H%M%S').sql${COLOR_RESET}"
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec db pg_dump -U postgres url_shortener > ./backups/backup-$$(date +'%Y%m%d-%H%M%S').sql

db-restore: ## Restore database from a backup file (usage: make db-restore file=./backups/backup.sql)
	@echo "${COLOR_BLUE}Restoring database from $(file)${COLOR_RESET}"
	@test -f $(file) || (echo "${COLOR_YELLOW}Error: Backup file $(file) not found${COLOR_RESET}" && exit 1)
	cat $(file) | docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec -T db psql -U postgres url_shortener

# Shell access
shell: ## Open a shell in the API container
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec api bash

shell-db: ## Open a PostgreSQL shell
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec db psql -U postgres url_shortener

shell-redis: ## Open a Redis CLI shell
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml exec redis redis-cli

# Additional commands
restart: ## Restart all containers
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml restart

stop: ## Stop all containers without removing them
	docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml stop

setup: ## Initial setup (build and start development environment)
	@echo "${COLOR_BLUE}Setting up URL Shortener development environment...${COLOR_RESET}"
	make build-dev
	make up-dev
	@echo "${COLOR_BLUE}Running initial migrations...${COLOR_RESET}"
	sleep 5  # Wait for services to start
	make migrate
	@echo "${COLOR_GREEN}Setup complete! URL Shortener is now running.${COLOR_RESET}"
	@echo "${COLOR_CYAN}API is available at http://localhost:8000${COLOR_RESET}"
	@echo "${COLOR_CYAN}pgAdmin is available at http://localhost:5050${COLOR_RESET}"

# Default command shows help 