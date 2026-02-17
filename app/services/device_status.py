from __future__ import annotations

from typing import Final

DEVICE_STATUS_OFFLINE: Final[str] = "Offline"
DEVICE_STATUS_ONLINE: Final[str] = "Online"
DEVICE_STATUS_CONNECTING: Final[str] = "Connecting"
DEVICE_STATUS_STARTING: Final[str] = "Starting"
DEVICE_STATUS_RECORDING: Final[str] = "Recording"
DEVICE_STATUS_STOPPING: Final[str] = "Stopping"

DEVICE_STATUS_VALUES: Final[tuple[str, ...]] = (
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_STARTING,
    DEVICE_STATUS_RECORDING,
    DEVICE_STATUS_STOPPING,
)

ONLINE_DEVICE_STATUSES: Final[frozenset[str]] = frozenset(
    {
        DEVICE_STATUS_ONLINE,
        DEVICE_STATUS_STARTING,
        DEVICE_STATUS_RECORDING,
        DEVICE_STATUS_STOPPING,
    }
)

RUNTIME_ACTIVE_DEVICE_STATUSES: Final[frozenset[str]] = frozenset(
    {
        DEVICE_STATUS_STARTING,
        DEVICE_STATUS_RECORDING,
        DEVICE_STATUS_STOPPING,
    }
)

_STATUS_MAP: Final[dict[str, str]] = {
    DEVICE_STATUS_OFFLINE.lower(): DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE.lower(): DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_CONNECTING.lower(): DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_STARTING.lower(): DEVICE_STATUS_STARTING,
    DEVICE_STATUS_RECORDING.lower(): DEVICE_STATUS_RECORDING,
    DEVICE_STATUS_STOPPING.lower(): DEVICE_STATUS_STOPPING,
}


def normalize_device_status(value: str | None, fallback: str = DEVICE_STATUS_OFFLINE) -> str:
    normalized_fallback = _STATUS_MAP.get(str(fallback or "").strip().lower(), DEVICE_STATUS_OFFLINE)
    raw = str(value or "").strip().lower()
    return _STATUS_MAP.get(raw, normalized_fallback)


def is_device_online_status(value: str | None) -> bool:
    return normalize_device_status(value) in ONLINE_DEVICE_STATUSES
