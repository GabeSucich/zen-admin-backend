from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db import CalendarEventClientSuggestion, Client, Todo
from schemas import CalendarEventClientSuggestionResponse, ConfirmSuggestionRequest
from utils.error_logging import log_error_to_db

router = APIRouter(prefix="/calendar-suggestions", tags=["CalendarSuggestions"])


@router.get("/", response_model=list[CalendarEventClientSuggestionResponse])
@log_error_to_db
async def get_unconfirmed_suggestions(
    db: AsyncSession = Depends(get_db),
):
    """Fetch all unconfirmed CalendarEventClientSuggestions with client and todos."""
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .where(CalendarEventClientSuggestion.user_confirmed == False)
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos),
        )
    )
    suggestions = result.scalars().all()
    return [CalendarEventClientSuggestionResponse.from_model(s) for s in suggestions]


@router.post("/{suggestion_id}/confirm", response_model=CalendarEventClientSuggestionResponse)
@log_error_to_db
async def confirm_suggestion(
    suggestion_id: int,
    data: ConfirmSuggestionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm a calendar event client suggestion, optionally replacing the client."""
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .where(CalendarEventClientSuggestion.id == suggestion_id)
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos),
        )
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if data.replacement_client_id is not None:
        # Reassign todos to the replacement client
        for todo in suggestion.todos:
            todo.client_id = data.replacement_client_id

        # Archive old client if it was unconfirmed
        old_client = suggestion.client
        if not old_client.user_confirmed:
            old_client.archived = True

        suggestion.user_confirmed = True
    else:
        # Confirm the suggestion and its associated client
        suggestion.client.user_confirmed = True
        suggestion.user_confirmed = True

    await db.commit()

    # Reload to return fresh data
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .where(CalendarEventClientSuggestion.id == suggestion_id)
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos),
        )
    )
    suggestion = result.scalar_one_or_none()
    return CalendarEventClientSuggestionResponse.from_model(suggestion)
