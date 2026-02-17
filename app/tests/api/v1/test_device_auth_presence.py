import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import parse_qs, urlparse

from app.core import security
from app.models.city import City
from app.models.device import Device
from app.models.place import Place
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.user import User
from app.models.user_device_access import UserDeviceAccess
from app.services.device_runtime_state import device_runtime_state
from app.services.realtime_hub import realtime_hub
from app.services.recorder import recorder_service


async def _seed_device_context(db: AsyncSession) -> tuple[User, Device]:
    suffix = uuid4().hex[:8]
    user = User(
        username=f"presence_user_{suffix}",
        password=security.get_password_hash("presence"),
        is_superuser=False,
        is_active=True,
    )
    city = City(name="Cidade Presenca", uf="SP", is_active=True)
    db.add_all([user, city])
    await db.flush()

    place = Place(name="Sala Presenca", city_id=city.id, is_active=True)
    db.add(place)
    await db.flush()

    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    if srt is None:
        srt = Protocol(protocol="srt", port=9000, is_active=True)
        db.add(srt)

    rtmp = (await db.execute(select(Protocol).where(Protocol.protocol == "rtmp"))).scalars().first()
    if rtmp is None:
        rtmp = Protocol(protocol="rtmp", port=8554, is_active=True)
        db.add(rtmp)
    await db.flush()

    device = Device(
        name="Device Presence",
        sn=f"SN-PRESENCE-{suffix}",
        place_id=place.id,
        is_active=True,
        protocol_id=rtmp.id,
    )
    db.add(device)
    await db.flush()

    access = UserDeviceAccess(user_id=user.id, device_id=device.id)
    db.add(access)
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)
    return user, device


@pytest.mark.asyncio
async def test_device_heartbeat_ignored_when_owner_is_offline(client: AsyncClient, db: AsyncSession):
    _, device = await _seed_device_context(db)
    token = security.create_access_token(str(device.id))
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/surgwaze/v1/device-auth/heartbeat",
        json={
            "device_id": str(device.id),
            "status": "ready",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored_user_offline"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Connecting"


@pytest.mark.asyncio
async def test_device_heartbeat_promotes_online_when_owner_is_online(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    token = security.create_access_token(str(device.id))
    headers = {"Authorization": f"Bearer {token}"}

    async def always_online(_user_ids: set[int]) -> bool:
        return True

    monkeypatch.setattr(realtime_hub, "any_user_online", always_online)

    response = await client.post(
        "/surgwaze/v1/device-auth/heartbeat",
        json={
            "device_id": str(device.id),
            "status": "ready",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Connecting"


@pytest.mark.asyncio
async def test_device_heartbeat_promotes_online_when_superuser_is_online(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    token = security.create_access_token(str(device.id))
    headers = {"Authorization": f"Bearer {token}"}

    async def owner_offline(_user_ids: set[int]) -> bool:
        return False

    async def superuser_online() -> bool:
        return True

    monkeypatch.setattr(realtime_hub, "any_user_online", owner_offline)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", superuser_online)

    response = await client.post(
        "/surgwaze/v1/device-auth/heartbeat",
        json={
            "device_id": str(device.id),
            "status": "ready",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Connecting"


@pytest.mark.asyncio
async def test_ingest_auth_allows_publish_without_online_user_or_recording(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)

    async def no_user_online(_user_ids: set[int]) -> bool:
        return False

    async def no_superuser_online() -> bool:
        return False

    monkeypatch.setattr(realtime_hub, "any_user_online", no_user_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "path": f"surgwaze/v1/{device.key}/stream",
            "protocol": "rtmp",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["detail"] == "allow_publish_authenticated"


@pytest.mark.asyncio
async def test_ingest_auth_allows_publish_when_owner_is_online(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)

    async def owner_online(_user_ids: set[int]) -> bool:
        return True

    async def no_superuser_online() -> bool:
        return False

    monkeypatch.setattr(realtime_hub, "any_user_online", owner_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "path": f"/surgwaze/v1/{device.key}/stream",
            "protocol": "rtmp",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Connecting"


@pytest.mark.asyncio
async def test_ingest_auth_allows_publish_when_open_record_exists(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user, device = await _seed_device_context(db)
    open_record = Record(
        owner_id=user.id,
        device_id=device.id,
        place_id=device.place_id,
        title="Open record",
    )
    db.add(open_record)
    await db.commit()

    async def no_user_online(_user_ids: set[int]) -> bool:
        return False

    async def no_superuser_online() -> bool:
        return False

    monkeypatch.setattr(realtime_hub, "any_user_online", no_user_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "path": f"surgwaze/v1/{device.key}/stream",
            "protocol": "rtmp",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Recording"


@pytest.mark.asyncio
async def test_ingest_auth_allows_srt_publish_using_streamid_query(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    assert srt is not None
    device.protocol_id = srt.id
    db.add(device)
    await db.commit()

    async def owner_online(_user_ids: set[int]) -> bool:
        return True

    async def no_superuser_online() -> bool:
        return False

    monkeypatch.setattr(realtime_hub, "any_user_online", owner_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "protocol": "srt",
            "query": f"streamid=publish:surgwaze/v1/{device.key}/stream",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Connecting"


@pytest.mark.asyncio
async def test_device_auth_returns_srt_ingest_url_with_streamid(
    client: AsyncClient,
    db: AsyncSession,
):
    _, device = await _seed_device_context(db)
    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    assert srt is not None
    device.protocol_id = srt.id
    db.add(device)
    await db.commit()

    response = await client.post(
        "/surgwaze/v1/device-auth/auth",
        json={"qr_token": device.key},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol"] == "srt"
    assert payload["ingest_url"].startswith("srt://")

    parsed = urlparse(payload["ingest_url"])
    query = parse_qs(parsed.query)
    assert query.get("streamid") == [f"publish:surgwaze/v1/{device.key}/stream"]


@pytest.mark.asyncio
async def test_ingest_auth_rejects_protocol_mismatch_for_device(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    srt = (await db.execute(select(Protocol).where(Protocol.protocol == "srt"))).scalars().first()
    assert srt is not None
    device.protocol_id = srt.id
    db.add(device)
    await db.commit()

    async def owner_online(_user_ids: set[int]) -> bool:
        return True

    async def no_superuser_online() -> bool:
        return False

    monkeypatch.setattr(realtime_hub, "any_user_online", owner_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "protocol": "rtmp",
            "path": f"surgwaze/v1/{device.key}/stream",
        },
    )
    assert response.status_code == 403
    assert "Protocol mismatch" in response.json()["detail"]


@pytest.mark.asyncio
async def test_device_heartbeat_ignored_emits_realtime_online_update(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    device.status = "Online"
    db.add(device)
    await db.commit()

    token = security.create_access_token(str(device.id))
    headers = {"Authorization": f"Bearer {token}"}
    captured: dict[str, object] = {}

    async def no_user_online(_user_ids: set[int]) -> bool:
        return False

    async def fake_emit_device_status(
        _db: AsyncSession,
        *,
        device_id: int,
        status: str,
        online: bool,
        stream_url: str | None,
        checked_at=None,
        detail: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        captured["device_id"] = device_id
        captured["status"] = status
        captured["online"] = online
        captured["detail"] = detail
        captured["stream_url"] = stream_url

    from app.api.v1.endpoints import device_auth as device_auth_endpoint

    monkeypatch.setattr(realtime_hub, "any_user_online", no_user_online)
    monkeypatch.setattr(device_auth_endpoint, "emit_device_status", fake_emit_device_status)

    response = await client.post(
        "/surgwaze/v1/device-auth/heartbeat",
        json={
            "device_id": str(device.id),
            "status": "ready",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored_user_offline"
    assert captured.get("device_id") == device.id
    assert captured.get("status") == "Connecting"
    assert captured.get("online") is False
    assert captured.get("detail") == "heartbeat_ignored_user_offline"


@pytest.mark.asyncio
async def test_ingest_auth_publish_authenticated_emits_realtime_update(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, device = await _seed_device_context(db)
    device.status = "Online"
    db.add(device)
    await db.commit()

    captured: dict[str, object] = {}

    async def no_user_online(_user_ids: set[int]) -> bool:
        return False

    async def no_superuser_online() -> bool:
        return False

    async def fake_emit_device_status(
        _db: AsyncSession,
        *,
        device_id: int,
        status: str,
        online: bool,
        stream_url: str | None,
        checked_at=None,
        detail: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        captured["device_id"] = device_id
        captured["status"] = status
        captured["online"] = online
        captured["detail"] = detail
        captured["stream_url"] = stream_url

    from app.api.v1.endpoints import device_auth as device_auth_endpoint

    monkeypatch.setattr(realtime_hub, "any_user_online", no_user_online)
    monkeypatch.setattr(realtime_hub, "any_superuser_online", no_superuser_online)
    monkeypatch.setattr(recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(device_auth_endpoint, "emit_device_status", fake_emit_device_status)

    response = await client.post(
        "/surgwaze/v1/device-auth/ingest-auth",
        json={
            "action": "publish",
            "path": f"surgwaze/v1/{device.key}/stream",
            "protocol": "rtmp",
        },
    )
    assert response.status_code == 200
    assert captured.get("device_id") == device.id
    assert captured.get("status") == "Connecting"
    assert captured.get("online") is False
    assert captured.get("detail") == "ingest_publish_allowed:allow_publish_authenticated"
