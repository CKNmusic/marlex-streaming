import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.device import Device
from app.services.device_status import (
    DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_RECORDING,
    RUNTIME_ACTIVE_DEVICE_STATUSES,
    is_device_online_status,
    normalize_device_status,
)
from app.services.device_stream_url import build_device_stream_url, load_device_stream_context
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_control import infer_protocol_from_source_type, ingest_api_get_json
from app.services.ingest_presence import stream_path_from_url
from app.services.ingest_stream_profile import (
    get_cached_stream_profile,
    normalize_protocol_from_url,
    schedule_stream_profile_probe,
)
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.device_runtime_state import device_runtime_state
from app.services.ingest_logging import log_ingest_info
from app.services.recorder import recorder_service
from app.services.realtime_events import emit_device_status
from app.services.stream_protocols import normalize_protocol_name

logger = logging.getLogger(__name__)


def _to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _is_within_grace(*, checked_at: datetime, last_seen: Optional[datetime], grace_seconds: int) -> bool:
    normalized_last_seen = _to_utc_naive(last_seen)
    if normalized_last_seen is None:
        return False
    normalized_checked_at = _to_utc_naive(checked_at) or checked_at
    return (normalized_checked_at - normalized_last_seen) <= timedelta(seconds=max(grace_seconds, 0))


def _index_paths(payload: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip("/")
        if not name:
            continue
        indexed[name] = item
    return indexed


def _probe_path_online(
    *,
    path_items: Optional[dict[str, dict[str, Any]]],
    stream_url: Optional[str],
) -> Optional[bool]:
    if path_items is None:
        return None
    if not stream_url:
        return None
    path_name = stream_path_from_url(stream_url)
    if not path_name:
        return None

    item = path_items.get(path_name)
    if item is None:
        return False

    is_online = bool(item.get("online") or item.get("ready") or item.get("available"))
    if not is_online:
        return False

    source = item.get("source") if isinstance(item, dict) else None
    source_type = str(source.get("type") or "").strip() if isinstance(source, dict) else ""
    source_protocol = infer_protocol_from_source_type(source_type)
    expected_protocol = normalize_protocol_name(urlparse(stream_url).scheme)
    if expected_protocol and source_protocol and source_protocol != expected_protocol:
        return False
    return True


class DevicePresenceMonitor:
    def __init__(self) -> None:
        self.enabled = bool(settings.DEVICE_PRESENCE_MONITOR_ENABLED)
        self.interval_sec = max(float(settings.DEVICE_PRESENCE_MONITOR_INTERVAL_SEC), 1.0)
        self.offline_grace_seconds = max(int(settings.DEVICE_STATUS_OFFLINE_GRACE_SECONDS), 0)
        self.connecting_timeout_seconds = max(int(settings.DEVICE_CONNECTING_TIMEOUT_SECONDS), 1)
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.enabled:
            logger.info("device_presence_monitor disabled by configuration")
            return
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "device_presence_monitor started interval_sec=%s grace_sec=%s connecting_timeout_sec=%s",
            self.interval_sec,
            self.offline_grace_seconds,
            self.connecting_timeout_seconds,
        )

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        try:
            await self._task
        except Exception:
            logger.exception("device_presence_monitor failed while stopping")
        self._task = None
        logger.info("device_presence_monitor stopped")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with SessionLocal() as db:
                    await self.scan_once(db)
            except Exception:
                logger.exception("device_presence_monitor scan failed")
            await asyncio.sleep(self.interval_sec)

    async def _load_paths_snapshot(self) -> Optional[dict[str, dict[str, Any]]]:
        payload = await ingest_api_get_json("/paths/list")
        if payload is None:
            return None
        return _index_paths(payload)

    async def scan_once(self, db: AsyncSession) -> int:
        devices_result = await db.execute(select(Device).where(Device.is_active.is_(True)))
        devices = devices_result.scalars().all()
        if not devices:
            return 0

        stream_context = await load_device_stream_context(db)
        path_items = await self._load_paths_snapshot()
        logger.info("device_presence_monitor scan paths_count=%d paths=%s", len(path_items or {}), list((path_items or {}).keys()))
        checked_at = datetime.now(timezone.utc)

        transition_events: list[dict[str, Any]] = []
        updated = 0

        for device in devices:
            stream_url = build_device_stream_url(device, stream_context)
            runtime_snapshot = device_runtime_state.get(int(device.id))
            persisted_status = normalize_device_status(
                runtime_snapshot.status if runtime_snapshot is not None else None,
                fallback=DEVICE_STATUS_OFFLINE,
            )
            persisted_online = bool(runtime_snapshot.online) if runtime_snapshot is not None else False
            persisted_checked_at = runtime_snapshot.checked_at if runtime_snapshot is not None else None
            persisted_metadata = runtime_snapshot.metadata if runtime_snapshot is not None else None
            runtime_status = normalize_device_status(recorder_service.get_state(device.id))
            is_recording = recorder_service.is_recording(device.id)
            has_recent_publish = ingest_publish_state.has_recent_publish(
                int(device.id),
                within_seconds=self.connecting_timeout_seconds,
            )

            next_status = persisted_status
            next_online = persisted_online
            should_refresh_last_seen = False
            reason = "unchanged"
            metadata: Optional[dict[str, Any]] = None

            if runtime_status in RUNTIME_ACTIVE_DEVICE_STATUSES:
                next_status = runtime_status
                next_online = True
                should_refresh_last_seen = True
                reason = "runtime_active"
            elif is_recording:
                next_status = DEVICE_STATUS_RECORDING
                next_online = True
                should_refresh_last_seen = True
                reason = "recording_active"
            else:
                ingest_online = _probe_path_online(path_items=path_items, stream_url=stream_url)
                if ingest_online is True:
                    metadata = ingest_runtime_metadata.update_protocol_hint(
                        device_key=device.key,
                        protocol=normalize_protocol_from_url(stream_url or ""),
                    )
                    cached_profile = get_cached_stream_profile(device.key or "")
                    if cached_profile:
                        metadata = ingest_runtime_metadata.update_from_stream_profile(
                            device_key=device.key,
                            profile=cached_profile,
                        )
                    metadata = ingest_runtime_metadata.sanitize(metadata)

                    if ingest_runtime_metadata.is_complete(metadata):
                        next_online = True
                        next_status = DEVICE_STATUS_ONLINE
                        should_refresh_last_seen = True
                        reason = "ingest_online_metadata_ready"
                    else:
                        next_online = False
                        next_status = DEVICE_STATUS_CONNECTING
                        # Keep runtime heartbeat fresh while ingest is online but metadata is still completing.
                        should_refresh_last_seen = True
                        reason = "ingest_online_metadata_pending"
                        schedule_stream_profile_probe(
                            device_key=device.key or "",
                            stream_url=stream_url,
                            protocol=metadata.get("protocol") if isinstance(metadata, dict) else None,
                            context="presence_monitor:metadata_pending",
                        )
                elif has_recent_publish:
                    next_online = False
                    next_status = DEVICE_STATUS_CONNECTING
                    # A recently accepted publish is a valid runtime signal.
                    should_refresh_last_seen = True
                    reason = "connecting_wait_ingest" if ingest_online is False else "connecting_ingest_unreachable"
                elif ingest_online is None:
                    can_keep_online_in_grace = (
                        persisted_online
                        or is_device_online_status(persisted_status)
                    )
                    if _is_within_grace(
                        checked_at=checked_at,
                        last_seen=persisted_checked_at,
                        grace_seconds=self.offline_grace_seconds,
                    ) and can_keep_online_in_grace:
                        next_online = True
                        next_status = (
                            persisted_status
                            if is_device_online_status(persisted_status)
                            else DEVICE_STATUS_ONLINE
                        )
                        reason = "ingest_unreachable_grace"
                    else:
                        next_online = False
                        next_status = DEVICE_STATUS_OFFLINE
                        reason = "ingest_unreachable_timeout"
                    should_refresh_last_seen = False
                else:
                    next_online = False
                    can_keep_online_in_grace = (
                        persisted_online
                        or is_device_online_status(persisted_status)
                    )
                    if (
                        _is_within_grace(
                            checked_at=checked_at,
                            last_seen=persisted_checked_at,
                            grace_seconds=self.offline_grace_seconds,
                        ) and can_keep_online_in_grace
                    ):
                        next_online = True
                        reason = "grace"
                    else:
                        reason = "ingest_offline"
                    next_status = DEVICE_STATUS_ONLINE if next_online else DEVICE_STATUS_OFFLINE
                    # Keep grace window fixed to the last real signal; never extend it.
                    should_refresh_last_seen = False
                    if not next_online:
                        ingest_runtime_metadata.clear(device.key)
                        metadata = None

            next_metadata = ingest_runtime_metadata.sanitize(metadata or ingest_runtime_metadata.get(device.key))
            metadata_changed = (persisted_metadata or None) != (next_metadata or None)
            changed = (
                (persisted_status != next_status)
                or (persisted_online != next_online)
                or metadata_changed
            )
            if changed:
                updated += 1
                transition_events.append(
                    {
                        "device_id": int(device.id),
                        "device_key": str(device.key or ""),
                        "status": next_status,
                        "online": next_online,
                        "stream_url": stream_url,
                        "checked_at": checked_at,
                        "detail": f"presence_monitor:{reason}",
                        "reason": reason,
                        "from_status": persisted_status,
                        "to_status": next_status,
                        "metadata": next_metadata,
                    }
                )

            if not changed:
                effective_checked_at = checked_at if should_refresh_last_seen else (persisted_checked_at or checked_at)
                device_runtime_state.upsert(
                    device_id=int(device.id),
                    status=next_status,
                    online=next_online,
                    stream_url=stream_url,
                    checked_at=effective_checked_at,
                    metadata=next_metadata,
                )

        if not transition_events:
            return 0

        for event in transition_events:
            device_runtime_state.upsert(
                device_id=int(event["device_id"]),
                status=str(event["status"]),
                online=bool(event["online"]),
                stream_url=event["stream_url"],
                checked_at=event["checked_at"],
                metadata=event.get("metadata"),
            )
            logger.info(
                "device_presence_transition key=%s device_id=%s from=%s to=%s online=%s reason=%s",
                event["device_key"] or "-",
                event["device_id"],
                event["from_status"],
                event["to_status"],
                event["online"],
                event["detail"],
            )
            log_ingest_info(
                event["device_key"] or "-",
                (
                    "presence_transition "
                    f"device_id={event['device_id']} "
                    f"from={event['from_status']} to={event['to_status']} "
                    f"online={event['online']} reason={event['reason']}"
                ),
            )
            if (
                event["online"]
                and not is_device_online_status(event["from_status"])
                and is_device_online_status(event["to_status"])
                and event["reason"] in {"ingest_online", "runtime_active", "recording_active"}
            ):
                schedule_stream_profile_probe(
                    device_key=event["device_key"],
                    stream_url=event["stream_url"],
                    protocol=None,
                    context=f"presence_monitor:{event['to_status']}",
                )
            await emit_device_status(
                db,
                device_id=event["device_id"],
                status=event["status"],
                online=event["online"],
                stream_url=event["stream_url"],
                checked_at=event["checked_at"],
                detail=event["detail"],
                metadata=event.get("metadata"),
            )
        return updated


device_presence_monitor = DevicePresenceMonitor()
