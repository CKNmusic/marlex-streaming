import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_device_access import UserDeviceAccess
from app.services.device_runtime_state import device_runtime_state
from app.services.device_status import normalize_device_status
from app.services.event_bus import realtime_event_bus
from app.services.realtime_hub import (
    META_MANAGERS_ONLY,
    META_TARGET_DEVICE_ID,
    META_TARGET_USER_IDS,
)

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_last_device_status_payload: dict[int, tuple[str, bool, str]] = {}


def reset_device_status_cache() -> None:
    _last_device_status_payload.clear()
    device_runtime_state.clear_all()


async def resolve_device_user_ids(db: AsyncSession, device_id: int) -> Set[int]:
    result = await db.execute(select(UserDeviceAccess.user_id).where(UserDeviceAccess.device_id == device_id))
    return {int(row[0]) for row in result.all()}


async def emit_device_status(
    db: AsyncSession,
    *,
    device_id: int,
    status: str,
    online: bool,
    stream_url: Optional[str],
    checked_at: Optional[datetime] = None,
    detail: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> None:
    normalized_metadata: dict[str, Any] = {}
    if isinstance(metadata, dict):
        for field in ("ip", "key", "protocol", "codec", "resolution", "audio_codec"):
            value = metadata.get(field)
            normalized_value = str(value or "").strip()
            if normalized_value:
                normalized_metadata[field] = normalized_value
    metadata_signature = json.dumps(normalized_metadata, sort_keys=True, ensure_ascii=True)
    normalized_status = normalize_device_status(status)
    normalized_online = bool(online)
    current_state = (normalized_status, normalized_online, metadata_signature)
    if not force and _last_device_status_payload.get(int(device_id)) == current_state:
        logger.info(
            "emit_device_status SKIPPED (dedup) device_id=%s key=%s status=%s online=%s detail=%s",
            device_id,
            normalized_metadata.get("key", "-"),
            normalized_status,
            normalized_online,
            detail or "-",
        )
        return
    _last_device_status_payload[int(device_id)] = current_state
    snapshot = device_runtime_state.upsert(
        device_id=int(device_id),
        status=normalized_status,
        online=normalized_online,
        stream_url=stream_url,
        checked_at=checked_at,
        metadata=normalized_metadata,
    )

    user_ids = await resolve_device_user_ids(db, device_id)
    payload = {
        "type": "device_status",
        "timestamp": now_iso(),
        "device_id": device_id,
        "status": normalized_status,
        "online": normalized_online,
        "stream_url": stream_url,
        "checked_at": snapshot.checked_at.isoformat(timespec="seconds"),
        "detail": detail,
        "metadata": normalized_metadata or None,
        META_TARGET_DEVICE_ID: device_id,
        META_TARGET_USER_IDS: sorted(user_ids) if user_ids else None,
    }
    logger.info(
        "emit_device_status SENT device_id=%s key=%s status=%s online=%s detail=%s target_users=%s",
        device_id,
        normalized_metadata.get("key", "-"),
        normalized_status,
        normalized_online,
        detail or "-",
        sorted(user_ids) if user_ids else "none",
    )
    await realtime_event_bus.publish(payload)


async def emit_record_status(
    db: AsyncSession,
    *,
    record_id: int,
    device_id: int,
    owner_id: int,
    status: str,
    final_status: Optional[str],
    stop_reason: Optional[str],
    end_time: Optional[datetime],
    detail: Optional[str] = None,
) -> None:
    # User-level record updates are private: only the record owner receives them.
    # Superusers still receive all events via RealtimeHub manager override.
    user_ids = {owner_id}
    payload = {
        "type": "record_status",
        "timestamp": now_iso(),
        "record_id": record_id,
        "device_id": device_id,
        "owner_id": owner_id,
        "status": status,
        "final_status": final_status,
        "stop_reason": stop_reason,
        "end_time": end_time.isoformat(timespec="seconds") if end_time else None,
        "detail": detail,
        META_TARGET_DEVICE_ID: device_id,
        META_TARGET_USER_IDS: sorted(user_ids) if user_ids else None,
    }
    await realtime_event_bus.publish(payload)


async def emit_manager_metrics(payload: dict[str, object]) -> None:
    event_payload = {
        "type": "manager_metrics",
        "timestamp": now_iso(),
        "metrics": payload,
        META_MANAGERS_ONLY: True,
    }
    await realtime_event_bus.publish(event_payload)
