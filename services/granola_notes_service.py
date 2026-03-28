from datetime import datetime, timedelta, timezone

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import CalendarEvent, CalendarEventMeetingNotes
from utils.env_vars import load_env_var, EnvVarName
from utils.openai_helpers import CalendarEventForMatching, GranolaNoteForMatching, NoteToEventMatch, match_notes_to_events

GRANOLA_API_KEY = load_env_var(EnvVarName.GRANOLA_API_KEY)
GRANOLA_API_BASE_URL = load_env_var(EnvVarName.GRANOLA_API_BASE_URL)


class GranolaNoteOwner(BaseModel):
    name: str
    email: str


class GranolaNote(BaseModel):
    id: str
    object: str
    title: str
    owner: GranolaNoteOwner
    created_at: datetime
    updated_at: datetime


class GranolaNoteDetail(BaseModel):
    id: str
    title: str
    owner: GranolaNoteOwner
    summary_text: str
    summary_markdown: str | None
    created_at: datetime
    updated_at: datetime


class GranolaNotesResponse(BaseModel):
    notes: list[GranolaNote]
    hasMore: bool
    cursor: str | None



class GranolaNotesService:

    def __init__(self, days_ago: int = 7) -> None:
        self.days_ago = days_ago

    async def fetch_all_notes(self) -> list[GranolaNote]:
        created_after = (datetime.now(timezone.utc) - timedelta(days=self.days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        notes: list[GranolaNote] = []
        cursor = None

        async with httpx.AsyncClient() as client:
            while True:
                params = {"created_after": created_after}
                if cursor:
                    params["cursor"] = cursor

                response = await client.get(
                    f"{GRANOLA_API_BASE_URL}/notes",
                    params=params,
                    headers={"Authorization": f"Bearer {GRANOLA_API_KEY}"},
                )
                response.raise_for_status()
                data = GranolaNotesResponse.model_validate(response.json())

                notes.extend([n for n in data.notes if n.object == "note"])

                if not data.hasMore:
                    break
                cursor = data.cursor

        return notes

    async def match_notes_to_db(self, granola_notes: list[GranolaNote], db: AsyncSession) -> list[NoteToEventMatch]:
        # Filter out notes that already have a matching CalendarEventMeetingNotes record
        note_ids = [n.id for n in granola_notes]
        result = await db.execute(
            select(CalendarEventMeetingNotes.note_id)
            .where(CalendarEventMeetingNotes.note_id.in_(note_ids))
        )
        existing_note_ids = set(result.scalars().all())
        new_notes = [n for n in granola_notes if n.id not in existing_note_ids]

        if not new_notes:
            return [NoteToEventMatch(granola_note_id=n.id, calendar_event_id=None) for n in granola_notes]

        # Query CalendarEvents in the date range that don't already have meeting notes
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_ago)
        result = await db.execute(
            select(CalendarEvent)
            .outerjoin(CalendarEventMeetingNotes, CalendarEvent.id == CalendarEventMeetingNotes.calendar_event_id)
            .where(
                CalendarEvent.start_time >= cutoff,
                CalendarEventMeetingNotes.id.is_(None),
            )
        )
        unmatched_events = result.scalars().all()

        # If no calendar events to match against, return all as unmatched
        if not unmatched_events:
            return [NoteToEventMatch(granola_note_id=n.id, calendar_event_id=None) for n in new_notes]

        events = [
            CalendarEventForMatching(
                id=e.id,
                title=e.title,
                description=e.description,
                start_time=e.start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            )
            for e in unmatched_events
        ]

        notes = [
            GranolaNoteForMatching(
                id=n.id,
                title=n.title,
                created_at=n.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            )
            for n in new_notes
        ]

        return await match_notes_to_events(events, notes)

    async def get_note(self, note_id: str) -> GranolaNoteDetail:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GRANOLA_API_BASE_URL}/notes/{note_id}",
                headers={"Authorization": f"Bearer {GRANOLA_API_KEY}"},
            )
            response.raise_for_status()
            return GranolaNoteDetail.model_validate(response.json())
