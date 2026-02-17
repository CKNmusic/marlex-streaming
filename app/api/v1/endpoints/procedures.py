from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.models.user import User
from app.models.procedure import Procedure
from app.models.record import Record
from app.schemas.procedure import ProcedureCreate, ProcedureUpdate, Procedure as ProcedureSchema
from app.api import deps

router = APIRouter()

@router.get("/", response_model=List[ProcedureSchema])
async def read_procedures(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve procedures. Available for active users (master manages).
    """
    result = await db.execute(select(Procedure).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/", response_model=ProcedureSchema)
async def create_procedure(
    *,
    db: AsyncSession = Depends(get_db),
    procedure_in: ProcedureCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new procedure. Admin only.
    """
    procedure = Procedure(**procedure_in.model_dump())
    db.add(procedure)
    await db.commit()
    await db.refresh(procedure)
    return procedure

@router.patch("/{procedure_id}", response_model=ProcedureSchema)
async def update_procedure(
    *,
    db: AsyncSession = Depends(get_db),
    procedure_id: int,
    procedure_in: ProcedureUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a procedure. Admin only.
    """
    result = await db.execute(select(Procedure).where(Procedure.id == procedure_id))
    procedure = result.scalars().first()
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedimento não encontrado")

    update_data = procedure_in.model_dump(exclude_unset=True)
    if update_data.get("is_active") is False and procedure.is_active:
        record_ref = await db.execute(
            select(Record.id).where(Record.procedure_id == procedure_id).limit(1)
        )
        if record_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Procedimento em uso, não pode desativar.")

    for field, value in update_data.items():
        setattr(procedure, field, value)

    db.add(procedure)
    await db.commit()
    await db.refresh(procedure)
    return procedure

@router.delete("/{procedure_id}", response_model=ProcedureSchema)
async def delete_procedure(
    *,
    db: AsyncSession = Depends(get_db),
    procedure_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a procedure. Admin only.
    """
    result = await db.execute(select(Procedure).where(Procedure.id == procedure_id))
    procedure = result.scalars().first()
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedimento não encontrado")

    record_ref = await db.execute(
        select(Record.id).where(Record.procedure_id == procedure_id).limit(1)
    )
    if record_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Procedimento em uso, desative.")

    await db.delete(procedure)
    await db.commit()
    return procedure
