from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.user import User
from app.models.city import City
from app.models.place import Place
from app.schemas.city import CityCreate, CityUpdate, City as CitySchema
from app.api import deps

router = APIRouter()


@router.get("/", response_model=List[CitySchema])
async def read_cities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve cities. Any authenticated user can read.
    """
    result = await db.execute(select(City))
    return result.scalars().all()


@router.post("/", response_model=CitySchema)
async def create_city(
    *,
    db: AsyncSession = Depends(get_db),
    city_in: CityCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new city. Master only.
    """
    city = City(**city_in.model_dump())
    db.add(city)
    await db.commit()
    await db.refresh(city)
    return city


@router.patch("/{city_id}", response_model=CitySchema)
async def update_city(
    *,
    db: AsyncSession = Depends(get_db),
    city_id: int,
    city_in: CityUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update city. Master only.
    """
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalars().first()
    if not city:
        raise HTTPException(status_code=404, detail="Cidade não encontrada")

    update_data = city_in.model_dump(exclude_unset=True)
    if "name" in update_data or "uf" in update_data:
        raise HTTPException(status_code=400, detail="Cidade não pode ser editada. Cadastre uma nova cidade.")
    if update_data.get("is_active") is False and city.is_active:
        place_ref = await db.execute(
            select(Place.id).where(Place.city_id == city_id).limit(1)
        )
        if place_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Cidade em uso, não pode desativar.")

    for field, value in update_data.items():
        setattr(city, field, value)

    db.add(city)
    await db.commit()
    await db.refresh(city)
    return city


@router.delete("/{city_id}", response_model=CitySchema)
async def delete_city(
    *,
    db: AsyncSession = Depends(get_db),
    city_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete city. Master only.
    """
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalars().first()
    if not city:
        raise HTTPException(status_code=404, detail="Cidade não encontrada")

    place_ref = await db.execute(
        select(Place.id).where(Place.city_id == city_id).limit(1)
    )
    if place_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Cidade em uso, desative.")

    try:
        await db.delete(city)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Cidade em uso, não pode excluir")

    return city
