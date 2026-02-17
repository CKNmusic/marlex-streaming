from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.models.user import User
from app.models.device import Device
from app.models.protocol import Protocol
from app.schemas.protocol import ProtocolCreate, ProtocolUpdate, Protocol as ProtocolSchema
from app.api import deps
from app.services.stream_protocols import is_known_protocol, normalize_protocol_name

router = APIRouter()

@router.get("/", response_model=List[ProtocolSchema])
async def read_protocols(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve protocols. Master only as per spec.
    """
    result = await db.execute(select(Protocol))
    return result.scalars().all()

@router.post("/", response_model=ProtocolSchema)
async def create_protocol(
    *,
    db: AsyncSession = Depends(get_db),
    protocol_in: ProtocolCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new protocol. Admin only.
    """
    normalized_protocol = normalize_protocol_name(protocol_in.protocol)
    if not normalized_protocol:
        raise HTTPException(status_code=422, detail="Protocol inválido.")
    if not is_known_protocol(normalized_protocol):
        raise HTTPException(status_code=422, detail="Protocol não suportado.")
    protocol = Protocol(
        protocol=normalized_protocol,
        port=int(protocol_in.port),
        is_active=bool(protocol_in.is_active),
    )
    db.add(protocol)
    await db.commit()
    await db.refresh(protocol)
    return protocol

@router.delete("/{protocol_id}", response_model=ProtocolSchema)
async def delete_protocol(
    *,
    db: AsyncSession = Depends(get_db),
    protocol_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a protocol. Admin only.
    """
    result = await db.execute(select(Protocol).where(Protocol.id == protocol_id))
    protocol = result.scalars().first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    device_ref = await db.execute(
        select(Device.id).where(Device.protocol_id == protocol.id).limit(1)
    )
    if device_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Protocol em uso, não pode excluir.")

    await db.delete(protocol)
    await db.commit()
    return protocol

@router.patch("/{protocol_id}", response_model=ProtocolSchema)
async def update_protocol(
    *,
    db: AsyncSession = Depends(get_db),
    protocol_id: int,
    protocol_in: ProtocolUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a protocol. Admin only.
    """
    result = await db.execute(select(Protocol).where(Protocol.id == protocol_id))
    protocol = result.scalars().first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    update_data = protocol_in.model_dump(exclude_unset=True)
    if "protocol" in update_data:
        normalized_protocol = normalize_protocol_name(update_data["protocol"])
        if not normalized_protocol:
            raise HTTPException(status_code=422, detail="Protocol inválido.")
        if not is_known_protocol(normalized_protocol):
            raise HTTPException(status_code=422, detail="Protocol não suportado.")
        update_data["protocol"] = normalized_protocol
    if update_data.get("is_active") is False and protocol.is_active:
        device_ref = await db.execute(
            select(Device.id).where(Device.protocol_id == protocol.id).limit(1)
        )
        if device_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Protocol em uso, não pode desativar.")
    if "protocol" in update_data and update_data["protocol"] != protocol.protocol:
        device_ref = await db.execute(
            select(Device.id).where(Device.protocol_id == protocol.id).limit(1)
        )
        if device_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Protocol em uso, não pode renomear.")
    for field, value in update_data.items():
        setattr(protocol, field, value)

    db.add(protocol)
    await db.commit()
    await db.refresh(protocol)
    return protocol
