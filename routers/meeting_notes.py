import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import CalendarEventMeetingNotes, ProcessMeetingNotesLog
from models.constants import MeetingNotesSource
from schemas import ConfirmMeetingNotesRequest, IngestGranolaNotesRequest, IngestGranolaNotesResponse, GranolaMeetingNotesResponse, ArchiveMeetingNotesRequest, ActionItemsResponse
from services.granola_notes_service import GranolaNotesService
from utils.openai_helpers import extract_granola_meeting_action_items

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-notes", tags=["MeetingNotes"])

class GetGranolaNotesForEventResponse(BaseModel):
    notes: GranolaMeetingNotesResponse | None

@router.get("/granola/calendar-event/{calendar_event_id}", response_model=GetGranolaNotesForEventResponse)
async def get_granola_notes_for_event(
    calendar_event_id: int,
    db: AsyncSession = Depends(get_db),
) -> GetGranolaNotesForEventResponse:
    result = await db.execute(
        select(CalendarEventMeetingNotes)
        .where(
            CalendarEventMeetingNotes.calendar_event_id == calendar_event_id,
            CalendarEventMeetingNotes.source == MeetingNotesSource.GRANOLA,
            CalendarEventMeetingNotes.archived == False,
        )
        .order_by(desc(CalendarEventMeetingNotes.id))
        .limit(1)
    )
    notes = result.scalar_one_or_none()
    if not notes:
        return GetGranolaNotesForEventResponse(
            notes=None
        )
    return GetGranolaNotesForEventResponse(
        notes=GranolaMeetingNotesResponse.model_validate(notes)
    )


@router.post("/granola/confirm", response_model=GranolaMeetingNotesResponse)
async def confirm_granola_notes(
    data: ConfirmMeetingNotesRequest,
    db: AsyncSession = Depends(get_db),
) -> GranolaMeetingNotesResponse:
    notes = await db.get(CalendarEventMeetingNotes, data.meeting_notes_id)
    if not notes:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    notes.user_confirmed = True
    await db.commit()
    await db.refresh(notes)
    return GranolaMeetingNotesResponse.model_validate(notes)


@router.post("/granola/archive", response_model=GranolaMeetingNotesResponse)
async def archive_granola_note(
    data: ArchiveMeetingNotesRequest,
    db: AsyncSession = Depends(get_db),
) -> GranolaMeetingNotesResponse:
    notes = await db.get(CalendarEventMeetingNotes, data.meeting_notes_id)
    if not notes:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    notes.archived = True
    await db.commit()
    await db.refresh(notes)
    return GranolaMeetingNotesResponse.model_validate(notes)


@router.get("/granola/{meeting_notes_id}/action-items", response_model=ActionItemsResponse)
async def get_granola_action_items(
    meeting_notes_id: int,
    db: AsyncSession = Depends(get_db),
) -> ActionItemsResponse:
    notes = await db.get(CalendarEventMeetingNotes, meeting_notes_id)
    if not notes or notes.source != MeetingNotesSource.GRANOLA:
        raise HTTPException(status_code=404, detail="Granola meeting notes not found")
    content = notes.notes_markdown if notes.notes_markdown else notes.notes_text
    result = await extract_granola_meeting_action_items(content)
    return ActionItemsResponse(action_items=result.action_items)


@router.post("/granola/ingest", response_model=IngestGranolaNotesResponse)
async def ingest_granola_notes(
    data: IngestGranolaNotesRequest,
    db: AsyncSession = Depends(get_db)
) -> IngestGranolaNotesResponse:
    # Rate limit: check most recent ProcessMeetingNotesLog
    result = await db.execute(
        select(ProcessMeetingNotesLog).order_by(desc(ProcessMeetingNotesLog.id)).limit(1)
    )
    last_log = result.scalar_one_or_none()
    if last_log and last_log.created_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) - timedelta(minutes=2):
        raise HTTPException(status_code=429, detail="Cannot ingest meeting notes more frequently than every 2 minutes")
    
    # Log this invocation
    db.add(ProcessMeetingNotesLog())
    await db.commit()

    notes_service = GranolaNotesService(days_ago=data.days_ago)

    logger.info("Fetching Granola notes from the last %d days", data.days_ago)
    all_notes = await notes_service.fetch_all_notes()
    logger.info("Fetched %d notes from Granola", len(all_notes))

    # Check which note IDs already exist in the DB
    note_ids = [n.id for n in all_notes]
    result = await db.execute(
        select(CalendarEventMeetingNotes.note_id)
        .where(CalendarEventMeetingNotes.note_id.in_(note_ids))
    )
    existing_note_ids = set(result.scalars().all())

    skipped = [n for n in all_notes if n.id in existing_note_ids]
    to_process = [n for n in all_notes if n.id not in existing_note_ids]
    logger.info("Skipping %d existing notes, %d new notes to process", len(skipped), len(to_process))

    matches = await notes_service.match_notes_to_db(to_process, db)

    matched = [m for m in matches if m.calendar_event_id is not None]
    unmatched = [m for m in matches if m.calendar_event_id is None]
    logger.info("Matched %d notes to calendar events, %d unmatched", len(matched), len(unmatched))

    # For matched notes, fetch full detail concurrently and create DB records
    note_details = await asyncio.gather(
        *(notes_service.get_note(m.granola_note_id) for m in matched)
    )
    for match, note_detail in zip(matched, note_details):
        db.add(CalendarEventMeetingNotes(
            calendar_event_id=match.calendar_event_id,
            title=note_detail.title,
            note_id=match.granola_note_id,
            notes_text=note_detail.summary_text,
            notes_markdown=note_detail.summary_markdown,
            user_confirmed=False,
            source=MeetingNotesSource.GRANOLA,
        ))

    await db.commit()
    logger.info("Committed %d meeting notes records to DB", len(matched))

    return IngestGranolaNotesResponse(
        skipped_count=len(skipped),
        skipped_note_ids=[n.id for n in skipped],
        matched_count=len(matched),
        matched_note_ids=[m.granola_note_id for m in matched],
        unmatched_count=len(unmatched),
        unmatched_note_ids=[m.granola_note_id for m in unmatched],
    )
