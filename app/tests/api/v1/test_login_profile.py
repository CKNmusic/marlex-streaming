import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core import security
from app.models.user import User


@pytest.mark.asyncio
async def test_login_and_profile_password_change(client: AsyncClient, db: AsyncSession):
    user = User(
        username="user_profile",
        full_name="Perfil Teste",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()

    # Login with original password
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "user_profile", "password": "123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Update profile (name + password)
    response = await client.patch(
        f"{settings.API_V1_STR}/users/me",
        json={"full_name": "Perfil Atualizado", "password": "1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Perfil Atualizado"

    # Old password should fail
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "user_profile", "password": "123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400

    # New password should work
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "user_profile", "password": "1234"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_requires_password_reset_when_password_is_username(client: AsyncClient, db: AsyncSession):
    user = User(
        username="reset_user",
        full_name="Reset User",
        password=security.get_password_hash("reset_user"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "reset_user", "password": "reset_user"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("reset_required") is True
    assert data.get("reset_token")

    reset_token = data["reset_token"]
    response = await client.post(
        f"{settings.API_V1_STR}/login/reset-password",
        json={"reset_token": reset_token, "password": "new_password"},
    )
    assert response.status_code == 200
    assert response.json().get("access_token")

    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "reset_user", "password": "new_password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
