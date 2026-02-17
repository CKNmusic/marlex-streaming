import os
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import devices as devices_endpoint
from app.api.v1.endpoints import records as records_endpoint
from app.core import security
from app.core.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_procedure_and_record_crud(
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
        path = f"recordings/record_{record_id}.{extension}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file_handle:
            file_handle.write(b"video")
        return path

    monkeypatch.setattr(records_endpoint, "probe_stream", always_online)
    monkeypatch.setattr(records_endpoint.recorder_service, "start_recording", fake_start_recording)

    admin = User(
        username="admin_proc",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_proc",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(user)

    admin_token = security.create_access_token(admin.id)
    user_token = security.create_access_token(user.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Create city and place
    response = await client.post(
        f"{settings.API_V1_STR}/cities/",
        json={"name": "Cidade CRUD", "uf": "CR"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    city_id = response.json()["id"]

    response = await client.post(
        f"{settings.API_V1_STR}/places/",
        json={"name": "Local CRUD", "description": "Sala CRUD", "city_id": city_id},
        headers=admin_headers,
    )
    assert response.status_code == 200
    place_id = response.json()["id"]

    # Create device
    response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={"name": "Device CRUD", "sn": "SN-CRUD-0001", "place_id": place_id, "is_active": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    device_id = response.json()["id"]
    device_key = response.json()["key"]

    # Create procedure
    response = await client.post(
        f"{settings.API_V1_STR}/procedures/",
        json={"name": "Procedimento CRUD", "description": "Proc"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    procedure_id = response.json()["id"]

    # List procedures
    response = await client.get(f"{settings.API_V1_STR}/procedures/", headers=admin_headers)
    assert response.status_code == 200
    assert any(item["id"] == procedure_id for item in response.json())

    # Update procedure
    response = await client.patch(
        f"{settings.API_V1_STR}/procedures/{procedure_id}",
        json={"description": "Proc Atualizado"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Proc Atualizado"

    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device_key},
        headers=user_headers,
    )
    assert bind_response.status_code == 200

    # Start record stream
    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device_id, "procedure_id": procedure_id, "title": "Registro CRUD"},
        headers=user_headers,
    )
    assert response.status_code == 200
    record_id = response.json()["id"]

    # List record streams
    response = await client.get(f"{settings.API_V1_STR}/records/", headers=user_headers)
    assert response.status_code == 200
    assert any(item["id"] == record_id for item in response.json())

    # Update record stream
    response = await client.patch(
        f"{settings.API_V1_STR}/records/{record_id}",
        json={"title": "Registro Atualizado"},
        headers=user_headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Registro Atualizado"

    # Delete record stream (admin)
    response = await client.delete(
        f"{settings.API_V1_STR}/records/{record_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200

    # Delete procedure (no references now)
    response = await client.delete(
        f"{settings.API_V1_STR}/procedures/{procedure_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_blocked_when_fk_exists(
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
        username="admin_fk",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_fk",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, user])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(user)

    admin_token = security.create_access_token(admin.id)
    user_token = security.create_access_token(user.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Create city, place, device, procedure
    response = await client.post(
        f"{settings.API_V1_STR}/cities/",
        json={"name": "Cidade FK", "uf": "FK"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    city_id = response.json()["id"]

    response = await client.post(
        f"{settings.API_V1_STR}/places/",
        json={"name": "Local FK", "description": "Sala FK", "city_id": city_id},
        headers=admin_headers,
    )
    assert response.status_code == 200
    place_id = response.json()["id"]

    response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={"name": "Device FK", "sn": "SN-FK-0001", "place_id": place_id, "is_active": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    device_id = response.json()["id"]
    device_key = response.json()["key"]

    response = await client.post(
        f"{settings.API_V1_STR}/procedures/",
        json={"name": "Procedimento FK", "description": "Proc FK"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    procedure_id = response.json()["id"]

    bind_response = await client.post(
        f"{settings.API_V1_STR}/devices/bind",
        json={"key": device_key},
        headers=user_headers,
    )
    assert bind_response.status_code == 200

    # Create record stream referencing all
    response = await client.post(
        f"{settings.API_V1_STR}/records/start",
        json={"device_id": device_id, "procedure_id": procedure_id, "title": "Registro FK"},
        headers=user_headers,
    )
    assert response.status_code == 200

    # Delete device should fail (in use)
    response = await client.delete(
        f"{settings.API_V1_STR}/devices/{device_id}",
        headers=admin_headers,
    )
    assert response.status_code == 400

    # Delete user should fail (in use)
    response = await client.delete(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=admin_headers,
    )
    assert response.status_code == 400

    # Delete place should fail (in use)
    response = await client.delete(
        f"{settings.API_V1_STR}/places/{place_id}",
        headers=admin_headers,
    )
    assert response.status_code == 400

    # Delete city should fail (place exists)
    response = await client.delete(
        f"{settings.API_V1_STR}/cities/{city_id}",
        headers=admin_headers,
    )
    assert response.status_code == 400

    # Delete procedure should fail (record exists)
    response = await client.delete(
        f"{settings.API_V1_STR}/procedures/{procedure_id}",
        headers=admin_headers,
    )
    assert response.status_code == 400
