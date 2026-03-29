from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import ErrorListResponse, ErrorResponse
from models.db import Error

router = APIRouter(prefix="/errors", tags=["Errors"])


@router.get("", response_model=ErrorListResponse)
async def list_errors(
    page_size: int = Query(default=10, ge=1, le=100),
    cursor: int | None = Query(default=None),
    since: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ErrorListResponse:
    query = (
        select(Error)
        .order_by(Error.created_at.desc(), Error.id.desc())
    )

    if since is not None:
        since_utc = since.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(Error.created_at > since_utc)

    if cursor is not None:
        query = query.where(Error.id < cursor)

    query = query.limit(page_size + 1)

    results = (await db.execute(query)).scalars().all()

    if len(results) > page_size:
        items = results[:page_size]
        next_cursor = items[-1].id
    else:
        items = results
        next_cursor = None

    return ErrorListResponse(
        items=[ErrorResponse.model_validate(r) for r in items],
        next_cursor=next_cursor,
    )
