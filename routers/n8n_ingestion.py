from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from models.db import CalendarEvent, CalendarEventClientSuggestion, Client, Todo
from models.constants import MeetingType, TodoSource, TodoType
from schemas import (
    CalendarEventData,
    FilterEventsRequest,
    FilterEventsResponse,
    ProcessCalendarEventsRequest,
)
from utils.error_logging import log_error_to_db, log_background_error
from utils.openai_helpers import (
    match_client_from_meeting,
    extract_contact_info,
    classify_meeting_type,
)

router = APIRouter(prefix="/n8n", tags=["N8nIngestion"])


@router.post("/filter-events", response_model=FilterEventsResponse)
@log_error_to_db
async def filter_new_events(
    data: FilterEventsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Return event IDs that don't yet exist in the database."""
    result = await db.execute(
        select(CalendarEvent.gcal_source_event_id)
        .where(CalendarEvent.gcal_source_event_id.in_(data.event_ids))
    )
    existing_ids = set(result.scalars().all())
    new_ids = [eid for eid in data.event_ids if eid not in existing_ids]
    return FilterEventsResponse(new_event_ids=new_ids)


@router.post("/process-events")
@log_error_to_db
async def process_calendar_events(
    data: ProcessCalendarEventsRequest,
    background_tasks: BackgroundTasks,
):
    """Queue calendar events for background processing."""
    background_tasks.add_task(
        _process_events_background,
        [event.model_dump() for event in data.events],
    )
    return {"detail": f"Processing {len(data.events)} events in background"}


async def _process_events_background(events_data: list[dict]):
    """Background task to process all calendar events."""
    for event_data in events_data:
        try:
            await _process_single_event(event_data)
        except Exception as e:
            await log_background_error("process_calendar_event", e)


async def _process_single_event(event_data: dict):
    """Process a single calendar event: create record, match client, create todos."""
    event = CalendarEventData(**event_data)

    async with async_session() as db:
        # Step 1: Create CalendarEvent record
        cal_event = CalendarEvent(
            gcal_source_event_id=event.event_id,
            source_data=event.calendar_data,
        )
        db.add(cal_event)
        await db.commit()
        await db.refresh(cal_event)

        try:
            # Step 1A: Client matching via OpenAI
            result = await db.execute(
                select(Client).where(Client.user_confirmed == True)
            )
            confirmed_clients = result.scalars().all()
            existing_clients = [
                {"id": c.id, "name": f"{c.first_name} {c.last_name}"}
                for c in confirmed_clients
            ]

            match_result = await match_client_from_meeting(
                existing_clients=existing_clients,
                attendee_names=event.attendee_names,
                meeting_title=event.title,
            )

            # Step 3: Resolve client_id
            client_id = match_result.client_id

            if client_id is None:
                # No match found — extract contact info and create new client
                contact_info = await extract_contact_info(event.calendar_data)
                new_client = Client(
                    first_name=match_result.first_name,
                    last_name=match_result.last_name,
                    email=contact_info.email,
                    phone=contact_info.phone,
                    user_confirmed=False,
                    source="auto",
                )
                db.add(new_client)
                await db.flush()
                client_id = new_client.id

            # Create CalendarEventClientSuggestion
            suggestion = CalendarEventClientSuggestion(
                client_id=client_id,
                calendar_event_id=cal_event.id,
                user_confirmed=False,
            )
            db.add(suggestion)
            await db.flush()

            # Step 1B: Classify meeting type and create todo
            meeting_type_result = await classify_meeting_type(
                meeting_title=event.title,
                calendar_data=event.calendar_data,
            )

            full_name = f"{match_result.first_name} {match_result.last_name}"
            today = date.today()
            todo = _build_todo_for_meeting(
                client_id=client_id,
                suggestion_id=suggestion.id,
                meeting_type=meeting_type_result.meeting_type,
                full_name=full_name,
                event=event,
                today=today,
            )
            db.add(todo)
            await db.commit()

        except Exception:
            await db.rollback()
            # Step 4: Create manual review todo on failure
            async with async_session() as error_db:
                error_todo = Todo(
                    title="Calendar Event Review Required",
                    notes=(
                        "Automated calendar event processing failed. "
                        "Please review calendar event "
                        f"https://www.google.com/calendar/event?eid={event.event_id}"
                    ),
                    due_date=date.today(),
                    source=TodoSource.AUTO,
                    todo_type=TodoType.MANUAL_EVENT_REVIEW,
                )
                error_db.add(error_todo)
                await error_db.commit()
            raise


def _build_todo_for_meeting(
    client_id: int,
    suggestion_id: int,
    meeting_type: MeetingType,
    full_name: str,
    event: CalendarEventData,
    today: date,
) -> Todo:
    """Build the appropriate Todo based on meeting type."""
    if meeting_type == MeetingType.NEW_PATIENT_CONSULTATION:
        return Todo(
            client_id=client_id,
            cal_event_client_suggestion_id=suggestion_id,
            title=f"New Client Onboarding: {full_name}",
            notes=(
                "- Add patient to Charm\n"
                "- Review client data in dashboard\n"
                "- Send intake forms\n"
                "- Add Stripe invoicing for clients on membership\n"
                "- Add any consult-specific todos manually in dashboard"
            ),
            due_date=today,
            source=TodoSource.AUTO,
            todo_type=TodoType.NEW_CLIENT_ONBOARDING,
        )
    elif meeting_type == MeetingType.FOLLOW_UP_CONSULTATION:
        meeting_date = event.calendar_data.get("start", {}).get("dateTime", str(today))
        duration_minutes = _estimate_duration_minutes(event.calendar_data)
        return Todo(
            client_id=client_id,
            cal_event_client_suggestion_id=suggestion_id,
            title=f"Consultation Billing Review: {full_name}",
            notes=(
                f"If {full_name} is not on membership program, be sure to "
                f"invoice them for {duration_minutes} minute consultation on {meeting_date}"
            ),
            due_date=today,
            source=TodoSource.AUTO,
            todo_type=TodoType.CONSULTATION_BILLING_REVIEW,
        )
    else:
        meeting_date = event.calendar_data.get("start", {}).get("dateTime", str(today))
        return Todo(
            client_id=client_id,
            cal_event_client_suggestion_id=suggestion_id,
            title=f"Review: {event.title}",
            notes=f"Add any todos from the meeting with {full_name} on {meeting_date}",
            due_date=today,
            source=TodoSource.AUTO,
            todo_type=TodoType.GENERAL,
        )


def _estimate_duration_minutes(calendar_data: dict) -> int:
    """Estimate meeting duration in minutes from calendar start/end times."""
    try:
        from datetime import datetime as dt
        start = calendar_data.get("start", {}).get("dateTime", "")
        end = calendar_data.get("end", {}).get("dateTime", "")
        if start and end:
            start_dt = dt.fromisoformat(start)
            end_dt = dt.fromisoformat(end)
            return int((end_dt - start_dt).total_seconds() / 60)
    except (ValueError, TypeError):
        pass
    return 60  # Default to 60 minutes
