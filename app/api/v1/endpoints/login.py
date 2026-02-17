from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.schemas.token import LoginResponse, PasswordResetRequest
from app.services.user_notifications import (
    NOTIFICATION_TYPE_LOGIN,
    create_user_notification,
)

router = APIRouter()

@router.post("/access-token", response_model=LoginResponse)
async def login_access_token(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # 1. Fetch user by username
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    
    # 2. Authenticate
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    password_is_username = security.verify_password(user.username, user.password)
    if password_is_username:
        if form_data.password != user.username:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        try:
            await create_user_notification(
                db,
                user_id=user.id,
                notification_type=NOTIFICATION_TYPE_LOGIN,
                title="Login realizado",
                message="Login efetuado com senha provisória.",
                visible_to_user=False,
            )
            await db.commit()
        except Exception:
            await db.rollback()
        reset_token = security.create_password_reset_token(user.id)
        return {
            "reset_required": True,
            "reset_token": reset_token,
            "token_type": "reset",
        }

    if not security.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    try:
        await create_user_notification(
            db,
            user_id=user.id,
            notification_type=NOTIFICATION_TYPE_LOGIN,
            title="Login realizado",
            message="Login efetuado com sucesso.",
            visible_to_user=False,
        )
        await db.commit()
    except Exception:
        await db.rollback()
    
    # 3. Generate token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }


@router.post("/reset-password", response_model=LoginResponse)
async def reset_password(
    *,
    db: AsyncSession = Depends(get_db),
    payload: PasswordResetRequest,
) -> Any:
    """
    Reset password using a short-lived reset token.
    Returns a fresh access token (auto-login).
    """
    user_id = security.verify_password_reset_token(payload.reset_token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = security.get_password_hash(payload.password)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }
