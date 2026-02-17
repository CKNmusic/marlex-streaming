import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import devices as devices_endpoint
from app.api.v1.endpoints import records as records_endpoint
from app.core import security
from app.core.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_deactivate_blocked_when_entity_in_use(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def always_online(_stream_url: str | None) -> bool:
        return True

    async def fake_start_recording(
        *,
        device_id: int,
        record_id: int,
        source_url: str,
        owner_id: int,
        profile: str = "passthrough",
        output_format: str = "mp4",
    ) -> str:
        extension = "mkv" if (output_format or "").strip().lower() == "mkv" else "mp4"
        return f"recordings/record_{record_id}.{extension}"

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)

    admin = User(
        username="admin_deactivate_guard",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_deactivate_guard",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(user)

    admin_headers = {"Authorization": f"Bearer {security.create_access_token(admin.id)}"}
    user_headers = {"Authorization": f"Bearer {security.create_access_token(user.id)}"}

    city_response = await client.post(
        f"{settings.API_V1_STR}/cities/",
        json={"name": "Cidade Uso Ativo", "uf": "UA"},
        headers=admin_headers,
    )
    assert city_response.status_code == 200
    city_id = city_response.json()["id"]

    place_response = await client.post(
        f"{settings.API_V1_STR}/places/",
        json={"name": "Local Uso Ativo", "description": "Sala", "city_id": city_id},
        headers=admin_headers,
    )
    assert place_response.status_code == 200
    place_id = place_response.json()["id"]

    mark_response = await client.post(
        f"{settings.API_V1_STR}/marks/",
        json={"name": "Marca Uso Ativo"},
        headers=admin_headers,
    )
    assert mark_response.status_code == 200
    mark_id = mark_response.json()["id"]

    protocols_response = await client.get(
        f"{settings.API_V1_STR}/protocols/",
        headers=admin_headers,
    )
    assert protocols_response.status_code == 200
    protocols = protocols_response.json()
    if protocols:
        selected_protocol = protocols[0]
    else:
        created_protocol_response = await client.post(
            f"{settings.API_V1_STR}/protocols/",
            json={"protocol": "srt", "port": 9000, "is_active": True},
            headers=admin_headers,
        )
        assert created_protocol_response.status_code == 200
        selected_protocol = created_protocol_response.json()

    if selected_protocol.get("is_active") is False:
        activate_protocol_response = await client.patch(
            f"{settings.API_V1_STR}/protocols/{selected_protocol['id']}",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert activate_protocol_response.status_code == 200

    device_response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={
            "name": "Device Uso Ativo",
            "sn": "SN-DEACT-001",
            "mark_id": mark_id,
            "place_id": place_id,
            "protocol": selected_protocol["protocol"],
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert device_response.status_code == 200
    device = device_response.json()

    procedure_response = await client.post(
        f"{settings.API_V1_STR}/procedures/",
        json={"name": "Proc Uso Ativo", "description": "Proc"},
        headers=admin_headers,
    )
    assert procedure_response.status_code == 200
    procedure_id = procedure_response.json()["id"]

    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device["key"]},
        headers=user_headers,
    )
    assert bind_response.status_code == 200

    start_response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={
            "device_id": device["id"],
            "procedure_id": procedure_id,
            "title": "Registro em uso",
        },
        headers=user_headers,
    )
    assert start_response.status_code == 200

    deactivate_user = await client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_user.status_code == 400

    deactivate_device = await client.patch(
        f"{settings.API_V1_STR}/devices/{device['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_device.status_code == 400

    deactivate_procedure = await client.patch(
        f"{settings.API_V1_STR}/procedures/{procedure_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_procedure.status_code == 400

    deactivate_place = await client.patch(
        f"{settings.API_V1_STR}/places/{place_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_place.status_code == 400

    deactivate_city = await client.patch(
        f"{settings.API_V1_STR}/cities/{city_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_city.status_code == 400

    deactivate_protocol = await client.patch(
        f"{settings.API_V1_STR}/protocols/{selected_protocol['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_protocol.status_code == 400

    delete_protocol = await client.delete(
        f"{settings.API_V1_STR}/protocols/{selected_protocol['id']}",
        headers=admin_headers,
    )
    assert delete_protocol.status_code == 400

    deactivate_mark = await client.patch(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_mark.status_code == 400

    delete_mark = await client.delete(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        headers=admin_headers,
    )
    assert delete_mark.status_code == 400
