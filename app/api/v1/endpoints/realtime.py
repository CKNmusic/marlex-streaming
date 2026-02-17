from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Set

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User
from app.models.user_device_access import UserDeviceAccess
from app.schemas.token import TokenPayload
from app.services.device_stream_url import build_device_stream_url, load_device_stream_context
from app.services.device_runtime_state import device_runtime_state
from app.services.device_status import (
    DEVICE_STATUS_OFFLINE,
    RUNTIME_ACTIVE_DEVICE_STATUSES,
    is_device_online_status,
    normalize_device_status,
)
from app.services.realtime_hub import realtime_hub
from app.services.system_metrics import metrics_collector

router = APIRouter()
SNAPSHOT_STALE_AFTER = timedelta(
    seconds=max(
        int(settings.DEVICE_STATUS_OFFLINE_GRACE_SECONDS + (settings.DEVICE_PRESENCE_MONITOR_INTERVAL_SEC * 2)),
        8,
    )
)


async def get_user_from_ws_token(db: AsyncSession, token: str) -> Optional[User]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
        user_id = int(token_data.sub)
    except (JWTError, ValidationError, TypeError, ValueError):
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user or not user.is_active:
        return None
    return user


async def get_allowed_device_ids(db: AsyncSession, user: User) -> Set[int]:
    if user.is_superuser:
        result = await db.execute(select(Device.id))
        return {int(row[0]) for row in result.all()}

    result = await db.execute(
        select(UserDeviceAccess.device_id).where(UserDeviceAccess.user_id == user.id)
    )
    return {int(row[0]) for row in result.all()}


async def get_snapshot_devices(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    if user.is_superuser:
        query = select(Device)
    else:
        query = (
            select(Device)
            .join(UserDeviceAccess, UserDeviceAccess.device_id == Device.id)
            .where(UserDeviceAccess.user_id == user.id)
        )

    result = await db.execute(query)
    devices = result.scalars().all()
    stream_context = await load_device_stream_context(db)
    runtime_status_map = device_runtime_state.list_by_ids([int(device.id) for device in devices])
    now = datetime.now(timezone.utc)
    payload: list[dict[str, Any]] = []
    for device in devices:
        fallback_stream_url = build_device_stream_url(device, stream_context)
        runtime_snapshot = runtime_status_map.get(int(device.id))
        if runtime_snapshot is None:
            payload.append(
                {
                    "device_id": device.id,
                    "status": DEVICE_STATUS_OFFLINE,
                    "online": False,
                    "stream_url": fallback_stream_url,
                    "checked_at": now.isoformat(timespec="seconds"),
                    "metadata": None,
                }
            )
            continue

        checked_at = runtime_snapshot.checked_at
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)

        normalized_status = normalize_device_status(runtime_snapshot.status)
        snapshot_stale = (now - checked_at) > SNAPSHOT_STALE_AFTER
        if snapshot_stale and normalized_status not in RUNTIME_ACTIVE_DEVICE_STATUSES:
            normalized_status = DEVICE_STATUS_OFFLINE
            online = False
        else:
            online = bool(runtime_snapshot.online) or is_device_online_status(normalized_status)

        payload.append(
            {
                "device_id": device.id,
                "status": normalized_status,
                "online": online,
                "stream_url": runtime_snapshot.stream_url or fallback_stream_url,
                "checked_at": checked_at.isoformat(timespec="seconds"),
                "metadata": runtime_snapshot.metadata if runtime_snapshot.metadata else None,
            }
        )
    return payload


@router.websocket("/ws")
async def websocket_realtime(
    websocket: WebSocket,
    token: str = Query(...),
    dashboard: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await get_user_from_ws_token(db, token)
    if not user:
        await websocket.close(code=1008)
        return

    allowed_device_ids = await get_allowed_device_ids(db, user)
    wants_manager_metrics = bool(user.is_superuser and dashboard == "manager")
    client_id = await realtime_hub.register(
        websocket=websocket,
        user_id=user.id,
        is_superuser=user.is_superuser,
        allowed_device_ids=allowed_device_ids,
        wants_manager_metrics=wants_manager_metrics,
    )

    try:
        manager_clients = await realtime_hub.manager_subscribers()
        await metrics_collector.set_manager_clients(manager_clients)

        await websocket.send_json(
            {
                "type": "snapshot",
                "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
                "devices": await get_snapshot_devices(db, user),
                "metrics": metrics_collector.current() if wants_manager_metrics else None,
            }
        )

        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_hub.unregister(client_id)
        manager_clients = await realtime_hub.manager_subscribers()
        await metrics_collector.set_manager_clients(manager_clients)
