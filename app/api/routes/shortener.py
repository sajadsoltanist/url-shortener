from fastapi import APIRouter, Depends, HTTPException, Path, Query, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import schemas
from app.db.session import get_db, db_transaction
from app.api.dependencies import get_shortener_service, get_stats_service, get_base_url
from app.services.shortener import ShortenedURLService
from app.services.stats import StatsService
from app.services.exceptions import (
    URLNotFoundError,
    URLExpiredError,
    InvalidURLError,
    CustomCodeAlreadyExistsError,
    CustomCodeValidationError,
    URLCreationError,
)
from typing import Optional
from datetime import datetime
from app.api.params import LimitParam, SkipParam

router = APIRouter(tags=["shortener"])


@router.post(
    "/shorten",
    response_model=schemas.URLResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": schemas.ErrorResponse, "description": "Invalid URL or custom code"},
        409: {"model": schemas.ErrorResponse, "description": "Custom code already exists"}
    }
)
@db_transaction()
async def create_short_url(
    url_data: schemas.URLCreateRequest,
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    base_url: str = Depends(get_base_url)
):
    try:
        url = await shortener_service.create_short_url(
            db=db,
            original_url=url_data.original_url,
            custom_code=url_data.custom_code,
            expiration_days=url_data.expiration_days
        )
        short_url = f"{base_url}/{url.short_code}"
        return schemas.URLResponse(
            short_code=url.short_code,
            original_url=url.original_url,
            short_url=short_url,
            created_at=url.created_at,
            expires_at=url.expires_at,
            is_custom=url.is_custom,
            click_count=url.click_count
        )
    except InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CustomCodeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CustomCodeAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except URLCreationError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/urls",
    response_model=schemas.URLListResponse
)
@db_transaction()
async def list_urls(
    skip: int = SkipParam(),
    limit: int = LimitParam(),
    include_expired: bool = Query(False, description="Include expired URLs"),
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    base_url: str = Depends(get_base_url)
):
    urls = await shortener_service.get_urls_list(
        db=db,
        skip=skip,
        limit=limit,
        include_expired=include_expired
    )
    url_responses = []
    for url in urls:
        short_url = f"{base_url}/{url.short_code}"
        url_responses.append(schemas.URLResponse(
            short_code=url.short_code,
            original_url=url.original_url,
            short_url=short_url,
            created_at=url.created_at,
            expires_at=url.expires_at,
            is_custom=url.is_custom,
            click_count=url.click_count
        ))
    return schemas.URLListResponse(
        urls=url_responses,
        page_count=len(url_responses)
    )


@router.get(
    "/urls/paginated",
    response_model=schemas.URLListResponse
)
@db_transaction()
async def list_urls_keyset(
    limit: int = LimitParam(),
    last_created_at: Optional[datetime] = Query(None, description="Timestamp of the last URL from previous page"),
    last_id: Optional[int] = Query(None, description="ID of the last URL from previous page"),
    include_expired: bool = Query(False, description="Include expired URLs"),
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    base_url: str = Depends(get_base_url)
):
    """
    Get paginated list of URLs using efficient keyset pagination.
    
    For the first page, omit last_created_at and last_id.
    For subsequent pages, provide values from the last item of the previous page.
    """
    urls = await shortener_service.get_urls_list_keyset(
        db=db,
        limit=limit,
        last_created_at=last_created_at,
        last_id=last_id,
        include_expired=include_expired
    )
    url_responses = []
    for url in urls:
        short_url = f"{base_url}/{url.short_code}"
        url_responses.append(schemas.URLResponse(
            short_code=url.short_code,
            original_url=url.original_url,
            short_url=short_url,
            created_at=url.created_at,
            expires_at=url.expires_at,
            is_custom=url.is_custom,
            click_count=url.click_count
        ))
    return schemas.URLListResponse(
        urls=url_responses,
        page_count=len(url_responses)
    )


@router.get(
    "/urls/top/paginated",
    response_model=schemas.URLListResponse
)
@db_transaction()
async def list_top_urls_keyset(
    limit: int = LimitParam(10),
    last_click_count: Optional[int] = Query(None, description="Click count of the last URL from previous page"),
    last_id: Optional[int] = Query(None, description="ID of the last URL from previous page"),
    include_expired: bool = Query(False, description="Include expired URLs"),
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    base_url: str = Depends(get_base_url)
):
    """
    Get top URLs by click count using efficient keyset pagination.
    
    For the first page, omit last_click_count and last_id.
    For subsequent pages, provide values from the last item of the previous page.
    """
    urls = await shortener_service.get_top_urls_keyset(
        db=db,
        limit=limit,
        last_click_count=last_click_count,
        last_id=last_id,
        include_expired=include_expired
    )
    url_responses = []
    for url in urls:
        short_url = f"{base_url}/{url.short_code}"
        url_responses.append(schemas.URLResponse(
            short_code=url.short_code,
            original_url=url.original_url,
            short_url=short_url,
            created_at=url.created_at,
            expires_at=url.expires_at,
            is_custom=url.is_custom,
            click_count=url.click_count
        ))
    return schemas.URLListResponse(
        urls=url_responses,
        page_count=len(url_responses)
    )


@router.get(
    "/urls/{short_code}",
    response_model=schemas.URLResponse,
    responses={
        404: {"model": schemas.ErrorResponse, "description": "URL not found"},
        410: {"model": schemas.ErrorResponse, "description": "URL has expired"}
    }
)
@db_transaction()
async def get_url_info(
    short_code: str = Path(..., description="The short code of the URL"),
    db: AsyncSession = Depends(get_db),
    shortener_service: ShortenedURLService = Depends(get_shortener_service),
    base_url: str = Depends(get_base_url)
):
    try:
        url_info = await shortener_service.get_url_info(db, short_code)
        short_url = f"{base_url}/{short_code}"
        return schemas.URLResponse(
            short_code=url_info["short_code"],
            original_url=url_info["original_url"],
            short_url=short_url,
            created_at=url_info["created_at"],
            expires_at=url_info["expires_at"],
            is_custom=url_info["is_custom"],
            click_count=url_info["click_count"]
        )
    except URLNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except URLExpiredError as e:
        raise HTTPException(status_code=410, detail=str(e))


@router.get(
    "/urls/{short_code}/stats",
    response_model=schemas.URLStatsResponse,
    responses={
        404: {"model": schemas.ErrorResponse, "description": "URL not found"}
    }
)
@db_transaction()
async def get_url_stats(
    short_code: str = Path(..., description="The short code of the URL"),
    timeframe: schemas.Timeframe = Query(
        schemas.Timeframe.DAILY,
        description="Time aggregation: daily, weekly, monthly"
    ),
    days: int = Query(30, description="Number of days to include in stats", ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    stats_service: StatsService = Depends(get_stats_service)
):
    try:
        stats = await stats_service.get_url_stats(
            db=db,
            short_code=short_code,
            timeframe=timeframe.value,
            days=days
        )
        return stats
    except URLNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
 