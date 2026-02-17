from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from app.services.device_status import DEVICE_STATUS_OFFLINE, normalize_device_status


@dataclass(frozen=True)
class DeviceRuntimeSnapshot:
    device_id: int
    status: str
    online: bool
    checked_at: datetime
    stream_url: Optional[str]
    metadata: Optional[dict[str, str]]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_metadata(payload: Optional[dict[str, Any]]) -> Optional[dict[str, str]]:
    if not isinstance(payload, dict):
        return None
    normalized: dict[str, str] = {}
    for field in ("ip", "key", "protocol", "codec", "resolution", "audio_codec"):
        value = str(payload.get(field) or "").strip()
        if value:
            normalized[field] = value
    return normalized or None


class DeviceRuntimeStateStore:
    def __init__(self) -> None:
        self._items: dict[int, DeviceRuntimeSnapshot] = {}
        self._lock = Lock()

    def clear_all(self) -> None:
        with self._lock:
            self._items.clear()

    def clear(self, device_id: int) -> None:
        with self._lock:
            self._items.pop(int(device_id), None)

    def get(self, device_id: int) -> Optional[DeviceRuntimeSnapshot]:
        with self._lock:
            snapshot = self._items.get(int(device_id))
            if snapshot is None:
                return None
            return DeviceRuntimeSnapshot(
                device_id=snapshot.device_id,
                status=snapshot.status,
                online=snapshot.online,
                checked_at=snapshot.checked_at,
                stream_url=snapshot.stream_url,
                metadata=dict(snapshot.metadata) if snapshot.metadata else None,
            )

    def get_status(self, device_id: int, fallback: str = DEVICE_STATUS_OFFLINE) -> str:
        snapshot = self.get(device_id)
        if snapshot is None:
            return normalize_device_status(fallback)
        return normalize_device_status(snapshot.status, fallback=fallback)

    def upsert(
        self,
        *,
        device_id: int,
        status: str,
        online: bool,
        checked_at: Optional[datetime],
        stream_url: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> DeviceRuntimeSnapshot:
        normalized_checked_at = checked_at or _now_utc()
        normalized_status = normalize_device_status(status)
        normalized_metadata = _normalize_metadata(metadata)
        snapshot = DeviceRuntimeSnapshot(
            device_id=int(device_id),
            status=normalized_status,
            online=bool(online),
            checked_at=normalized_checked_at,
            stream_url=str(stream_url).strip() if stream_url else None,
            metadata=normalized_metadata,
        )
        with self._lock:
            self._items[int(device_id)] = snapshot
        return snapshot

    def list_by_ids(self, device_ids: list[int]) -> dict[int, DeviceRuntimeSnapshot]:
        result: dict[int, DeviceRuntimeSnapshot] = {}
        for device_id in device_ids:
            snapshot = self.get(int(device_id))
            if snapshot is not None:
                result[int(device_id)] = snapshot
        return result


device_runtime_state = DeviceRuntimeStateStore()

