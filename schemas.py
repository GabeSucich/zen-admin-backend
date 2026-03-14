from datetime import date, datetime

from pydantic import BaseModel, computed_field

from models.constants import Location, MeetingType, MembershipStatus, TodoSource, TodoType
from models.db import (
    CalendarEventClientSuggestion as CalendarEventClientSuggestionModel,
    Client as ClientModel,
    MeetingTypeTodoTemplates as MeetingTypeTodoTemplatesModel,
    Todo as TodoModel,
)
from utils.gcal import gcal_event_link


# --- Client Schemas ---

class ClientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    notes: str | None
    address: str | None
    source: str
    location: Location | None
    membership_status: MembershipStatus
    charm_id: str | None
    user_confirmed: bool
    archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, client: ClientModel) -> "ClientResponse":
        return cls.model_validate(client)


class UpdateClientRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    address: str | None = None
    location: Location | None = None
    membership_status: MembershipStatus | None = None
    charm_id: str | None = None


class CreateClientRequest(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    address: str | None = None
    location: Location | None = None
    membership_status: MembershipStatus = MembershipStatus.NON_MEMBER
    charm_id: str | None = None


# --- Todo Schemas ---

class TodoResponse(BaseModel):
    id: int
    client_id: int | None
    cal_event_client_suggestion_id: int | None
    title: str
    notes: str | None
    due_date: date
    completed_at: datetime | None
    source: TodoSource
    todo_type: TodoType
    client: ClientResponse | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, todo: TodoModel) -> "TodoResponse":
        return cls.model_validate(todo)


class CreateTodoRequest(BaseModel):
    client_id: int | None = None
    cal_event_client_suggestion_id: int | None = None
    title: str
    notes: str | None = None
    due_date: date
    todo_type: TodoType


class UpdateTodoRequest(BaseModel):
    client_id: int | None = None
    title: str | None = None
    notes: str | None = None
    due_date: date | None = None


class ChangeDueDateRequest(BaseModel):
    due_date: date


# --- Calendar Event Schemas ---

class CalendarEventData(BaseModel):
    event_id: str
    title: str
    description: str | None = None
    start_time: str
    time_zone: str
    attendee_emails: list[str] = []
    calendar_data: dict

    def start_time_utc(self) -> datetime:
        from zoneinfo import ZoneInfo
        local_dt = datetime.fromisoformat(self.start_time)
        if local_dt.tzinfo is None:
            local_dt = local_dt.replace(tzinfo=ZoneInfo(self.time_zone))
        return local_dt.astimezone(ZoneInfo("UTC"))



class ProcessCalendarEventsRequest(BaseModel):
    events: list[CalendarEventData]


# --- Calendar Event Client Suggestion Schemas ---

class CalendarEventClientSuggestionResponse(BaseModel):
    id: int
    client_id: int | None
    calendar_event_id: int
    meeting_type: MeetingType | None
    user_confirmed: bool
    client: ClientResponse | None
    todos: list[TodoResponse]
    gcal_source_event_id: str
    title: str
    description: str | None
    start_time: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def gcal_link(self) -> str:
        return gcal_event_link(self.gcal_source_event_id)

    @classmethod
    def from_model(cls, suggestion: CalendarEventClientSuggestionModel) -> "CalendarEventClientSuggestionResponse":
        data = {
            **{c.key: getattr(suggestion, c.key) for c in suggestion.__table__.columns},
            "client": suggestion.client,
            "todos": suggestion.todos,
            "gcal_source_event_id": suggestion.cal_event.gcal_source_event_id,
            "title": suggestion.cal_event.title,
            "description": suggestion.cal_event.description,
            "start_time": suggestion.cal_event.start_time,
        }
        return cls.model_validate(data)


class ConfirmSuggestionRequest(BaseModel):
    meeting_type: MeetingType
    replacement_client_id: int | None = None


# --- Meeting Type Todo Template Schemas ---

class MeetingTypeTodoTemplateResponse(BaseModel):
    id: int
    meeting_type: MeetingType
    todo_type: TodoType
    title: str
    notes: str
    days_until_due: int
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, template: MeetingTypeTodoTemplatesModel) -> "MeetingTypeTodoTemplateResponse":
        return cls.model_validate(template)


class CreateMeetingTypeTodoTemplateRequest(BaseModel):
    meeting_type: MeetingType
    todo_type: TodoType
    title: str
    notes: str
    days_until_due: int
    order: int


class MeetingTypeResponse(BaseModel):
    meeting_type: MeetingType
    templates: list[MeetingTypeTodoTemplateResponse]


class UpdateMeetingTypeTodoTemplateRequest(BaseModel):
    title: str | None = None
    notes: str | None = None
    days_until_due: int | None = None
    order: int | None = None
