from datetime import date, datetime

from sqlalchemy  import DateTime, Text, Date, Enum, ForeignKey, Index, Text, text, event
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from .base import Base
from .constants import MembershipStatus, Location, TodoSource, TodoType

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
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    location: Mapped[Location] = mapped_column(Enum(Location), nullable=False)
    membership_status: Mapped[MembershipStatus] = mapped_column(Enum(MembershipStatus), nullable=False, default=MembershipStatus.NON_MEMBER)

    todos: Mapped[list['Todo']] = relationship("Todo", back_populates="client")

class Todo(Base):
    __tablename__ = "todos"

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=True, default=None)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[TodoSource] = mapped_column(Enum(TodoSource), nullable=False, default=TodoSource.AUTO)
    todo_type: Mapped[TodoType] = mapped_column(Enum(TodoType), nullable=False)

    client: Mapped["Client"] = relationship("Client", back_populates="todos")


@event.listens_for(Base.metadata, "after_create")
def create_indexes(target, connection, **kwargs):
    connection.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
    connection.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_clients_name_trgm 
        ON clients USING GIN ((first_name || ' ' || last_name) gin_trgm_ops)
    """))