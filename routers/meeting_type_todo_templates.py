from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import MeetingTypeTodoTemplates
from schemas import (
    MeetingTypeTodoTemplateResponse,
    CreateMeetingTypeTodoTemplateRequest,
    UpdateMeetingTypeTodoTemplateRequest,
)
from utils.error_logging import log_error_to_db

router = APIRouter(prefix="/meeting-type-todo-templates", tags=["MeetingTypeTodoTemplates"])


@router.get("/", response_model=list[MeetingTypeTodoTemplateResponse])
@log_error_to_db
async def list_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MeetingTypeTodoTemplates).order_by(
            MeetingTypeTodoTemplates.meeting_type,
            MeetingTypeTodoTemplates.order,
        )
    )
    return [MeetingTypeTodoTemplateResponse.from_model(t) for t in result.scalars().all()]


@router.post("/", response_model=MeetingTypeTodoTemplateResponse)
@log_error_to_db
async def create_template(
    data: CreateMeetingTypeTodoTemplateRequest,
    db: AsyncSession = Depends(get_db),
):
    template = MeetingTypeTodoTemplates(**data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return MeetingTypeTodoTemplateResponse.from_model(template)


@router.patch("/{template_id}", response_model=MeetingTypeTodoTemplateResponse)
@log_error_to_db
async def update_template(
    template_id: int,
    data: UpdateMeetingTypeTodoTemplateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MeetingTypeTodoTemplates).where(MeetingTypeTodoTemplates.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)
    return MeetingTypeTodoTemplateResponse.from_model(template)


@router.delete("/{template_id}")
@log_error_to_db
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MeetingTypeTodoTemplates).where(MeetingTypeTodoTemplates.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.commit()
    return {"detail": "Template deleted"}
