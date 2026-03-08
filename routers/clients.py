from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import Client
from schemas import ClientResponse, CreateClientRequest, UpdateClientRequest
from utils.error_logging import log_error_to_db

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("/", response_model=list[ClientResponse])
@log_error_to_db
async def get_clients(
    user_confirmed: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all non-archived clients, with optional user_confirmed filter."""
    query = select(Client).where(Client.archived == False)
    if user_confirmed is not None:
        query = query.where(Client.user_confirmed == user_confirmed)
    result = await db.execute(query)
    return [ClientResponse.from_model(c) for c in result.scalars().all()]


@router.patch("/{client_id}", response_model=ClientResponse)
@log_error_to_db
async def update_client(
    client_id: int,
    data: UpdateClientRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update specific fields on a client."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await db.commit()
    await db.refresh(client)
    return ClientResponse.from_model(client)


@router.post("/{client_id}/archive", response_model=ClientResponse)
@log_error_to_db
async def archive_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Set archived=True on a client."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    client.archived = True
    await db.commit()
    await db.refresh(client)
    return ClientResponse.from_model(client)


@router.post("/", response_model=ClientResponse)
@log_error_to_db
async def create_client(
    data: CreateClientRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new client (manually created clients are user_confirmed by default)."""
    client = Client(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        notes=data.notes,
        address=data.address,
        location=data.location,
        membership_status=data.membership_status,
        charm_id=data.charm_id,
        user_confirmed=True,
        source="manual",
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ClientResponse.from_model(client)
