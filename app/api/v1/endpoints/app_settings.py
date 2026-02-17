from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core.config import settings
from app.db.session import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.schemas.app_setting import AppSetting as AppSettingSchema, AppSettingUpdate
from app.services.output_format import normalize_output_format
from app.services.recorder import normalize_recordings_dir, recorder_service

router = APIRouter()


def _default_public_host() -> str:
    return f"http://{settings.APP_HOST}:3000/{settings.APP_NAME}"


def _normalize_scan_start_in(raw_value: Any, *, strict: bool = False) -> int:
    message = "Tempo limite para iniciar a gravacao deve ser inteiro entre 5 e 600 segundos."

    if isinstance(raw_value, bool):
        if strict:
            raise HTTPException(status_code=422, detail=message)
        return 60

    if isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float):
        if not raw_value.is_integer():
            if strict:
                raise HTTPException(status_code=422, detail=message)
            return 60
        value = int(raw_value)
    elif isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if not trimmed or not trimmed.isdigit():
            if strict:
                raise HTTPException(status_code=422, detail=message)
            return 60
        value = int(trimmed)
    else:
        if strict:
            raise HTTPException(status_code=422, detail=message)
        return 60

    if strict and (value < 5 or value > 600):
        raise HTTPException(status_code=422, detail=message)
    return max(5, min(value, 600))


@router.get("/", response_model=AppSettingSchema)
async def read_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve app settings. Any authenticated user can read.
    """
    result = await db.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
    app_setting = result.scalars().first()
    if not app_setting:
        app_setting = AppSetting(
            name=settings.APP_NAME,
            description="Streaming Médico",
            host=_default_public_host(),
            recordings_dir=normalize_recordings_dir("/recordings"),
            output_format="mp4",
            scan_start_in=60,
        )
        db.add(app_setting)
        await db.commit()
        await db.refresh(app_setting)
    else:
        app_setting.output_format = normalize_output_format(app_setting.output_format)
        app_setting.recordings_dir = normalize_recordings_dir(app_setting.recordings_dir)
        app_setting.scan_start_in = _normalize_scan_start_in(getattr(app_setting, "scan_start_in", 60))
        db.add(app_setting)
        await db.commit()
        await db.refresh(app_setting)
    recorder_service.set_recordings_dir(app_setting.recordings_dir)
    return app_setting


@router.patch("/", response_model=AppSettingSchema)
async def update_app_settings(
    *,
    db: AsyncSession = Depends(get_db),
    app_in: AppSettingUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update app settings. Master only.
    """
    result = await db.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
    app_setting = result.scalars().first()
    if not app_setting:
        app_setting = AppSetting(
            name=settings.APP_NAME,
            description="Streaming Médico",
            host=_default_public_host(),
            recordings_dir=normalize_recordings_dir("/recordings"),
            output_format="mp4",
            scan_start_in=60,
        )

    update_data = app_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar.")
    if "output_format" in update_data:
        update_data["output_format"] = normalize_output_format(update_data.get("output_format"))
    if "recordings_dir" in update_data:
        update_data["recordings_dir"] = normalize_recordings_dir(update_data.get("recordings_dir"))
    if "scan_start_in" in update_data:
        update_data["scan_start_in"] = _normalize_scan_start_in(update_data.get("scan_start_in"), strict=True)

    for field, value in update_data.items():
        setattr(app_setting, field, value)

    db.add(app_setting)
    await db.commit()
    await db.refresh(app_setting)
    recorder_service.set_recordings_dir(app_setting.recordings_dir)
    return app_setting
