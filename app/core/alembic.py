"""Alembic migration utilities and helpers.

This module provides utilities for working with Alembic migrations
in the URL shortener application. It serves as a central place for
migration-related functionality and best practices documentation.
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Project paths
ALEMBIC_DIR = Path(__file__).resolve().parent.parent.parent / "alembic"
ALEMBIC_INI = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def run_migrations(offline: bool = False) -> None:
    """Run all pending Alembic migrations.
    
    This is a helper function that can be called during application startup
    to ensure the database schema is up to date. It is safe to use in all
    environments, including production.
    
    Args:
        offline: If True, generate SQL statements instead of executing them
    """
    try:
        import alembic.config
        alembic_args = [
            "-c", str(ALEMBIC_INI),
            "upgrade", "head",
        ]
        
        if offline:
            alembic_args.append("--sql")
            
        alembic_cfg = alembic.config.Config(str(ALEMBIC_INI))
        alembic.command.upgrade(alembic_cfg, "head")
        logger.info("Successfully applied Alembic migrations")
    except ImportError:
        logger.error(
            "Alembic is not installed. Cannot run migrations. "
            "Install with: pip install alembic"
        )
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise


def create_migration(message: str) -> Optional[str]:
    """Create a new Alembic migration revision.
    
    This function should be used to create new migrations when making
    schema changes, rather than directly modifying the database schema.
    
    Args:
        message: Description of the migration (used in the revision name)
        
    Returns:
        str: Path to the new migration file, or None if creation failed
    """
    try:
        import alembic.config
        
        # Clean the message to make it a valid filename part
        clean_message = message.lower().replace(" ", "_")
        
        alembic_cfg = alembic.config.Config(str(ALEMBIC_INI))
        result = alembic.command.revision(
            alembic_cfg,
            message=clean_message,
            autogenerate=True
        )
        
        logger.info(f"Created new migration: {result}")
        return result
    except ImportError:
        logger.error(
            "Alembic is not installed. Cannot create migration. "
            "Install with: pip install alembic"
        )
    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        raise
    
    return None


def get_current_revision() -> Optional[str]:
    """Get the current Alembic revision of the database.
    
    Returns:
        str: Current revision identifier or None if it cannot be determined
    """
    try:
        import alembic.config
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine, text
        
        # Create a temporary connection to check the current revision
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
        
        return current_rev
    except ImportError:
        logger.error(
            "Alembic is not installed. Cannot get current revision. "
            "Install with: pip install alembic"
        )
    except Exception as e:
        logger.error(f"Failed to get current revision: {e}")
    
    return None


def get_migration_history() -> List[dict]:
    """Get the history of applied migrations.
    
    Returns:
        List[dict]: List of migration records with revision ID, timestamp, and description
    """
    try:
        import alembic.config
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine, text
        
        history = []
        
        # Create a temporary connection to check migration history
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
        with engine.connect() as conn:
            # Get data from alembic_version table
            result = conn.execute(text("SELECT * FROM alembic_version"))
            current_rev = result.fetchone()[0] if result.rowcount > 0 else None
            
            if current_rev:
                # Get script directory to access revision information
                alembic_cfg = alembic.config.Config(str(ALEMBIC_INI))
                script_directory = alembic.script.ScriptDirectory.from_config(alembic_cfg)
                
                # Start with current revision and work backwards
                revision = script_directory.get_revision(current_rev)
                while revision:
                    history.append({
                        "revision": revision.revision,
                        "down_revision": revision.down_revision,
                        "timestamp": getattr(revision, "timestamp", None),
                        "description": revision.doc,
                    })
                    # Move to parent revision
                    if revision.down_revision:
                        revision = script_directory.get_revision(revision.down_revision)
                    else:
                        revision = None
        
        return history
    except ImportError:
        logger.error(
            "Alembic is not installed. Cannot get migration history. "
            "Install with: pip install alembic"
        )
    except Exception as e:
        logger.error(f"Failed to get migration history: {e}")
    
    return []


# Functions below are generally not needed directly but provided for completeness
def downgrade(target: str = "-1") -> None:
    """Downgrade the database schema to a previous version.
    
    WARNING: This is potentially destructive and should be used with caution,
    especially in production environments.
    
    Args:
        target: Target revision (default: one step back)
    """
    try:
        import alembic.config
        alembic_cfg = alembic.config.Config(str(ALEMBIC_INI))
        alembic.command.downgrade(alembic_cfg, target)
        logger.info(f"Successfully downgraded to {target}")
    except ImportError:
        logger.error(
            "Alembic is not installed. Cannot downgrade. "
            "Install with: pip install alembic"
        )
    except Exception as e:
        logger.error(f"Failed to downgrade: {e}")
        raise 