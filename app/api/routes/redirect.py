"""URL redirection endpoint with click tracking."""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api.dependencies import get_shortener_service, get_stats_service
from app.db.session import get_db, db_transaction, SessionManager
from app.services.shortener import ShortenedURLService
from app.services.stats import StatsService
from app.services.exceptions import URLNotFoundError, URLExpiredError
from app.core.decorators import log_url_access_decorator

# Create router with tags
router = APIRouter(tags=["redirect"])


async def track_click(
    stats_service: StatsService,
    short_code: str,
    ip_address: str = None,
    user_agent: str = None
):
    """Track click events in a separate database session.
    
    Args:
        stats_service: Statistics service instance
        short_code: Short code that was clicked
        ip_address: Client IP address
        user_agent: Client user agent string
    """
    # Create a new database session for the background task
    async with SessionManager.transaction_context() as db:
        try:
            await stats_service.track_click(
                db=db,
                short_code=short_code,
                ip_address=ip_address,
                user_agent=user_agent
            )
        except Exception as e:
            # Log but don't fail the request
            logger.error(f"Error tracking click", short_code=short_code, error=str(e))


@router.get(
    "/{short_code}",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT
)
@db_transaction()
@log_url_access_decorator()
async def redirect_to_original_url(
    request: Request,
    background_tasks: BackgroundTasks,
    short_code: str,
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Redirect to original URL and track click as background task."""
    try:
        # Get the URL
        url = await shortener_service.get_url_by_code(db, short_code)
        
        # Extract tracking information from request
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        # URL access logging is now handled by the decorator
        
        # Add click tracking as a background task - don't pass the db session
        background_tasks.add_task(
            track_click,
            stats_service,
            short_code,
            ip_address,
            user_agent
        )
        
        # Return redirect to original URL
        return RedirectResponse(url=url.original_url)
        
    except URLNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except URLExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redirect error: {str(e)}") 