from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.constants import MeetingType
from models.db import MeetingTypeTodoTemplates
from schemas import MeetingTypeResponse, MeetingTypeTodoTemplateResponse

router = APIRouter(prefix="/meeting-types", tags=["MeetingTypes"])


@router.get("/", response_model=list[MeetingTypeResponse])
async def get_meeting_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MeetingTypeTodoTemplates).order_by(MeetingTypeTodoTemplates.order)
    )
    templates = result.scalars().all()

    templates_by_type: dict[MeetingType, list[MeetingTypeTodoTemplateResponse]] = {
        mt: [] for mt in MeetingType
    }
    for t in templates:
        templates_by_type[t.meeting_type].append(MeetingTypeTodoTemplateResponse.from_model(t))

    return [
        MeetingTypeResponse(meeting_type=mt, templates=templates_by_type[mt])
        for mt in MeetingType
    ]
