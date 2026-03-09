from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Integer, Text, Date, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from .base import Base
from .constants import MeetingType, MembershipStatus, Location, ProcessingState, TodoSource, TodoType

class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str]
    first_name: Mapped[str]
    last_name: Mapped[str]

class Client(Base):
    __tablename__ = "clients"

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    location: Mapped[Location | None] = mapped_column(Enum(Location), nullable=True, default=None)
    membership_status: Mapped[MembershipStatus] = mapped_column(Enum(MembershipStatus), nullable=False, default=MembershipStatus.NON_MEMBER)
    charm_id: Mapped[str | None] = mapped_column(Text, default=None)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    todos: Mapped[list['Todo']] = relationship("Todo", back_populates="client", cascade="all, delete-orphan")
    cal_event_client_suggestion: Mapped[Optional['CalendarEventClientSuggestion']] = relationship("CalendarEventClientSuggestion", back_populates="client")

class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    gcal_source_event_id: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    processing_state: Mapped[ProcessingState] = mapped_column(Enum(ProcessingState), nullable=False, default=ProcessingState.IN_PROGRESS)

    cal_event_client_suggestions: Mapped[list['CalendarEventClientSuggestion']] = relationship("CalendarEventClientSuggestion", back_populates="cal_event")
    errors: Mapped[list['Error']] = relationship("Error", back_populates="calendar_event")

class CalendarEventClientSuggestion(Base):
    __tablename__ = "calendar_event_client_suggestions"

    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"), nullable=True, default=None)
    calendar_event_id: Mapped[int] = mapped_column(ForeignKey("calendar_events.id"), index=True)
    meeting_type: Mapped[MeetingType | None] = mapped_column(Enum(MeetingType), nullable=True, default=None)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    todos: Mapped[list['Todo']] = relationship("Todo", back_populates="cal_event_client_suggestion")
    client: Mapped[Optional['Client']] = relationship("Client", back_populates="cal_event_client_suggestion")
    cal_event: Mapped['CalendarEvent'] = relationship("CalendarEvent", back_populates="cal_event_client_suggestions")


class Todo(Base):
    __tablename__ = "todos"

    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, default=None)
    cal_event_client_suggestion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("calendar_event_client_suggestions.id"), nullable=True, default=None)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[TodoSource] = mapped_column(Enum(TodoSource), nullable=False, default=TodoSource.AUTO)
    todo_type: Mapped[TodoType] = mapped_column(Enum(TodoType), nullable=False)

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="todos")
    cal_event_client_suggestion: Mapped[Optional["CalendarEventClientSuggestion"]] = relationship("CalendarEventClientSuggestion", back_populates="todos")


class Error(Base):
    __tablename__ = "errors"

    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback_str: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    calendar_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("calendar_events.id"), nullable=True, default=None)

    calendar_event: Mapped[Optional['CalendarEvent']] = relationship("CalendarEvent", back_populates="errors")

class ProcessEventLog(Base):

    __tablename__ = "process_event_logs"


class MeetingTypeTodoTemplates(Base):
    __tablename__ = "meeting_type_todo_templates"

    meeting_type: Mapped[MeetingType] = mapped_column(Enum(MeetingType), nullable=False, index=True)
    todo_type: Mapped[TodoType] = mapped_column(Enum(TodoType), nullable=False)
    title: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text)
    days_until_due: Mapped[int] = mapped_column(Integer)
    order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)



