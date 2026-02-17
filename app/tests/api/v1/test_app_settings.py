import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_app_settings_read_and_update(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_app_settings",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_app_settings",
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

    # Read as user
    response = await client.get(f"{settings.API_V1_STR}/app-settings/", headers=user_headers)
    assert response.status_code == 200
    assert "name" in response.json()
    assert "description" in response.json()
    assert "recordings_dir" in response.json()
    assert response.json()["output_format"] in {"mp4", "mkv"}
    assert response.json()["scan_start_in"] == 60

    # Update as admin
    response = await client.patch(
        f"{settings.API_V1_STR}/app-settings/",
        json={
            "name": "Projeto SurgWaze",
            "description": "Streaming Médico",
            "recordings_dir": "recordings/new_path",
            "output_format": "mkv",
            "scan_start_in": 90,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Projeto SurgWaze"
    assert response.json()["description"] == "Streaming Médico"
    assert response.json()["recordings_dir"] == "recordings/new_path"
    assert response.json()["output_format"] == "mkv"
    assert response.json()["scan_start_in"] == 90


@pytest.mark.asyncio
async def test_app_settings_rejects_non_integer_scan_start_in(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_app_settings_int_only",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    admin_token = security.create_access_token(admin.id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.patch(
        f"{settings.API_V1_STR}/app-settings/",
        json={
            "scan_start_in": 59.5,
        },
        headers=admin_headers,
    )
    assert response.status_code == 422
