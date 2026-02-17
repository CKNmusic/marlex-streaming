from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core import security
from app.db.session import get_db
from app.models.invite import Invite
from app.models.user import User
from app.schemas.invite import RegisterRequest

router = APIRouter()


@router.post("/")
async def register_with_invite(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Register a new user using an invite code.
    No authentication required - the invite code acts as authorization.
    """
    code = payload.invite_code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Código de convite obrigatório.")

    # Find invite
    result = await db.execute(select(Invite).where(Invite.code == code))
    invite = result.scalars().first()
    if not invite:
        raise HTTPException(status_code=404, detail="Código de convite inválido.")
    if not invite.is_active:
        raise HTTPException(status_code=400, detail="Convite já foi revogado.")
    if invite.used_by is not None:
        raise HTTPException(status_code=400, detail="Convite já foi utilizado.")
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Convite expirado.")

    # Validate username
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Nome de usuário obrigatório.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Nome de usuário deve ter pelo menos 3 caracteres.")

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Nome de usuário já está em uso.")

    # Validate password
    if not payload.password or len(payload.password) < 12:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 12 caracteres.")

    # Create user
    user = User(
        username=username,
        full_name=payload.full_name.strip() or None,
        is_active=True,
        is_superuser=False,
        password=security.get_password_hash(payload.password),
    )
    db.add(user)
    await db.flush()

    # Mark invite as used
    invite.used_by = user.id
    invite.used_at = datetime.now(timezone.utc)
    db.add(invite)

    await db.commit()

    return {"message": "Conta criada com sucesso."}
