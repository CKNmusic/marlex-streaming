from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IngestPublishState:
    """
    Lightweight in-memory tracker for recently accepted ingest publish attempts.
    Used to expose transitional device status ("Connecting") while stream path is
    still stabilizing on the ingest side.
    """

    def __init__(self) -> None:
        self._last_publish_by_device: Dict[int, datetime] = {}
        self._lock = Lock()

    def mark_publish(self, device_id: int, *, checked_at: Optional[datetime] = None) -> None:
        device_key = int(device_id)
        timestamp = _to_utc_aware(checked_at) if checked_at is not None else _utcnow()
        with self._lock:
            self._last_publish_by_device[device_key] = timestamp

    def clear(self, device_id: int) -> None:
        device_key = int(device_id)
        with self._lock:
            self._last_publish_by_device.pop(device_key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._last_publish_by_device.clear()

    def last_publish(self, device_id: int) -> Optional[datetime]:
        device_key = int(device_id)
        with self._lock:
            return self._last_publish_by_device.get(device_key)

    def has_recent_publish(self, device_id: int, *, within_seconds: int) -> bool:
        last_seen = self.last_publish(device_id)
        if last_seen is None:
            return False
        timeout = max(int(within_seconds), 1)
        return (_utcnow() - _to_utc_aware(last_seen)) <= timedelta(seconds=timeout)


ingest_publish_state = IngestPublishState()
