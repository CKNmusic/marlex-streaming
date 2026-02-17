import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import devices as devices_endpoint
from app.api.v1.endpoints import records as records_endpoint
from app.core import security
from app.core.config import settings
from app.models.city import City
from app.models.device import Device
from app.models.place import Place
from app.models.record import Record
from app.models.app_setting import AppSetting
from app.models.user import User
from app.models.user_device_access import UserDeviceAccess
from app.services.device_runtime_state import device_runtime_state
from app.services import realtime_events
from app.services.recorder import RecorderService, recorder_service


@pytest.mark.asyncio
async def test_start_and_stop_record_with_stream_uses_recorder(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_record",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_record",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.flush()

    city = City(name="Cidade Recorder", uf="RC")
    db.add(city)
    await db.flush()

    place = Place(name="Local Recorder", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Recorder",
        sn="SN-REC-001",
        place_id=place.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    await db.refresh(user)

    calls: dict[str, object] = {}
    recording_state = {"active": False}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        recording_state["active"] = True
        calls["start"] = {
            "device_id": device_id,
            "record_id": record_id,
            "source_url": source_url,
            "profile": profile,
        }
        return recorder_service.get_output_path(record_id)

    async def fake_stop_recording(device_id: int, reason: str = "user", final_status: str | None = None) -> bool:
        recording_state["active"] = False
        calls["stop"] = {"device_id": device_id}
        return True

    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "stop_recording", fake_stop_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _: recording_state["active"])

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)

    user_token = security.create_access_token(user.id)
    user_headers = {"Authorization": f"Bearer {user_token}"}
    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device.key},
        headers=user_headers,
    )
    assert bind_response.status_code == 200

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "Stream Record"},
        headers=user_headers,
    )
    assert response.status_code == 200
    record_id = response.json()["id"]
    assert response.json()["place_id"] == place.id

    assert "start" in calls
    assert calls["start"]["device_id"] == device.id
    assert calls["start"]["record_id"] == record_id
    assert calls["start"]["profile"] == "passthrough"
    source_url = str(calls["start"]["source_url"])
    assert source_url.startswith(("rtmp://", "srt://"))
    assert (f"/{device.key}/stream" in source_url) or (f"streamid=read:surgwaze/v1/{device.key}/stream" in source_url)

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Recording"

    response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record_id}",
        headers=user_headers,
    )
    assert response.status_code == 200
    assert response.json()["end_time"] is not None

    assert calls["stop"] == {"device_id": device.id}

    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status in {"Online", "Offline"}


@pytest.mark.asyncio
async def test_start_record_uses_configured_output_format(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await db.execute(delete(AppSetting))
    await db.flush()

    admin = User(
        username="admin_output_format",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    app_setting = AppSetting(
        name="Projeto SurgWaze",
        description="Streaming Médico",
        host="http://127.0.0.1:3000/surgwaze",
        recordings_dir="recordings/custom_target",
        output_format="mkv",
    )
    db.add(app_setting)
    await db.flush()

    city = City(name="Cidade Formato", uf="FM")
    db.add(city)
    await db.flush()
    place = Place(name="Local Formato", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Formato",
        sn="SN-FMT-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    captured: dict[str, object] = {}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        captured["device_id"] = device_id
        captured["record_id"] = record_id
        captured["output_format"] = output_format
        captured["source_url"] = source_url
        return recorder_service.get_output_path(record_id, output_format, owner_id=owner_id)

    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "formato mkv"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["output_path"].endswith(".mkv")
    assert payload["output_path"].startswith("recordings/custom_target/")
    assert captured["output_format"] == "mkv"
    assert captured["device_id"] == device.id


@pytest.mark.asyncio
async def test_read_records_exposes_runtime_transfer_rate_for_active_record(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_record_rate",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Rate", uf="RT")
    db.add(city)
    await db.flush()
    place = Place(name="Local Rate", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Rate",
        sn="SN-RATE-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    open_record = Record(
        owner_id=admin.id,
        device_id=device.id,
        place_id=place.id,
        title="Recording now",
        end_time=None,
        final_status="recording",
    )
    finished_record = Record(
        owner_id=admin.id,
        device_id=device.id,
        place_id=place.id,
        title="Finished",
        end_time=datetime.utcnow(),
        final_status="stopped_user",
    )
    db.add_all([open_record, finished_record])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(open_record)
    await db.refresh(finished_record)

    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: True)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _device_id: "Recording")
    monkeypatch.setattr(records_endpoint.recorder_service, "get_last_stop_info", lambda _device_id: None)
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "get_recording_transfer_rate_bps",
        lambda device_id: 3_145_728.0 if device_id == device.id else None,
    )

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.get(f"{settings.API_V1_STR}/records/", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()

    active_item = next(item for item in payload if item["id"] == open_record.id)
    finished_item = next(item for item in payload if item["id"] == finished_record.id)
    assert active_item["transfer_rate_bps"] == 3_145_728.0
    assert finished_item["transfer_rate_bps"] is None


@pytest.mark.asyncio
async def test_record_file_endpoint_requires_owner_token(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_stream_file",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    owner = User(
        username="user_stream_owner",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    other_user = User(
        username="user_stream_other",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, owner, other_user])
    await db.flush()

    city = City(name="Cidade Stream", uf="ST")
    db.add(city)
    await db.flush()

    place = Place(name="Local Stream", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Stream",
        sn="SN-STR-001",
        place_id=place.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    await db.refresh(owner)
    await db.refresh(other_user)

    runtime_active = {"value": False}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        runtime_active["value"] = True
        return recorder_service.get_output_path(record_id, owner_id=owner_id)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "is_recording",
        lambda _device_id: runtime_active["value"],
    )

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)

    owner_token = security.create_access_token(owner.id)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device.key},
        headers=owner_headers,
    )
    assert bind_response.status_code == 200

    start_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "Only DB Record"},
        headers=owner_headers,
    )
    assert start_response.status_code == 200
    record_id = start_response.json()["id"]

    output_path = recorder_service.get_output_path(record_id, owner_id=owner.id)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = b"fake-video-content"
    with open(output_path, "wb") as file_handle:
        file_handle.write(payload)

    try:
        missing_token = await client.get(f"{settings.API_V1_STR}/records/{record_id}/stream")
        assert missing_token.status_code == 401

        other_token = security.create_access_token(other_user.id)
        forbidden = await client.get(
            f"{settings.API_V1_STR}/records/{record_id}/stream?token={other_token}"
        )
        assert forbidden.status_code == 403

        ok_response = await client.get(
            f"{settings.API_V1_STR}/records/{record_id}/stream?token={owner_token}"
        )
        assert ok_response.status_code == 200
        assert ok_response.headers["content-type"].startswith("video/mp4")
        assert ok_response.headers["accept-ranges"] == "bytes"
        assert ok_response.content == payload

        partial_response = await client.get(
            f"{settings.API_V1_STR}/records/{record_id}/stream?token={owner_token}",
            headers={"Range": "bytes=5-9"},
        )
        assert partial_response.status_code == 206
        assert partial_response.headers["content-type"].startswith("video/mp4")
        assert partial_response.headers["accept-ranges"] == "bytes"
        assert partial_response.headers["content-range"] == f"bytes 5-9/{len(payload)}"
        assert partial_response.content == payload[5:10]

        download_response = await client.get(
            f"{settings.API_V1_STR}/records/{record_id}/stream?token={owner_token}&download=1"
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-disposition"].startswith("attachment;")
        assert download_response.content == payload
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


@pytest.mark.asyncio
async def test_start_record_does_not_persist_when_recorder_fails(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_record_fail",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Fail Start", uf="FS")
    db.add(city)
    await db.flush()
    place = Place(name="Local Fail Start", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Fail Start",
        sn="SN-FAIL-START-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str | None:
        return None

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "should fail"},
        headers=admin_headers,
    )
    assert response.status_code == 503
    assert "não foi possível iniciar a captura do stream" in response.json()["detail"].lower()
    snapshot = device_runtime_state.get(device.id)
    assert snapshot is not None
    assert snapshot.status == "Online"

    records_for_device = (
        await db.execute(select(Record).where(Record.device_id == device.id))
    ).scalars().all()
    assert records_for_device == []


@pytest.mark.asyncio
async def test_start_record_requires_bind_for_regular_user(
    client: AsyncClient,
    db: AsyncSession,
):
    admin = User(
        username="admin_bind_guard",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_bind_guard",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.flush()

    city = City(name="Cidade Bind", uf="BD")
    db.add(city)
    await db.flush()
    place = Place(name="Local Bind", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Bind",
        sn=f"SN-BIND-{uuid4().hex[:8].upper()}",
        place_id=place.id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)

    user_token = security.create_access_token(user.id)
    user_headers = {"Authorization": f"Bearer {user_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "Should fail"},
        headers=user_headers,
    )
    assert response.status_code == 403
    assert "scan obrigatório" in response.json()["detail"]


@pytest.mark.asyncio
async def test_start_record_blocks_same_device_key_when_already_recording(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_dup_key",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Dup", uf="DP")
    db.add(city)
    await db.flush()
    place = Place(name="Local Dup", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Dup",
        sn="SN-DUP-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    runtime_active = {"value": False}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        runtime_active["value"] = True
        return recorder_service.get_output_path(record_id, owner_id=owner_id)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "is_recording",
        lambda _device_id: runtime_active["value"],
    )

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    first_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "first"},
        headers=admin_headers,
    )
    assert first_response.status_code == 200

    second_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "second"},
        headers=admin_headers,
    )
    assert second_response.status_code == 409


@pytest.mark.asyncio
async def test_stop_record_persists_lifecycle_log_and_size(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_stop_log",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Stop", uf="SP")
    db.add(city)
    await db.flush()
    place = Place(name="Local Stop", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Stop",
        sn="SN-STOP-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    state = {"active": False}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        state["active"] = True
        path = recorder_service.get_output_path(record_id, owner_id=owner_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file_handle:
            file_handle.write(b"video")
        return path

    async def fake_stop_recording(device_id: int, reason: str = "user", final_status: str | None = None) -> bool:
        state["active"] = False
        return True

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "stop_recording", fake_stop_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _: state["active"])
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _: "Recording")
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "get_last_stop_info",
        lambda _device_id: {
            "reason": "timeout",
            "final_status": "error_timeout",
            "started_at": "2026-02-05T10:00:00",
            "ended_at": "2026-02-05T10:01:00",
            "output_path": recorder_service.get_output_path(1),
            "file_size_bytes": 5,
        },
    )

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    start_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "log test"},
        headers=admin_headers,
    )
    assert start_response.status_code == 200
    record_id = start_response.json()["id"]

    stop_response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record_id}?reason=user",
        headers=admin_headers,
    )
    assert stop_response.status_code == 200
    payload = stop_response.json()
    assert payload["stop_reason"] == "timeout"
    assert payload["final_status"] == "error_timeout"
    assert payload["end_time"] is not None
    assert payload["file_size_bytes"] == 5
    assert payload["lifecycle_log"] is not None


@pytest.mark.asyncio
async def test_stop_record_exposes_detected_media_metadata(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_media_meta",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Meta", uf="MT")
    db.add(city)
    await db.flush()
    place = Place(name="Local Meta", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Meta",
        sn="SN-META-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    state = {"active": False}
    output_path_ref = {"value": ""}

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        state["active"] = True
        path = recorder_service.get_output_path(record_id, owner_id=owner_id)
        output_path_ref["value"] = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file_handle:
            file_handle.write(b"video")
        return path

    async def fake_stop_recording(device_id: int, reason: str = "user", final_status: str | None = None) -> bool:
        state["active"] = False
        return True

    async def fake_inspect_media_file(file_path: str | None) -> dict[str, str]:
        return {
            "video_resolution": "3840x2160",
            "video_codec": "hevc",
            "audio_codec": "aac",
        }

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint, "inspect_media_file", fake_inspect_media_file)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "stop_recording", fake_stop_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _: state["active"])
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _: "Recording")
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "get_last_stop_info",
        lambda _device_id: {
            "reason": "user",
            "final_status": "stopped_user",
            "started_at": "2026-02-11T12:00:00",
            "ended_at": "2026-02-11T12:01:00",
            "output_path": output_path_ref["value"],
            "file_size_bytes": 5,
        },
    )

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    start_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "meta test"},
        headers=admin_headers,
    )
    assert start_response.status_code == 200
    record_id = start_response.json()["id"]

    stop_response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record_id}?reason=user",
        headers=admin_headers,
    )
    assert stop_response.status_code == 200
    payload = stop_response.json()
    assert payload["video_resolution"] == "3840x2160"
    assert payload["video_codec"] == "hevc"
    assert payload["audio_codec"] == "aac"


@pytest.mark.asyncio
async def test_stop_record_by_admin_on_own_record_is_normal_user_stop(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_stop_own",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Stop Own", uf="SO")
    db.add(city)
    await db.flush()
    place = Place(name="Local Stop Own", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Stop Own",
        sn="SN-STOP-OWN-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=admin.id,
        device_id=device.id,
        place_id=place.id,
        title="Own recording",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(record)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_last_stop_info", lambda _device_id: None)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record.id}?reason=master",
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "user"
    assert payload["final_status"] == "stopped_user"
    assert payload["file_size_bytes"] == 0
    assert payload["output_path"] == recorder_service.get_output_path(record.id)


@pytest.mark.asyncio
async def test_stop_record_by_admin_on_other_user_record_uses_master_reason(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_stop_other",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    owner = User(
        username="owner_stop_other",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, owner])
    await db.flush()

    city = City(name="Cidade Stop Other", uf="ST")
    db.add(city)
    await db.flush()
    place = Place(name="Local Stop Other", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Stop Other",
        sn="SN-STOP-OTHER-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="Owner recording",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(record)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_last_stop_info", lambda _device_id: None)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record.id}?reason=master",
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "master"
    assert payload["final_status"] == "stopped_master"


@pytest.mark.asyncio
async def test_start_record_blocks_offline_device(
    client: AsyncClient,
    db: AsyncSession,
):
    admin = User(
        username="admin_offline_block",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Offline", uf="OF")
    db.add(city)
    await db.flush()
    place = Place(name="Local Offline", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Offline",
        sn="SN-OFF-001",
        place_id=place.id,
        is_active=True,
        status="Offline",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "offline should fail"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "offline" in response.json()["detail"].lower()

    records_for_device = (
        await db.execute(select(Record).where(Record.device_id == device.id))
    ).scalars().all()
    assert records_for_device == []


@pytest.mark.asyncio
async def test_start_record_rechecks_stream_even_when_device_status_is_online(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_online_stale",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Stale", uf="SL")
    db.add(city)
    await db.flush()
    place = Place(name="Local Stale", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Stale",
        sn="SN-STALE-001",
        place_id=place.id,
        is_active=True,
        status="Online",
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    called_start = {"value": False}

    async def should_not_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        called_start["value"] = True
        return recorder_service.get_output_path(record_id, output_format)

    async def always_offline(_stream_url: str | None) -> bool:
        return False

    monkeypatch.setattr(records_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", should_not_start_recording)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "stale should fail"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    detail = str(response.json()["detail"]).lower()
    assert ("conexão" in detail) or ("reconexão" in detail) or ("offline" in detail)
    assert called_start["value"] is False


@pytest.mark.asyncio
async def test_start_record_does_not_use_presence_grace_window_without_real_stream(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_start_grace",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Grace", uf="GR")
    db.add(city)
    await db.flush()
    place = Place(name="Local Grace", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Grace",
        sn="SN-GRACE-001",
        place_id=place.id,
        is_active=True,
        status="Online",
        last_seen=datetime.utcnow() - timedelta(seconds=20),
    )
    db.add(device)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(device)

    called_start = {"value": False}

    async def always_offline(_stream_url: str | None) -> bool:
        return False

    async def fake_start_recording(
        device_id: int,
        record_id: int,
        source_url: str,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        called_start["value"] = True
        return recorder_service.get_output_path(record_id, output_format)

    monkeypatch.setattr(records_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device.id, "title": "grace should fail without stream"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "conexão" in response.json()["detail"].lower() or "offline" in response.json()["detail"].lower()
    assert called_start["value"] is False


@pytest.mark.asyncio
async def test_bind_device_blocks_when_device_is_in_use_by_other_user(
    client: AsyncClient,
    db: AsyncSession,
):
    owner = User(
        username="owner_bind_conflict",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    another_user = User(
        username="scanner_bind_conflict",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([owner, another_user])
    await db.flush()

    city = City(name="Cidade Bind In Use", uf="IU")
    db.add(city)
    await db.flush()
    place = Place(name="Local Bind In Use", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(name="Camera Bind In Use", sn="SN-BIND-IN-USE", place_id=place.id, is_active=True)
    db.add(device)
    await db.flush()

    open_record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="Em andamento",
        end_time=None,
    )
    db.add(open_record)
    await db.commit()
    await db.refresh(another_user)
    await db.refresh(device)

    another_token = security.create_access_token(another_user.id)
    headers = {"Authorization": f"Bearer {another_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device.key},
        headers=headers,
    )
    assert response.status_code == 409
    assert "uso" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bind_status_returns_runtime_status_after_bind(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = User(
        username="bind_status_user",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    city = City(name="Cidade Bind Status", uf="BS")
    db.add(city)
    await db.flush()
    place = Place(name="Local Bind Status", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(name="Camera Bind Status", sn="SN-BIND-STATUS", place_id=place.id, is_active=True)
    db.add(device)
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)

    async def always_online(_stream_url: str | None) -> bool:
        return True

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)

    user_token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {user_token}"}

    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device.key},
        headers=headers,
    )
    assert bind_response.status_code == 200

    status_response = await client.get(
        f"{settings.API_V1_STR}/devices/{device.id}/bind-status",
        headers=headers,
    )
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["device_id"] == device.id
    assert payload["status"] == "Connecting"
    assert payload["online"] is False


@pytest.mark.asyncio
async def test_bind_status_ignores_grace_and_requires_real_online_signal(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = User(
        username="bind_status_strict_user",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    city = City(name="Cidade Bind Strict", uf="BX")
    db.add(city)
    await db.flush()
    place = Place(name="Local Bind Strict", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Bind Strict",
        sn="SN-BIND-STRICT",
        place_id=place.id,
        is_active=True,
        status="Online",
        last_seen=datetime.utcnow() - timedelta(seconds=5),
    )
    db.add(device)
    await db.commit()
    await db.refresh(user)
    await db.refresh(device)

    async def always_offline(_stream_url: str | None) -> bool:
        return False

    monkeypatch.setattr(devices_endpoint, "probe_stream", always_offline)
    monkeypatch.setattr(devices_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(devices_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")

    user_token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {user_token}"}

    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device.key},
        headers=headers,
    )
    assert bind_response.status_code == 200

    status_response = await client.get(
        f"{settings.API_V1_STR}/devices/{device.id}/bind-status",
        headers=headers,
    )
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["device_id"] == device.id
    assert payload["status"] == "Offline"
    assert payload["online"] is False


@pytest.mark.asyncio
async def test_emit_record_status_targets_only_record_owner(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = User(
        username="owner_rt_scope",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    watcher = User(
        username="watcher_rt_scope",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([owner, watcher])
    await db.flush()

    city = City(name="Cidade Scope", uf="SC")
    db.add(city)
    await db.flush()
    place = Place(name="Local Scope", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(name="Camera Scope", sn="SN-SCOPE-001", place_id=place.id, is_active=True)
    db.add(device)
    await db.flush()

    # Both users can see the same device, but record updates must stay private to owner.
    db.add_all(
        [
            UserDeviceAccess(user_id=owner.id, device_id=device.id),
            UserDeviceAccess(user_id=watcher.id, device_id=device.id),
        ]
    )
    await db.commit()

    captured: dict[str, object] = {}

    async def fake_publish(payload: dict[str, object]) -> None:
        captured.update(payload)

    monkeypatch.setattr(realtime_events.realtime_event_bus, "publish", fake_publish)

    await realtime_events.emit_record_status(
        db,
        record_id=99,
        device_id=device.id,
        owner_id=owner.id,
        status="Recording",
        final_status="recording",
        stop_reason=None,
        end_time=datetime.utcnow(),
        detail="scope-test",
    )

    assert captured["record_id"] == 99
    assert captured["owner_id"] == owner.id
    assert captured["type"] == "record_status"
    assert captured["_target_user_ids"] == [owner.id]


def test_recorder_service_is_recording_ignores_finished_process():
    service = RecorderService()

    class DeadProcess:
        returncode = 1

    service._active_recordings[123] = DeadProcess()  # type: ignore[assignment]

    assert service.is_recording(123) is False
    assert service.active_count() == 0


def test_recorder_service_output_path_uses_date_plus_device_key(tmp_path: Path):
    service = RecorderService()
    service.set_recordings_dir(str(tmp_path))

    reference_day = datetime(2026, 2, 10, 10, 0, 0)
    output_path = service.get_output_path(
        77,
        "mp4",
        stream_key="99720B1969CA",
        started_at=reference_day,
    )

    expected_suffix = os.path.join("99720B1969CA", "20260210", "2026_02_10_unknown_77.mp4")
    assert output_path.endswith(expected_suffix)


def test_record_public_id_prefers_device_key_from_output_path():
    record = Record(
        id=12,
        owner_id=1,
        device_id=2,
        place_id=3,
        seq=4,
        output_path="/recordings/99720B1969CA/20260210/2026021099720B1969CA.mp4",
    )
    assert record.public_id == "99720B1969CA"


@pytest.mark.asyncio
async def test_read_records_reconciles_stale_open_record_from_runtime_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = User(
        username="owner_reconcile_runtime",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(owner)
    await db.flush()

    city = City(name="Cidade Reconcile", uf="RC")
    db.add(city)
    await db.flush()

    place = Place(name="Local Reconcile", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Reconcile",
        sn="SN-RECON-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="aberta",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    output_path = recorder_service.get_output_path(record.id)
    record.output_path = output_path
    db.add(record)
    await db.commit()
    await db.refresh(owner)
    await db.refresh(record)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = b"video-stale-runtime"
    with open(output_path, "wb") as file_handle:
        file_handle.write(payload)

    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "get_last_stop_info",
        lambda _device_id: {
            "record_id": record.id,
            "reason": "connection",
            "final_status": "error_connection",
            "ended_at": "2026-02-07T10:10:10",
            "output_path": output_path,
            "file_size_bytes": len(payload),
        },
    )

    owner_token = security.create_access_token(owner.id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = await client.get(f"{settings.API_V1_STR}/records/", headers=headers)
    assert response.status_code == 200
    payload_response = response.json()
    assert len(payload_response) == 1
    assert payload_response[0]["id"] == record.id
    assert payload_response[0]["end_time"] is not None
    assert payload_response[0]["final_status"] == "error_connection"
    assert payload_response[0]["stop_reason"] == "connection"

    await db.refresh(record)
    assert record.end_time is not None
    assert record.final_status == "error_connection"
    assert record.stop_reason == "connection"
    assert record.file_size_bytes == len(payload)

    if os.path.exists(output_path):
        os.remove(output_path)


@pytest.mark.asyncio
async def test_read_records_reconciles_stale_open_record_drops_empty_file(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = User(
        username="owner_reconcile_empty",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(owner)
    await db.flush()

    city = City(name="Cidade Reconcile Empty", uf="RE")
    db.add(city)
    await db.flush()

    place = Place(name="Local Reconcile Empty", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Reconcile Empty",
        sn="SN-RECON-EMPTY-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="aberta-vazia",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    output_path = recorder_service.get_output_path(record.id)
    record.output_path = output_path
    db.add(record)
    await db.commit()
    await db.refresh(owner)
    await db.refresh(record)

    if os.path.exists(output_path):
        os.remove(output_path)

    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(
        records_endpoint.recorder_service,
        "get_last_stop_info",
        lambda _device_id: {
            "record_id": record.id,
            "reason": "connection",
            "final_status": "error_connection",
            "ended_at": "2026-02-07T10:10:10",
            "output_path": output_path,
            "file_size_bytes": 0,
        },
    )

    owner_token = security.create_access_token(owner.id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = await client.get(f"{settings.API_V1_STR}/records/", headers=headers)
    assert response.status_code == 200
    payload_response = response.json()
    assert all(item["id"] != record.id for item in payload_response)

    result = await db.execute(select(Record).where(Record.id == record.id))
    assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_read_records_reconciles_stale_open_record_without_stop_info(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = User(
        username="owner_reconcile_noinfo",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(owner)
    await db.flush()

    city = City(name="Cidade Reconcile NoInfo", uf="RI")
    db.add(city)
    await db.flush()

    place = Place(name="Local Reconcile NoInfo", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Reconcile NoInfo",
        sn="SN-RECON-NOINFO-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="aberta-sem-stop",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    output_path = recorder_service.get_output_path(record.id)
    record.output_path = output_path
    db.add(record)
    await db.commit()
    await db.refresh(owner)
    await db.refresh(record)

    if os.path.exists(output_path):
        os.remove(output_path)

    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(records_endpoint.recorder_service, "get_last_stop_info", lambda _device_id: None)

    owner_token = security.create_access_token(owner.id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = await client.get(f"{settings.API_V1_STR}/records/", headers=headers)
    assert response.status_code == 200
    payload_response = response.json()
    assert all(item["id"] != record.id for item in payload_response)

    result = await db.execute(select(Record).where(Record.id == record.id))
    assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_read_records_reconciles_stale_open_record_without_stop_info_but_with_file(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    owner = User(
        username="owner_reconcile_noinfo_file",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(owner)
    await db.flush()

    city = City(name="Cidade Reconcile NoInfo File", uf="RF")
    db.add(city)
    await db.flush()

    place = Place(name="Local Reconcile NoInfo File", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Reconcile NoInfo File",
        sn="SN-RECON-NOINFO-FILE-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=owner.id,
        device_id=device.id,
        place_id=place.id,
        title="aberta-sem-stop-com-arquivo",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    output_path = recorder_service.get_output_path(record.id)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(b"fake-video-bytes")

    record.output_path = output_path
    db.add(record)
    await db.commit()
    await db.refresh(owner)
    await db.refresh(record)

    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint.recorder_service, "get_state", lambda _device_id: "Offline")
    monkeypatch.setattr(records_endpoint.recorder_service, "get_last_stop_info", lambda _device_id: None)

    owner_token = security.create_access_token(owner.id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = await client.get(f"{settings.API_V1_STR}/records/", headers=headers)
    assert response.status_code == 200
    payload_response = response.json()
    target = next((item for item in payload_response if item["id"] == record.id), None)
    assert target is not None
    assert target["end_time"] is not None
    assert target["final_status"] == "error_connection"
    assert target["stop_reason"] == "disconnect"

    db.expire(record)
    await db.refresh(record)
    refreshed = record
    assert refreshed is not None
    assert refreshed.end_time is not None
    assert refreshed.final_status == "error_connection"
    assert refreshed.stop_reason == "disconnect"


@pytest.mark.asyncio
async def test_stop_record_enqueues_ingest_upload_job(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = User(
        username="admin_ingest_enqueue",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    city = City(name="Cidade Enqueue", uf="EN")
    db.add(city)
    await db.flush()

    place = Place(name="Local Enqueue", description="Sala", city_id=city.id)
    db.add(place)
    await db.flush()

    device = Device(
        name="Camera Enqueue",
        sn="SN-ENQUEUE-001",
        place_id=place.id,
        is_active=True,
        status="Recording",
    )
    db.add(device)
    await db.flush()

    record = Record(
        owner_id=admin.id,
        device_id=device.id,
        place_id=place.id,
        title="enqueue-stop",
        end_time=None,
        final_status="recording",
    )
    db.add(record)
    await db.flush()

    output_path = recorder_service.get_output_path(record.id)
    record.output_path = output_path
    db.add(record)
    await db.commit()
    await db.refresh(admin)
    await db.refresh(record)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as file_handle:
        file_handle.write(b"payload-for-upload")

    captured: dict[str, object] = {}

    async def fake_enqueue_upload(
        *,
        record_id: int,
        file_path: str,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        captured["record_id"] = record_id
        captured["file_path"] = file_path
        captured["metadata"] = metadata or {}
        return True

    async def always_offline(_stream_url: str | None) -> bool:
        return False

    monkeypatch.setattr(records_endpoint.ingest_upload_gateway, "enqueue_upload", fake_enqueue_upload)
    monkeypatch.setattr(records_endpoint.recorder_service, "is_recording", lambda _device_id: False)
    monkeypatch.setattr(records_endpoint, "probe_stream", always_offline)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.post(
        f"{settings.API_V1_STR}/records/stop/{record.id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert captured["record_id"] == record.id
    assert captured["file_path"] == output_path
    assert captured["metadata"]["source"] == "stop"

    if os.path.exists(output_path):
        os.remove(output_path)
