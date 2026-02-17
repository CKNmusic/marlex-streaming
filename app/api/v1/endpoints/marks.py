from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import get_db
from app.models.device import Device
from app.models.mark import Mark
from app.models.user import User
from app.schemas.mark import Mark as MarkSchema
from app.schemas.mark import MarkCreate, MarkUpdate

router = APIRouter()


def _normalize_mark_name(raw_name: str) -> str:
    return str(raw_name or "").strip()


@router.get("/", response_model=List[MarkSchema])
async def read_marks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(select(Mark))
    return result.scalars().all()


@router.post("/", response_model=MarkSchema)
async def create_mark(
    *,
    db: AsyncSession = Depends(get_db),
    mark_in: MarkCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    normalized_name = _normalize_mark_name(mark_in.name)
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Marca inválida.")

    existing = await db.execute(select(Mark).where(func.lower(Mark.name) == normalized_name.lower()))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Marca já cadastrada.")

    mark = Mark(name=normalized_name, is_active=bool(mark_in.is_active))
    db.add(mark)
    await db.commit()
    await db.refresh(mark)
    return mark


@router.patch("/{mark_id}", response_model=MarkSchema)
async def update_mark(
    *,
    db: AsyncSession = Depends(get_db),
    mark_id: int,
    mark_in: MarkUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(select(Mark).where(Mark.id == mark_id))
    mark = result.scalars().first()
    if not mark:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    update_data = mark_in.model_dump(exclude_unset=True)

    next_name = None
    if "name" in update_data:
        next_name = _normalize_mark_name(update_data["name"])
        if not next_name:
            raise HTTPException(status_code=422, detail="Marca inválida.")

    device_ref = await db.execute(select(Device.id).where(Device.mark_id == mark.id).limit(1))
    mark_in_use = device_ref.scalar() is not None

    if update_data.get("is_active") is False and mark.is_active and mark_in_use:
        raise HTTPException(status_code=400, detail="Marca em uso, não pode desativar.")

    if next_name and next_name.lower() != mark.name.lower():
        duplicate = await db.execute(
            select(Mark.id).where(
                func.lower(Mark.name) == next_name.lower(),
                Mark.id != mark.id,
            )
        )
        if duplicate.scalar() is not None:
            raise HTTPException(status_code=400, detail="Marca já cadastrada.")
        if mark_in_use:
            raise HTTPException(status_code=400, detail="Marca em uso, não pode renomear.")
        mark.name = next_name

    if "is_active" in update_data:
        mark.is_active = bool(update_data["is_active"])

    db.add(mark)
    await db.commit()
    await db.refresh(mark)
    return mark


@router.delete("/{mark_id}", response_model=MarkSchema)
async def delete_mark(
    *,
    db: AsyncSession = Depends(get_db),
    mark_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(select(Mark).where(Mark.id == mark_id))
    mark = result.scalars().first()
    if not mark:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    device_ref = await db.execute(select(Device.id).where(Device.mark_id == mark.id).limit(1))
    if device_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Marca em uso, não pode excluir.")

    await db.delete(mark)
    await db.commit()
    return mark
