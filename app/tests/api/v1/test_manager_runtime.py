import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_manager_runtime_metrics_admin_only(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_manager_metrics",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    user = User(
        username="user_manager_metrics",
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

    forbidden = await client.get(f"{settings.API_V1_STR}/manager-runtime/metrics/current", headers=user_headers)
    assert forbidden.status_code == 400

    response = await client.get(f"{settings.API_V1_STR}/manager-runtime/metrics/current", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "cpu_percent" in payload
    assert "memory_percent" in payload
    assert "network" in payload
    assert "download_bps" in payload["network"]
    assert "upload_bps" in payload["network"]
    assert "app_users_online" in payload

    history = await client.get(
        f"{settings.API_V1_STR}/manager-runtime/metrics/history?limit=5",
        headers=admin_headers,
    )
    assert history.status_code == 200
    assert "items" in history.json()
