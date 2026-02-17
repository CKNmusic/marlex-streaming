import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core import security
from app.models.user import User

@pytest.mark.asyncio
async def test_bootstrap_first_superuser_only_when_users_table_is_empty(client: AsyncClient, db: AsyncSession):
    await db.execute(delete(User))
    await db.commit()

    payload = {
        "username": "bootstrap_admin",
        "full_name": "Bootstrap Admin",
        "password": "123",
        "is_superuser": False,
        "is_active": True,
    }

    response = await client.post(f"{settings.API_V1_STR}/users/bootstrap", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "bootstrap_admin"
    assert data["is_superuser"] is True
    assert data["is_active"] is True

    response_second = await client.post(f"{settings.API_V1_STR}/users/bootstrap", json=payload)
    assert response_second.status_code == 409


@pytest.mark.asyncio
async def test_user_crud_and_activation(client: AsyncClient, db: AsyncSession):
    # 1. Setup Admin
    admin = User(
        username="master_test",
        password=security.get_password_hash("password"),
        is_superuser=True,
        is_active=True
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    
    access_token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 2. Add New User
    user_data = {
        "username": "new_doctor",
        "full_name": "Dr. Strange",
        "password": "doctorpassword",
        "is_superuser": False,
        "is_active": True,
    }
    
    response = await client.post(
        f"{settings.API_V1_STR}/users/",
        json=user_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user_data["username"]
    assert data["is_active"] is True  # Should be active by default as per request
    
    user_id = data["id"]
    
    # 3. List Users
    response = await client.get(f"{settings.API_V1_STR}/users/", headers=headers)
    assert response.status_code == 200
    assert any(u["username"] == "new_doctor" for u in response.json())
    
    # 4. Deactivate User
    # We need to check if we have a toggle or specific update
    response = await client.patch(
        f"{settings.API_V1_STR}/users/{user_id}",
        json={"is_active": False},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    
    # 5. Reactivate User
    response = await client.patch(
        f"{settings.API_V1_STR}/users/{user_id}",
        json={"is_active": True},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is True
    
    # 6. Edit User
    response = await client.patch(
        f"{settings.API_V1_STR}/users/{user_id}",
        json={"full_name": "Stephen Strange"},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Stephen Strange"

    # 7. Delete User
    response = await client.delete(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=headers
    )
    assert response.status_code == 200
