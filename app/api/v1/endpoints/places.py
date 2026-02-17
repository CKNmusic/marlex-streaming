from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.user import User
from app.models.place import Place
from app.models.city import City
from app.models.device import Device
from app.models.record import Record
from app.schemas.place import PlaceCreate, PlaceUpdate, Place as PlaceSchema
from app.api import deps

router = APIRouter()


@router.get("/", response_model=List[PlaceSchema])
async def read_places(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve places. Any authenticated user can read.
    """
    result = await db.execute(select(Place))
    return result.scalars().all()


@router.post("/", response_model=PlaceSchema)
async def create_place(
    *,
    db: AsyncSession = Depends(get_db),
    place_in: PlaceCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new place. Master only.
    """
    res_city = await db.execute(select(City).where(City.id == place_in.city_id))
    if not res_city.scalars().first():
        raise HTTPException(status_code=404, detail="Cidade não encontrada")
    place = Place(**place_in.model_dump())
    db.add(place)
    await db.commit()
    await db.refresh(place)
    return place


@router.patch("/{place_id}", response_model=PlaceSchema)
async def update_place(
    *,
    db: AsyncSession = Depends(get_db),
    place_id: int,
    place_in: PlaceUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update place. Master only.
    """
    result = await db.execute(select(Place).where(Place.id == place_id))
    place = result.scalars().first()
    if not place:
        raise HTTPException(status_code=404, detail="Place não encontrado")

    update_data = place_in.model_dump(exclude_unset=True)
    if "city_id" in update_data:
        next_city_id = update_data.pop("city_id")
        if next_city_id != place.city_id:
            raise HTTPException(
                status_code=400,
                detail="Cidade do local não pode ser alterada após criação.",
            )
    if update_data.get("is_active") is False and place.is_active:
        device_ref = await db.execute(
            select(Device.id).where(Device.place_id == place_id).limit(1)
        )
        if device_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Local em uso, não pode desativar.")
        record_ref = await db.execute(
            select(Record.id).where(Record.place_id == place_id).limit(1)
        )
        if record_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Local em uso, não pode desativar.")
    for field, value in update_data.items():
        setattr(place, field, value)

    db.add(place)
    await db.commit()
    await db.refresh(place)
    return place


@router.delete("/{place_id}", response_model=PlaceSchema)
async def delete_place(
    *,
    db: AsyncSession = Depends(get_db),
    place_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete place. Master only.
    """
    result = await db.execute(select(Place).where(Place.id == place_id))
    place = result.scalars().first()
    if not place:
        raise HTTPException(status_code=404, detail="Place não encontrado")

    device_ref = await db.execute(
        select(Device.id).where(Device.place_id == place_id).limit(1)
    )
    if device_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Local em uso, desative.")
    record_ref = await db.execute(
        select(Record.id).where(Record.place_id == place_id).limit(1)
    )
    if record_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Local em uso, desative.")

    try:
        await db.delete(place)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Place em uso, não pode excluir")

    return place
