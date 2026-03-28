from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from models.db import CalendarEvent, CalendarEventClientSuggestion, Client, Error, ProcessEventLog, Todo
from models.constants import ProcessingState, TodoSource, TodoType
from schemas import (
    CalendarEventData,
    ProcessCalendarEventsRequest,
)
from utils.error_logging import log_error_to_db, log_background_error
from utils.openai_helpers import (
    check_if_cancellation,
    extract_client_name,
    extract_client_email,
    match_client_to_existing,
    classify_meeting_type,
)

router = APIRouter(prefix="/n8n", tags=["N8nIngestion"])



@router.post("/process-events")
@log_error_to_db
async def process_calendar_events(
    data: ProcessCalendarEventsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Queue calendar events for background processing, skipping already-processed events."""
    # Rate limit: check most recent ProcessEventLog
    result = await db.execute(
        select(ProcessEventLog).order_by(desc(ProcessEventLog.id)).limit(1)
    )
    last_log = result.scalar_one_or_none()
    if last_log and last_log.created_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) - timedelta(minutes=2):
        return {"success": False, "detail": "Cannot call process-events more frequently than every 2 minutes"}

    # Look up existing calendar events for the submitted event IDs
    event_ids = [e.event_id for e in data.events]
    result = await db.execute(
        select(CalendarEvent.gcal_source_event_id, CalendarEvent.processing_state)
        .where(CalendarEvent.gcal_source_event_id.in_(event_ids))
    )
    existing = {row[0]: row[1] for row in result.all()}

    new_events = []
    retry_events = []
    skipped = 0

    for event in data.events:
        state = existing.get(event.event_id)
        if state is None:
            new_events.append(event.model_dump())
        elif state == ProcessingState.ERROR:
            retry_events.append(event.model_dump())
        else:
            skipped += 1

    to_process = new_events + retry_events
    if to_process:
        background_tasks.add_task(_process_events_background, to_process)

    # Log this invocation
    db.add(ProcessEventLog())
    await db.commit()

    return {
        "success": True,
        "detail": f"{len(new_events) + len(retry_events)} event(s) processed",
        "new": len(new_events),
        "retried": len(retry_events),
        "skipped": skipped,
    }


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
        # Check if this is a retry of a previously errored event
        result = await db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.gcal_source_event_id == event.event_id)
        )
        cal_event = result.scalar_one_or_none()

        if cal_event is not None:
            # Retry — reset state to IN_PROGRESS
            cal_event.processing_state = ProcessingState.IN_PROGRESS
        else:
            cal_event = CalendarEvent(
                gcal_source_event_id=event.event_id,
                title=event.title,
                description=event.description,
                start_time=event.start_time_utc(),
                source_data=event.calendar_data,
                processing_state=ProcessingState.IN_PROGRESS,
            )
            db.add(cal_event)

        await db.commit()
        await db.refresh(cal_event)
        cal_event_id = cal_event.id

        try:
            # Check if this is a cancellation — skip processing if so
            cancellation_check = await check_if_cancellation(event.title)
            if cancellation_check.is_cancellation:
                cal_event.processing_state = ProcessingState.COMPLETE
                await db.commit()
                return

            # Step 1A: Extract client name and email
            name_result = await extract_client_name(event.title)
            has_name = name_result.first_name and name_result.last_name

            email_result = await extract_client_email(
                attendee_emails=event.attendee_emails,
                client_first_name=name_result.first_name,
                client_last_name=name_result.last_name,
            )
            client_email = email_result.email

            # Step 1A continued: Match to existing clients
            result = await db.execute(
                select(Client).where(Client.user_confirmed == True)
            )
            confirmed_clients = result.scalars().all()
            existing_clients = [
                {"id": c.id, "name": f"{c.first_name} {c.last_name}", "email": c.email}
                for c in confirmed_clients
            ]

            match_result = await match_client_to_existing(
                existing_clients=existing_clients,
                client_email=client_email,
                client_first_name=name_result.first_name,
                client_last_name=name_result.last_name,
            )

            # Step 3: Resolve client_id
            client_id = match_result.client_id

            if client_id is None and has_name:
                # No match but we have a name — create new client
                new_client = Client(
                    first_name=name_result.first_name,
                    last_name=name_result.last_name,
                    email=client_email,
                    user_confirmed=False,
                    source="auto",
                )
                db.add(new_client)
                await db.flush()
                client_id = new_client.id

            # Classify meeting type
            meeting_type_result = await classify_meeting_type(
                meeting_title=event.title,
                meeting_description=event.description,
            )

            # Create CalendarEventClientSuggestion
            suggestion = CalendarEventClientSuggestion(
                client_id=client_id,
                calendar_event_id=cal_event_id,
                meeting_type=meeting_type_result.meeting_type,
                user_confirmed=False,
            )
            db.add(suggestion)

            cal_event.processing_state = ProcessingState.COMPLETE
            await db.commit()

        except Exception as e:
            await db.rollback()
            # Step 4: Mark as ERROR, log error, create manual review todo
            async with async_session() as error_db:
                # Update processing state
                cal_event_ref = await error_db.get(CalendarEvent, cal_event_id)
                if cal_event_ref:
                    cal_event_ref.processing_state = ProcessingState.ERROR

                # Log error linked to the calendar event
                import traceback
                error_record = Error(
                    endpoint="process_calendar_event",
                    method="BACKGROUND_TASK",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback_str=traceback.format_exc(),
                    calendar_event_id=cal_event_id,
                )
                error_db.add(error_record)

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


