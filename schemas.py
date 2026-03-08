from datetime import date, datetime

from pydantic import BaseModel

from models.constants import Location, MembershipStatus, TodoSource, TodoType


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
    def from_model(cls, client) -> "ClientResponse":
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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, todo) -> "TodoResponse":
        return cls.model_validate(todo)


class CreateTodoRequest(BaseModel):
    client_id: int | None = None
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
    attendee_names: list[str]
    calendar_data: dict


class FilterEventsRequest(BaseModel):
    event_ids: list[str]


class FilterEventsResponse(BaseModel):
    new_event_ids: list[str]


class ProcessCalendarEventsRequest(BaseModel):
    events: list[CalendarEventData]


# --- Calendar Event Client Suggestion Schemas ---

class CalendarEventClientSuggestionResponse(BaseModel):
    id: int
    client_id: int
    calendar_event_id: int
    user_confirmed: bool
    client: ClientResponse
    todos: list[TodoResponse]

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, suggestion) -> "CalendarEventClientSuggestionResponse":
        return cls.model_validate(suggestion)


class ConfirmSuggestionRequest(BaseModel):
    replacement_client_id: int | None = None
