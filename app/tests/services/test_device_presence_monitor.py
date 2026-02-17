from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.city import City
from app.models.device import Device
from app.models.place import Place
from app.services.device_presence_monitor import DevicePresenceMonitor
from app.services.device_runtime_state import device_runtime_state
from app.services.device_status import (
    DEVICE_STATUS_CONNECTING,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_ONLINE,
    DEVICE_STATUS_STARTING,
)
from app.services.ingest_publish_state import ingest_publish_state
from app.services.ingest_runtime_metadata import ingest_runtime_metadata
from app.services.recorder import recorder_service


async def _seed_device(db, *, status: str, last_seen: datetime | None) -> Device:
    suffix = uuid4().hex[:8]
    city = City(name=f"Cidade Monitor {suffix}", uf="SP")
    db.add(city)
    await db.flush()

    place = Place(name=f"Sala Monitor {suffix}", city_id=city.id, is_active=True)
    db.add(place)
    await db.flush()

    device = Device(
        model="Modelo Monitor",
        sn=f"SN-MONITOR-{suffix}",
        place_id=place.id,
        is_active=True,
        status=status,
        last_seen=last_seen,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@pytest.mark.asyncio
async def test_presence_monitor_marks_device_offline_when_stream_disappears(db, monkeypatch: pytest.MonkeyPatch) -> None:
    device = await _seed_device(
        db,
        status=DEVICE_STATUS_ONLINE,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    emitted: list[dict] = []

    async def fake_load_paths_snapshot() -> dict:
        return {}

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)

    updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert updated >= 0
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_OFFLINE
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    if matching:
        assert matching[-1]["status"] == DEVICE_STATUS_OFFLINE
        assert str(matching[-1]["detail"]).startswith("presence_monitor:")


@pytest.mark.asyncio
async def test_presence_monitor_does_not_emit_when_status_is_unchanged(db, monkeypatch: pytest.MonkeyPatch) -> None:
    device = await _seed_device(db, status=DEVICE_STATUS_OFFLINE, last_seen=None)
    emitted: list[dict] = []

    async def fake_load_paths_snapshot() -> dict:
        return {}

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)

    updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert updated >= 0
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_OFFLINE
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    assert matching == []


@pytest.mark.asyncio
async def test_presence_monitor_promotes_runtime_active_state(db, monkeypatch: pytest.MonkeyPatch) -> None:
    device = await _seed_device(db, status=DEVICE_STATUS_OFFLINE, last_seen=None)
    emitted: list[dict] = []

    async def fake_load_paths_snapshot() -> dict:
        return {}

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)
    monkeypatch.setattr(
        recorder_service,
        "get_state",
        lambda _device_id: DEVICE_STATUS_STARTING if int(_device_id) == int(device.id) else DEVICE_STATUS_OFFLINE,
    )
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert updated >= 1
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_STARTING
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    assert matching
    assert matching[-1]["status"] == DEVICE_STATUS_STARTING


@pytest.mark.asyncio
async def test_presence_monitor_marks_offline_when_ingest_api_is_unreachable_after_grace(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = await _seed_device(
        db,
        status=DEVICE_STATUS_ONLINE,
        last_seen=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    emitted: list[dict] = []

    async def fake_load_paths_snapshot():
        return None

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)
    monkeypatch.setattr(recorder_service, "get_state", lambda _device_id: DEVICE_STATUS_OFFLINE)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert updated >= 0
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_OFFLINE
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    if matching:
        assert matching[-1]["status"] == DEVICE_STATUS_OFFLINE
        assert matching[-1]["detail"] == "presence_monitor:ingest_unreachable_timeout"


@pytest.mark.asyncio
async def test_presence_monitor_sets_connecting_when_recent_publish_exists(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = await _seed_device(
        db,
        status=DEVICE_STATUS_OFFLINE,
        last_seen=None,
    )
    emitted: list[dict] = []

    async def fake_load_paths_snapshot():
        return {}

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0
    monitor.connecting_timeout_seconds = 60

    ingest_publish_state.clear_all()
    ingest_publish_state.mark_publish(device.id)

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)
    monkeypatch.setattr(recorder_service, "get_state", lambda _device_id: DEVICE_STATUS_OFFLINE)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert updated >= 1
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_CONNECTING
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    assert matching
    assert matching[-1]["status"] == DEVICE_STATUS_CONNECTING
    assert matching[-1]["detail"] == "presence_monitor:connecting_wait_ingest"
    ingest_publish_state.clear_all()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paths_snapshot",
    [
        None,
        {},
    ],
)
async def test_presence_monitor_does_not_promote_offline_to_online_from_grace_without_real_signal(
    db,
    monkeypatch: pytest.MonkeyPatch,
    paths_snapshot,
) -> None:
    device = await _seed_device(db, status=DEVICE_STATUS_OFFLINE, last_seen=None)
    emitted: list[dict] = []

    async def fake_load_paths_snapshot():
        return paths_snapshot

    async def fake_emit_device_status(*_args, **kwargs) -> None:
        emitted.append(kwargs)

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 60

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)
    monkeypatch.setattr(recorder_service, "get_state", lambda _device_id: DEVICE_STATUS_OFFLINE)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    first_updated = await monitor.scan_once(db)
    second_updated = await monitor.scan_once(db)
    snapshot = device_runtime_state.get(device.id)

    assert first_updated >= 0
    assert second_updated >= 0
    assert snapshot is not None
    assert snapshot.status == DEVICE_STATUS_OFFLINE
    matching = [item for item in emitted if int(item["device_id"]) == int(device.id)]
    assert all(item["status"] != DEVICE_STATUS_ONLINE for item in matching)


@pytest.mark.asyncio
async def test_presence_monitor_keeps_connecting_checked_at_fresh_while_ingest_online_metadata_pending(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = await _seed_device(
        db,
        status=DEVICE_STATUS_OFFLINE,
        last_seen=None,
    )

    path_name = f"surgwaze/v1/{device.key}/stream"

    async def fake_load_paths_snapshot():
        return {
            path_name: {
                "name": path_name,
                "online": True,
            }
        }

    async def fake_emit_device_status(*_args, **_kwargs) -> None:
        return None

    monitor = DevicePresenceMonitor()
    monitor.offline_grace_seconds = 0

    ingest_publish_state.clear_all()
    ingest_runtime_metadata.clear_all()

    monkeypatch.setattr(monitor, "_load_paths_snapshot", fake_load_paths_snapshot)
    monkeypatch.setattr("app.services.device_presence_monitor.emit_device_status", fake_emit_device_status)
    monkeypatch.setattr(recorder_service, "get_state", lambda _device_id: DEVICE_STATUS_OFFLINE)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    first_updated = await monitor.scan_once(db)
    first_snapshot = device_runtime_state.get(device.id)
    assert first_updated >= 1
    assert first_snapshot is not None
    assert first_snapshot.status == DEVICE_STATUS_CONNECTING

    second_updated = await monitor.scan_once(db)
    second_snapshot = device_runtime_state.get(device.id)
    assert second_updated >= 0
    assert second_snapshot is not None
    assert second_snapshot.status == DEVICE_STATUS_CONNECTING
    assert second_snapshot.checked_at >= first_snapshot.checked_at
