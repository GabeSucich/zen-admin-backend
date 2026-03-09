from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.constants import MeetingType, TodoSource
from models.db import MeetingTypeTodoTemplates, Todo


async def build_todos_from_client_meeting(
    db: AsyncSession,
    client_id: int | None,
    suggestion_id: int,
    meeting_type: MeetingType,
    today: date,
) -> list[Todo]:
    """Build Todo(s) from MeetingTypeTodoTemplates for the given meeting type."""
    result = await db.execute(
        select(MeetingTypeTodoTemplates)
        .where(MeetingTypeTodoTemplates.meeting_type == meeting_type)
        .order_by(MeetingTypeTodoTemplates.order)
    )
    templates = result.scalars().all()

    return [
        Todo(
            client_id=client_id,
            cal_event_client_suggestion_id=suggestion_id,
            title=template.title,
            notes=template.notes,
            due_date=today + timedelta(days=template.days_until_due),
            source=TodoSource.AUTO,
            todo_type=template.todo_type,
        )
        for template in templates
    ]
