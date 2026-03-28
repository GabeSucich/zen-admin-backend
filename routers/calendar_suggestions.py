from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy import func

from database import get_db
from models.db import CalendarEvent, CalendarEventClientSuggestion, Client, Todo
from schemas import CalendarEventClientSuggestionResponse, ConfirmSuggestionRequest
from utils.error_logging import log_error_to_db
from utils.todo_builder import build_todos_from_client_meeting

router = APIRouter(prefix="/calendar-suggestions", tags=["CalendarSuggestions"])


@router.get("/all", response_model=list[CalendarEventClientSuggestionResponse])
@log_error_to_db
async def get_all_suggestions(
    since: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all CalendarEventClientSuggestions for events before the given timestamp."""
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .join(CalendarEvent)
        .where(CalendarEvent.start_time >= since)
        .order_by(CalendarEvent.start_time.asc())
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos).selectinload(Todo.client),
            selectinload(CalendarEventClientSuggestion.cal_event),
        )
    )
    suggestions = result.scalars().all()
    return [CalendarEventClientSuggestionResponse.from_model(s) for s in suggestions]


@router.get("/", response_model=list[CalendarEventClientSuggestionResponse])
@log_error_to_db
async def get_unconfirmed_suggestions(
    db: AsyncSession = Depends(get_db),
):
    """Fetch all unconfirmed CalendarEventClientSuggestions with client and todos."""
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .join(CalendarEvent)
        .where(CalendarEventClientSuggestion.user_confirmed == False)
        .order_by(CalendarEvent.start_time.asc())
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos).selectinload(Todo.client),
            selectinload(CalendarEventClientSuggestion.cal_event),
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
            selectinload(CalendarEventClientSuggestion.todos).selectinload(Todo.client),
            selectinload(CalendarEventClientSuggestion.cal_event),
        )
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Determine the final client_id
    final_client_id = data.replacement_client_id if data.replacement_client_id is not None else suggestion.client_id

    if final_client_id is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot confirm a suggestion without a client. Provide a replacement_client_id.",
        )

    if data.replacement_client_id is not None:
        # Archive old client if it was unconfirmed
        if suggestion.client and not suggestion.client.user_confirmed:
            suggestion.client.archived = True

        suggestion.client_id = data.replacement_client_id

    # Confirm the suggestion and its associated client
    suggestion.user_confirmed = True
    final_client = await db.get(Client, final_client_id)
    if final_client:
        final_client.user_confirmed = True

    # Set meeting type from request
    suggestion.meeting_type = data.meeting_type

    # Delete existing todos and regenerate
    for todo in list(suggestion.todos):
        await db.delete(todo)
    await db.flush()

    # Create todos from templates for this meeting type
    todos = await build_todos_from_client_meeting(
        db=db,
        client_id=final_client_id,
        suggestion_id=suggestion.id,
        meeting_type=data.meeting_type,
        today=date.today(),
    )
    for todo in todos:
        db.add(todo)

    await db.commit()

    # Reload to return fresh data (populate_existing to refresh expired identity-mapped objects)
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .where(CalendarEventClientSuggestion.id == suggestion_id)
        .options(
            selectinload(CalendarEventClientSuggestion.client),
            selectinload(CalendarEventClientSuggestion.todos).selectinload(Todo.client),
            selectinload(CalendarEventClientSuggestion.cal_event),
        )
        .execution_options(populate_existing=True)
    )
    suggestion = result.scalar_one_or_none()
    return CalendarEventClientSuggestionResponse.from_model(suggestion)


@router.delete("/{suggestion_id}")
@log_error_to_db
async def delete_calendar_suggestion(
    suggestion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar suggestion and its todos. Deletes the client if no other references exist."""
    result = await db.execute(
        select(CalendarEventClientSuggestion)
        .where(CalendarEventClientSuggestion.id == suggestion_id)
        .options(selectinload(CalendarEventClientSuggestion.todos))
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    client_id = suggestion.client_id

    # Delete associated todos
    for todo in list(suggestion.todos):
        await db.delete(todo)

    await db.delete(suggestion)
    await db.flush()

    # Archive the client if no other todos or suggestions reference it
    if client_id is not None:
        other_todos = await db.execute(
            select(func.count()).select_from(Todo).where(Todo.client_id == client_id)
        )
        other_suggestions = await db.execute(
            select(func.count()).select_from(CalendarEventClientSuggestion)
            .where(CalendarEventClientSuggestion.client_id == client_id)
        )
        if other_todos.scalar() == 0 and other_suggestions.scalar() == 0:
            client = await db.get(Client, client_id)
            if client:
                client.archived = True

    await db.commit()
    return {"detail": "Suggestion deleted"}
