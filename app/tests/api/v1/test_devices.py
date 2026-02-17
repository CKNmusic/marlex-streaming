from datetime import datetime, timedelta, timezone

import pytest
import hashlib
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings


@pytest.mark.asyncio
async def test_create_device_and_key_generation(client: AsyncClient, db: AsyncSession):
    # 1. Login as admin (mock or use real login if needed)
    # For now, let's assume we have a superuser in the test DB
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    
    admin = User(
        username="admin_test",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True
    )
    db.add(admin)
    city = City(name="Cidade Teste", uf="TS")
    db.add(city)
    await db.flush()
    place = Place(name="Local Teste", description="Sala A", city_id=city.id)
    db.add(place)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(place)
    
    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 2. Add Device
    device_data = {
        "name": "Test Device",
        "sn": "SN123456789",
        "place_id": place.id,
        "is_active": True
    }
    
    response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json=device_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == device_data["name"]
    assert data["sn"] == device_data["sn"]
    assert "key" in data
    
    # 3. Verify KEY generation logic (SHA1 of ID + SN)
    device_id = data["id"]
    expected_raw = f"{device_id}{device_data['sn']}"
    expected_key = hashlib.md5(expected_raw.encode()).hexdigest()[:12]
    assert data["key"] == expected_key
    
    # 4. List Devices
    response = await client.get(f"{settings.API_V1_STR}/devices/", headers=headers)
    assert response.status_code == 200
    assert any(d["sn"] == "SN123456789" for d in response.json())
    
    # 5. Edit Device
    edit_data = {"name": "Updated Device Name"}
    response = await client.patch(
        f"{settings.API_V1_STR}/devices/{device_id}",
        json=edit_data,
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Device Name"
    
    # 6. Remove Device
    response = await client.delete(
        f"{settings.API_V1_STR}/devices/{device_id}",
        headers=headers
    )
    assert response.status_code == 200
    
    # Verify removal
    response = await client.get(f"{settings.API_V1_STR}/devices/", headers=headers)
    assert not any(d["id"] == device_id for d in response.json())


@pytest.mark.asyncio
async def test_create_device_duplicate_sn_returns_conflict(client: AsyncClient, db: AsyncSession):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place

    admin = User(
        username="admin_dup_device",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade Dup", uf="DP")
    db.add(city)
    await db.flush()
    place = Place(name="Local Dup", description="Sala Dup", city_id=city.id)
    db.add(place)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(place)

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}

    payload = {
        "name": "Device DUP A",
        "sn": "SN-DUP-0001",
        "place_id": place.id,
        "is_active": True,
    }
    response = await client.post(f"{settings.API_V1_STR}/devices/", json=payload, headers=headers)
    assert response.status_code == 200

    response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={
            "name": "Device DUP B",
            "sn": "SN-DUP-0001",
            "place_id": place.id,
            "is_active": True,
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert "SN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_read_devices_refreshes_only_list_slice_and_defaults_offline(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.api.v1.endpoints import devices as devices_endpoint
    from app.schemas.device import DeviceStatus as DeviceStatusSchema
    from app.services.device_runtime_state import device_runtime_state

    admin = User(
        username="admin_devices_slice_refresh",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    city = City(name="Cidade Slice", uf="SL")
    db.add_all([admin, city])
    await db.flush()
    place = Place(name="Local Slice", description="Sala Slice", city_id=city.id)
    db.add(place)
    await db.flush()

    device_a = Device(model="Modelo A", sn="SN-SLICE-001", place_id=place.id, is_active=True)
    device_b = Device(model="Modelo B", sn="SN-SLICE-002", place_id=place.id, is_active=True)
    db.add_all([device_a, device_b])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device_a)
    await db.refresh(device_b)

    checked_at_seed = datetime.now(timezone.utc)
    device_runtime_state.upsert(
        device_id=device_a.id,
        status="Online",
        online=True,
        checked_at=checked_at_seed,
        stream_url="srt://seed/device-a",
    )
    device_runtime_state.upsert(
        device_id=device_b.id,
        status="Online",
        online=True,
        checked_at=checked_at_seed,
        stream_url="srt://seed/device-b",
    )

    refreshed_calls: list[tuple[int, str, bool]] = []

    async def fake_refresh(_db, *, device, detail: str, use_grace: bool = True):
        refreshed_calls.append((int(device.id), detail, bool(use_grace)))
        checked_at = datetime.now(timezone.utc)
        device_runtime_state.upsert(
            device_id=int(device.id),
            status="Offline",
            online=False,
            checked_at=checked_at,
            stream_url=None,
        )
        return DeviceStatusSchema(
            device_id=int(device.id),
            online=False,
            status="Offline",
            stream_url=None,
            checked_at=checked_at,
            metadata=None,
        )

    monkeypatch.setattr(devices_endpoint, "refresh_device_runtime_status", fake_refresh)

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/?skip=0&limit=1", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "Offline"

    # list endpoint must not perform active refresh/probe; only runtime snapshot overlay.
    assert len(refreshed_calls) == 0

    untouched_id = device_b.id
    untouched_snapshot = device_runtime_state.get(untouched_id)
    assert untouched_snapshot is not None
    assert untouched_snapshot.status == "Online"


@pytest.mark.asyncio
async def test_create_device_allows_same_sn_for_different_marks(client: AsyncClient, db: AsyncSession):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place

    admin = User(
        username="admin_dup_mark_device",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade Dup Marca", uf="DM")
    db.add(city)
    await db.flush()
    place = Place(name="Local Dup Marca", description="Sala Dup Marca", city_id=city.id)
    db.add(place)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(place)

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}

    base_payload = {
        "sn": "SN-SHARED-0001",
        "place_id": place.id,
        "is_active": True,
        "protocol": "srt",
    }

    first = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={**base_payload, "mark_name": "MarcaA", "model": "ModeloA"},
        headers=headers,
    )
    assert first.status_code == 200

    second = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={**base_payload, "mark_name": "MarcaB", "model": "ModeloB"},
        headers=headers,
    )
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_device_status_values_are_limited(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.api.v1.endpoints import devices as devices_endpoint

    admin = User(
        username="admin_status_test",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade Status", uf="SS")
    db.add(city)
    await db.flush()
    place = Place(name="Local Status", description="Sala S", city_id=city.id)
    db.add(place)
    await db.flush()
    device = Device(name="Device Status", sn="SN-STATUS-001", place_id=place.id, is_active=True)
    db.add(device)
    await db.commit()
    await db.refresh(admin)

    async def always_offline(_stream_url):
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    allowed = {"Offline", "Connecting", "Online", "Starting", "Recording", "Stopping"}
    assert response.json()
    for item in response.json():
        assert item["status"] in allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_state", ["Starting", "Stopping", "Recording"])
async def test_device_status_returns_runtime_transitional_state(
    runtime_state: str,
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.api.v1.endpoints import devices as devices_endpoint

    admin = User(
        username=f"admin_runtime_{runtime_state.lower()}",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name=f"Cidade {runtime_state}", uf="RT")
    db.add(city)
    await db.flush()
    place = Place(name=f"Local {runtime_state}", description="Sala RT", city_id=city.id)
    db.add(place)
    await db.flush()
    device = Device(name=f"Device {runtime_state}", sn=f"SN-RT-{runtime_state}", place_id=place.id, is_active=True)
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_offline(_stream_url):
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: runtime_state)
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: runtime_state == "Recording")

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload
    status_row = next((item for item in payload if item["device_id"] == device.id), None)
    assert status_row is not None
    assert status_row["status"] == runtime_state
    assert status_row["online"] is True


@pytest.mark.asyncio
async def test_device_status_does_not_keep_active_state_from_open_record_without_signal(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.models.record import Record
    from app.api.v1.endpoints import devices as devices_endpoint

    admin = User(
        username="admin_open_record_status",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade Open Record", uf="OR")
    db.add(city)
    await db.flush()
    place = Place(name="Local Open Record", description="Sala OR", city_id=city.id)
    db.add(place)
    await db.flush()
    device = Device(model="Device Open Record", sn="SN-OPEN-STATUS-001", place_id=place.id, is_active=True, status="Starting")
    db.add(device)
    await db.flush()
    open_record = Record(
        owner_id=admin.id,
        device_id=device.id,
        place_id=place.id,
        title="Open Record Status",
    )
    db.add(open_record)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_offline(_stream_url):
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    status_row = next((item for item in payload if item["device_id"] == device.id), None)
    assert status_row is not None
    assert status_row["status"] == "Offline"
    assert status_row["online"] is False


@pytest.mark.asyncio
async def test_device_status_ignores_db_last_seen_when_runtime_has_no_signal(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.api.v1.endpoints import devices as devices_endpoint

    admin = User(
        username="admin_tz_grace",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade TZ Grace", uf="TG")
    db.add(city)
    await db.flush()
    place = Place(name="Local TZ Grace", description="Sala TG", city_id=city.id)
    db.add(place)
    await db.flush()
    device = Device(
        model="Device TZ Grace",
        sn="SN-TZ-GRACE-001",
        place_id=place.id,
        is_active=True,
        status="Online",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_offline(_stream_url):
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    status_row = next((item for item in payload if item["device_id"] == device.id), None)
    assert status_row is not None
    assert status_row["status"] == "Offline"
    assert status_row["online"] is False


@pytest.mark.asyncio
async def test_device_status_uses_runtime_presence_only_and_keeps_db_last_seen(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.api.v1.endpoints import devices as devices_endpoint

    admin = User(
        username="admin_grace_no_refresh",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    city = City(name="Cidade Grace Persist", uf="GP")
    db.add(city)
    await db.flush()
    place = Place(name="Local Grace Persist", description="Sala GP", city_id=city.id)
    db.add(place)
    await db.flush()
    grace_seconds = max(int(settings.DEVICE_STATUS_OFFLINE_GRACE_SECONDS), 0)
    initial_last_seen = datetime.now(timezone.utc) - timedelta(
        seconds=max(grace_seconds - 1, 0)
    )
    device = Device(
        model="Device Grace Persist",
        sn="SN-GRACE-PERSIST-001",
        place_id=place.id,
        is_active=True,
        status="Online",
        last_seen=initial_last_seen,
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_offline(_stream_url):
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    status_row = next((item for item in payload if item["device_id"] == device.id), None)
    assert status_row is not None
    assert status_row["status"] == "Offline"
    assert status_row["online"] is False

    await db.refresh(device)
    assert device.last_seen == initial_last_seen


@pytest.mark.asyncio
async def test_bind_device_is_idempotent(client: AsyncClient, db: AsyncSession):
    from app.core import security
    from app.models.user import User
    from app.models.city import City
    from app.models.place import Place
    from app.models.device import Device
    from app.models.user_device_access import UserDeviceAccess
    from sqlalchemy import select, func

    user = User(
        username="user_bind_idempotent",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    city = City(name="Cidade Bind", uf="BD")
    db.add_all([user, city])
    await db.flush()
    place = Place(name="Local Bind", description="Sala Bind", city_id=city.id)
    db.add(place)
    await db.flush()
    device = Device(model="Device Bind", sn="SN-BIND-001", place_id=place.id, is_active=True)
    db.add(device)
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)

    token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"key": device.key}

    first = await client.post(f"{settings.API_V1_STR}/devices/bind", json=body, headers=headers)
    assert first.status_code == 200

    second = await client.post(f"{settings.API_V1_STR}/devices/bind", json=body, headers=headers)
    assert second.status_code == 200

    count_result = await db.execute(
        select(func.count(UserDeviceAccess.id)).where(
            UserDeviceAccess.user_id == user.id,
            UserDeviceAccess.device_id == device.id,
        )
    )
    assert int(count_result.scalar() or 0) == 1


@pytest.mark.asyncio
async def test_probe_stream_without_ingest_or_ffprobe_is_offline_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1.endpoints import devices as devices_endpoint

    async def ingest_unknown(_stream_url):
        return None

    monkeypatch.setattr(devices_endpoint, "ingest_stream_url_is_online", ingest_unknown)
    monkeypatch.setattr(devices_endpoint.shutil, "which", lambda _name: None)

    online = await devices_endpoint.probe_stream("rtmp://127.0.0.1:8554/surgwaze/v1/device/stream")
    assert online is False


@pytest.mark.asyncio
async def test_probe_stream_timeout_kills_subprocess(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1.endpoints import devices as devices_endpoint

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None
            self.killed = False
            self.wait_calls = 0

        async def wait(self):
            self.wait_calls += 1
            await asyncio.sleep(0)
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

    proc = FakeProcess()

    async def ingest_unknown(_stream_url):
        return None

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return proc

    async def fake_wait_for(_awaitable, timeout):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(devices_endpoint.settings, "STREAM_PROBE_ALLOW_FFMPEG_FALLBACK", True)
    monkeypatch.setattr(devices_endpoint, "ingest_stream_url_is_online", ingest_unknown)
    monkeypatch.setattr(devices_endpoint.shutil, "which", lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
    monkeypatch.setattr(devices_endpoint.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(devices_endpoint.asyncio, "wait_for", fake_wait_for)

    online = await devices_endpoint.probe_stream("rtsp://127.0.0.1/surgwaze/v1/device/stream")

    assert online is False
    assert proc.killed is True
    assert proc.wait_calls >= 1


@pytest.mark.asyncio
async def test_devices_status_builds_srt_url_when_device_protocol_is_srt(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.city import City
    from app.models.device import Device
    from app.models.place import Place
    from app.models.protocol import Protocol
    from app.models.user import User
    from app.api.v1.endpoints import devices as devices_endpoint
    from sqlalchemy import select

    admin = User(
        username="admin_srt_status",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    city = City(name="Cidade SRT", uf="SR")
    db.add_all([admin, city])
    await db.flush()

    place = Place(name="Local SRT", description="Sala SRT", city_id=city.id)
    db.add(place)
    await db.flush()

    rtmp = (await db.execute(select(Protocol).where(Protocol.protocol == "rtmp"))).scalars().first()
    if rtmp is None:
        db.add(Protocol(protocol="rtmp", port=8554, is_active=True))
    else:
        rtmp.port = 8554
        rtmp.is_active = True
        db.add(rtmp)

    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    if srt is None:
        db.add(Protocol(protocol="srt", port=9000, is_active=True))
    else:
        srt.port = 9000
        srt.is_active = True
        db.add(srt)
    await db.flush()

    device = Device(
        name="Device SRT",
        sn="SN-SRT-001",
        place_id=place.id,
        protocol_id=srt.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_offline(_stream_url: str | None) -> bool:
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(f"{settings.API_V1_STR}/devices/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    item = next((row for row in payload if row["device_id"] == device.id), None)
    assert item is not None
    assert item["stream_url"].startswith("srt://")


@pytest.mark.asyncio
async def test_update_device_rejects_protocol_not_in_active_registry(client: AsyncClient, db: AsyncSession):
    from app.core import security
    from app.models.city import City
    from app.models.device import Device
    from app.models.place import Place
    from app.models.protocol import Protocol
    from app.models.user import User
    from sqlalchemy import select

    admin = User(
        username="admin_invalid_protocol",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    city = City(name="Cidade Proto", uf="PR")
    db.add_all([admin, city])
    await db.flush()
    place = Place(name="Local Proto", description="Sala Proto", city_id=city.id)
    db.add(place)
    await db.flush()

    rtmp = (await db.execute(select(Protocol).where(Protocol.protocol == "rtmp"))).scalars().first()
    if rtmp is None:
        db.add(Protocol(protocol="rtmp", port=8554, is_active=True))
    else:
        rtmp.port = 8554
        rtmp.is_active = True
        db.add(rtmp)

    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    if srt is None:
        db.add(Protocol(protocol="srt", port=9000, is_active=False))
    else:
        srt.port = 9000
        srt.is_active = False
        db.add(srt)
    await db.flush()

    device = Device(name="Device Proto", sn="SN-PROTO-001", place_id=place.id, is_active=True)
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.patch(
        f"{settings.API_V1_STR}/devices/{device.id}",
        json={"protocol": "srt"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "ativos" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_device_protocol_triggers_kick_check_for_mismatched_source(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core import security
    from app.models.city import City
    from app.models.device import Device
    from app.models.place import Place
    from app.models.protocol import Protocol
    from app.models.user import User
    from app.api.v1.endpoints import devices as devices_endpoint
    from sqlalchemy import select

    admin = User(
        username="admin_protocol_switch",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    city = City(name="Cidade Switch", uf="SW")
    db.add_all([admin, city])
    await db.flush()

    place = Place(name="Local Switch", description="Sala Switch", city_id=city.id)
    db.add(place)
    await db.flush()

    rtmp = (await db.execute(select(Protocol).where(Protocol.protocol == "rtmp"))).scalars().first()
    if rtmp is None:
        db.add(Protocol(protocol="rtmp", port=8554, is_active=True))
    else:
        rtmp.port = 8554
        rtmp.is_active = True
        db.add(rtmp)

    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    if srt is None:
        db.add(Protocol(protocol="srt", port=9000, is_active=True))
    else:
        srt.port = 9000
        srt.is_active = True
        db.add(srt)
    await db.flush()

    device = Device(
        name="Device Switch",
        sn="SN-SWITCH-001",
        place_id=place.id,
        protocol_id=rtmp.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    captured: dict[str, str] = {}

    async def fake_kick_mismatched_source_for_path(*, path_name: str | None, expected_protocol: str | None) -> bool:
        captured["path_name"] = str(path_name or "")
        captured["expected_protocol"] = str(expected_protocol or "")
        return False

    monkeypatch.setattr(
        devices_endpoint,
        "kick_mismatched_source_for_path",
        fake_kick_mismatched_source_for_path,
    )

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.patch(
        f"{settings.API_V1_STR}/devices/{device.id}",
        json={"protocol": "srt"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["protocol"] == "srt"
    assert captured.get("path_name") == f"{settings.APP_NAME}/{settings.APP_VERSION}/{device.key}/stream"
    assert captured.get("expected_protocol") == "srt"


@pytest.mark.asyncio
async def test_qrcode_remains_stable_when_device_protocol_changes(
    client: AsyncClient,
    db: AsyncSession,
):
    from app.core import security
    from app.models.app_setting import AppSetting
    from app.models.city import City
    from app.models.device import Device
    from app.models.place import Place
    from app.models.protocol import Protocol
    from app.models.user import User
    from sqlalchemy import select

    admin = User(
        username="admin_qr_stable",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    city = City(name="Cidade QR", uf="QR")
    db.add_all([admin, city])
    await db.flush()

    place = Place(name="Local QR", description="Sala QR", city_id=city.id)
    db.add(place)
    await db.flush()

    app_setting = AppSetting(
        name="Projeto SurgWaze",
        description="Streaming Medico",
        host="http://127.0.0.1:3000/surgwaze",
        recordings_dir="/recordings",
        output_format="mp4",
    )
    db.add(app_setting)

    rtmp = (await db.execute(select(Protocol).where(Protocol.protocol == "rtmp"))).scalars().first()
    if rtmp is None:
        db.add(Protocol(protocol="rtmp", port=8554, is_active=True))
    else:
        rtmp.port = 8554
        rtmp.is_active = True
        db.add(rtmp)

    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    if srt is None:
        db.add(Protocol(protocol="srt", port=9000, is_active=True))
    else:
        srt.port = 9000
        srt.is_active = True
        db.add(srt)
    await db.flush()

    device = Device(
        name="Device QR Stable",
        sn="SN-QR-STABLE-001",
        place_id=place.id,
        protocol_id=rtmp.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    first_qr = await client.get(
        f"{settings.API_V1_STR}/devices/{device.id}/qrcode",
        headers=headers,
    )
    assert first_qr.status_code == 200
    assert first_qr.headers.get("content-type", "").startswith("image/png")
    assert first_qr.content

    update_response = await client.patch(
        f"{settings.API_V1_STR}/devices/{device.id}",
        json={"protocol": "srt"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["protocol"] == "srt"

    second_qr = await client.get(
        f"{settings.API_V1_STR}/devices/{device.id}/qrcode",
        headers=headers,
    )
    assert second_qr.status_code == 200
    assert second_qr.content == first_qr.content


def test_build_device_scan_url_uses_public_app_host_instead_of_loopback() -> None:
    from app.api.v1.endpoints import devices as devices_endpoint

    scan_url = devices_endpoint._build_device_scan_url(
        "http://127.0.0.1:3000/surgwaze",
        "1F0929AC30C7",
    )
    expected_host = str(settings.APP_HOST or "").strip() or "127.0.0.1"
    if expected_host.lower() in {"localhost", "::1"} or expected_host.startswith("127."):
        expected_host = "127.0.0.1"

    assert f"{expected_host}:3000" in scan_url
    assert scan_url.endswith("/surgwaze/scan?key=1F0929AC30C7")
    if expected_host != "127.0.0.1":
        assert "127.0.0.1:3000" not in scan_url


def test_build_device_scan_url_adds_default_frontend_port_for_ip_without_explicit_port() -> None:
    from app.api.v1.endpoints import devices as devices_endpoint

    scan_url = devices_endpoint._build_device_scan_url(
        "http://192.168.10.19/surgwaze",
        "1F0929AC30C7",
    )

    assert scan_url == "http://192.168.10.19:3000/surgwaze/scan?key=1F0929AC30C7"
