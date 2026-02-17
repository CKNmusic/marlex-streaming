import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core import security
from app.models.user import User


@pytest.mark.asyncio
async def test_protocols_cities_places_crud(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_refs",
        full_name="Admin Refs",
        password=security.get_password_hash("admin"),
        is_superuser=True,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Protocols
    response = await client.get(f"{settings.API_V1_STR}/protocols/", headers=headers)
    assert response.status_code == 200
    existing_protocols = {str(item.get("protocol", "")).lower() for item in response.json()}
    candidate_protocol = next(
        (name for name in ("rtmps", "rtsp", "rtsps", "srt") if name not in existing_protocols),
        None,
    )
    assert candidate_protocol is not None

    response = await client.post(
        f"{settings.API_V1_STR}/protocols/",
        json={"protocol": candidate_protocol, "port": 10080},
        headers=headers,
    )
    assert response.status_code == 200
    protocol_id = response.json()["id"]

    response = await client.get(f"{settings.API_V1_STR}/protocols/", headers=headers)
    assert response.status_code == 200
    assert any(p["protocol"] == candidate_protocol for p in response.json())

    response = await client.patch(
        f"{settings.API_V1_STR}/protocols/{protocol_id}",
        json={"port": 1936},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["port"] == 1936

    response = await client.delete(
        f"{settings.API_V1_STR}/protocols/{protocol_id}",
        headers=headers,
    )
    assert response.status_code == 200

    # Cities
    response = await client.post(
        f"{settings.API_V1_STR}/cities/",
        json={"name": "Cidade API", "uf": "AP"},
        headers=headers,
    )
    assert response.status_code == 200
    city_id = response.json()["id"]

    response = await client.get(f"{settings.API_V1_STR}/cities/", headers=headers)
    assert response.status_code == 200
    assert any(c["id"] == city_id for c in response.json())

    response = await client.patch(
        f"{settings.API_V1_STR}/cities/{city_id}",
        json={"name": "Cidade API Updated"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "não pode ser editada" in response.json()["detail"]
    response = await client.post(
        f"{settings.API_V1_STR}/cities/",
        json={"name": "Cidade API 2", "uf": "A2"},
        headers=headers,
    )
    assert response.status_code == 200
    city_id_2 = response.json()["id"]

    # Places
    response = await client.post(
        f"{settings.API_V1_STR}/places/",
        json={"name": "Local API", "description": "Sala B", "city_id": city_id},
        headers=headers,
    )
    assert response.status_code == 200
    place_id = response.json()["id"]

    response = await client.get(f"{settings.API_V1_STR}/places/", headers=headers)
    assert response.status_code == 200
    assert any(l["id"] == place_id for l in response.json())

    response = await client.patch(
        f"{settings.API_V1_STR}/places/{place_id}",
        json={"description": "Sala B2"},
        headers=headers,
    )
    assert response.status_code == 200
    response = await client.patch(
        f"{settings.API_V1_STR}/places/{place_id}",
        json={"city_id": city_id_2},
        headers=headers,
    )
    assert response.status_code == 400
    assert "não pode ser alterada" in response.json()["detail"]

    # Marks
    response = await client.post(
        f"{settings.API_V1_STR}/marks/",
        json={"name": "Marca API"},
        headers=headers,
    )
    assert response.status_code == 200
    mark_id = response.json()["id"]

    response = await client.get(f"{settings.API_V1_STR}/marks/", headers=headers)
    assert response.status_code == 200
    assert any(mark["id"] == mark_id for mark in response.json())

    response = await client.patch(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        json={"name": "Marca API Updated"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Marca API Updated"
    mark_id = response.json()["id"]

    response = await client.post(
        f"{settings.API_V1_STR}/devices/",
        json={
            "model": "Model API",
            "sn": "SN-MARK-API-0001",
            "mark_id": mark_id,
            "protocol": "srt",
            "place_id": place_id,
            "is_active": True,
        },
        headers=headers,
    )
    assert response.status_code == 200
    device_id = response.json()["id"]

    response = await client.patch(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        json={"name": "Marca API Renamed"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "não pode renomear" in response.json()["detail"]

    response = await client.patch(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert response.status_code == 400
    assert "não pode desativar" in response.json()["detail"]

    response = await client.delete(
        f"{settings.API_V1_STR}/marks/{mark_id}",
        headers=headers,
    )
    assert response.status_code == 400
    assert "não pode excluir" in response.json()["detail"]

    response = await client.post(
        f"{settings.API_V1_STR}/marks/",
        json={"name": "Marca API Livre"},
        headers=headers,
    )
    assert response.status_code == 200
    free_mark_id = response.json()["id"]

    response = await client.patch(
        f"{settings.API_V1_STR}/marks/{free_mark_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    response = await client.delete(
        f"{settings.API_V1_STR}/marks/{free_mark_id}",
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.delete(
        f"{settings.API_V1_STR}/places/{place_id}",
        headers=headers,
    )
    assert response.status_code == 400
    assert "em uso" in response.json()["detail"]

    response = await client.delete(
        f"{settings.API_V1_STR}/devices/{device_id}",
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.delete(
        f"{settings.API_V1_STR}/places/{place_id}",
        headers=headers,
    )
    assert response.status_code == 200

    response = await client.delete(
        f"{settings.API_V1_STR}/cities/{city_id}",
        headers=headers,
    )
    assert response.status_code == 200
    response = await client.delete(
        f"{settings.API_V1_STR}/cities/{city_id_2}",
        headers=headers,
    )
    assert response.status_code == 200
