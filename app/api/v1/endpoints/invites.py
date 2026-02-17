import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core import security
from app.db.session import get_db
from app.models.invite import Invite
from app.models.user import User
from app.schemas.invite import InviteOut, RegisterRequest

router = APIRouter()

INVITE_EXPIRY_HOURS = 72


def _generate_invite_code() -> str:
    raw = secrets.token_hex(4).upper()
    return f"{raw[:4]}-{raw[4:]}"


@router.get("/", response_model=List[InviteOut])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(
        select(Invite).where(Invite.created_by == current_user.id).order_by(Invite.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=InviteOut, status_code=201)
async def create_invite(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    code = _generate_invite_code()
    # Ensure uniqueness
    for _ in range(5):
        existing = await db.execute(select(Invite).where(Invite.code == code))
        if not existing.scalars().first():
            break
        code = _generate_invite_code()

    invite = Invite(
        code=code,
        created_by=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS),
        is_active=True,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


@router.delete("/{invite_id}", response_model=InviteOut)
async def revoke_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalars().first()
    if not invite:
        raise HTTPException(status_code=404, detail="Convite não encontrado.")
    if invite.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão.")
    invite.is_active = False
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite
