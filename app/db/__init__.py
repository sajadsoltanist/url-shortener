"""Database module for the URL shortener application."""
from app.db.base import engine, get_engine, DatabaseHealthCheck
from app.db.session import get_db, db_transaction, SessionManager, db_dependency

# Resilience imports are commented out for now
# from app.db.resilience import (
#     initialize_database_connection,
#     circuit_breaker,
#     get_db_with_circuit_breaker,
#     db_circuit_breaker,
#     CircuitBreakerError
# )

__all__ = [
    "engine",
    "get_engine",
    "DatabaseHealthCheck",
    "get_db",
    "db_transaction",
    "SessionManager",
    "db_dependency",
    # Resilience features are temporarily disabled but code is preserved
    # "initialize_database_connection",
    # "circuit_breaker",
    # "get_db_with_circuit_breaker",
    # "db_circuit_breaker",
    # "CircuitBreakerError",
]
