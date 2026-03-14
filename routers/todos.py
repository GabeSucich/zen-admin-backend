from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db import Todo, CalendarEventClientSuggestion
from models.constants import TodoSource, TodoType
from schemas import TodoResponse, CreateTodoRequest, UpdateTodoRequest, ChangeDueDateRequest
from utils.error_logging import log_error_to_db

router = APIRouter(prefix="/todos", tags=["Todos"])


async def _get_todo_with_client(db: AsyncSession, todo_id: int) -> Todo | None:
    result = await db.execute(
        select(Todo)
        .where(Todo.id == todo_id)
        .options(selectinload(Todo.client))
    )
    return result.scalar_one_or_none()


@router.get("/confirmed", response_model=list[TodoResponse])
@log_error_to_db
async def get_confirmed_todos(
    due_before_or_on: str | None = Query(default=None),
    is_completed: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return todos where the associated CalendarEventClientSuggestion is None or user_confirmed=True."""
    query = (
        select(Todo)
        .outerjoin(CalendarEventClientSuggestion)
        .where(
            or_(
                Todo.cal_event_client_suggestion_id.is_(None),
                CalendarEventClientSuggestion.user_confirmed == True,
            )
        )
        .options(selectinload(Todo.client))
        .order_by(Todo.due_date.asc(), Todo.created_at.asc())
    )

    if due_before_or_on is not None:
        cutoff = date.fromisoformat(due_before_or_on)
        query = query.where(Todo.due_date <= cutoff)

    if is_completed is True:
        query = query.where(Todo.completed_at.is_not(None))
    elif is_completed is False:
        query = query.where(Todo.completed_at.is_(None))

    result = await db.execute(query)
    return [TodoResponse.from_model(t) for t in result.scalars().all()]


@router.get("/{todo_id}", response_model=TodoResponse)
@log_error_to_db
async def get_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    todo = await _get_todo_with_client(db, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.from_model(todo)


@router.post("/", response_model=TodoResponse)
@log_error_to_db
async def create_todo(data: CreateTodoRequest, db: AsyncSession = Depends(get_db)):
    todo = Todo(
        client_id=data.client_id,
        cal_event_client_suggestion_id=data.cal_event_client_suggestion_id,
        title=data.title,
        notes=data.notes,
        due_date=data.due_date,
        source=TodoSource.MANUAL,
        todo_type=data.todo_type,
    )
    db.add(todo)
    await db.commit()
    todo = await _get_todo_with_client(db, todo.id)
    return TodoResponse.from_model(todo)


@router.patch("/{todo_id}", response_model=TodoResponse)
@log_error_to_db
async def update_todo(todo_id: int, data: UpdateTodoRequest, db: AsyncSession = Depends(get_db)):
    todo = await _get_todo_with_client(db, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(todo, field, value)

    await db.commit()
    todo = await _get_todo_with_client(db, todo_id)
    return TodoResponse.from_model(todo)


@router.post("/{todo_id}/complete", response_model=TodoResponse)
@log_error_to_db
async def mark_todo_complete(todo_id: int, db: AsyncSession = Depends(get_db)):
    todo = await _get_todo_with_client(db, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    todo.completed_at = datetime.now(tz=timezone.utc)
    await db.commit()
    todo = await _get_todo_with_client(db, todo_id)
    return TodoResponse.from_model(todo)


@router.post("/{todo_id}/change-due-date", response_model=TodoResponse)
@log_error_to_db
async def change_due_date(
    todo_id: int,
    data: ChangeDueDateRequest,
    db: AsyncSession = Depends(get_db),
):
    todo = await _get_todo_with_client(db, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    todo.due_date = data.due_date
    await db.commit()
    todo = await _get_todo_with_client(db, todo_id)
    return TodoResponse.from_model(todo)


@router.delete("/{todo_id}")
@log_error_to_db
async def delete_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Todo).where(Todo.id == todo_id))
    todo = result.scalar_one_or_none()
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    await db.delete(todo)
    await db.commit()
    return {"detail": "Todo deleted"}
