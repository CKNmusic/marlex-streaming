from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.user import User


@pytest.mark.asyncio
async def test_user_photo_upload_read_and_delete_as_blob(client: AsyncClient, db: AsyncSession):
    user = User(
        username="user_photo_blob",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    source = Image.new("RGB", (900, 500), color=(10, 120, 210))
    source_bytes = BytesIO()
    source.save(source_bytes, format="PNG")
    source_payload = source_bytes.getvalue()

    response = await client.post(
        f"{settings.API_V1_STR}/users/me/photo",
        headers=headers,
        files={"file": ("profile.png", source_payload, "image/png")},
    )
    assert response.status_code == 200

    response = await client.get(
        f"{settings.API_V1_STR}/users/{user.id}/photo",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")

    normalized = Image.open(BytesIO(response.content))
    assert normalized.size == (180, 240)

    response = await client.delete(f"{settings.API_V1_STR}/users/me/photo", headers=headers)
    assert response.status_code == 200
    assert response.json()["removed"] is True

    response = await client.get(
        f"{settings.API_V1_STR}/users/{user.id}/photo",
        headers=headers,
    )
    assert response.status_code == 204
    assert response.content == b""
