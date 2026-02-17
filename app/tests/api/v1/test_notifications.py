import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.user import User
from app.models.user_notification import UserNotification
from app.models.user_notification_viewer_state import UserNotificationViewerState
from app.services.user_notifications import (
    NOTIFICATION_TYPE_LOGIN,
    NOTIFICATION_TYPE_RECORD_FINISHED,
    create_user_notification,
)


@pytest.mark.asyncio
async def test_notifications_list_mark_read_delete(client: AsyncClient, db: AsyncSession):
    user = User(
        username="user_notifications",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await create_user_notification(
        db,
        user_id=user.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação REC-AAA finalizada",
        message="Motivo: user | Data: 10/02/2026, 09:00:00",
        visible_to_user=True,
    )
    visible_read = await create_user_notification(
        db,
        user_id=user.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação REC-BBB finalizada",
        message="Motivo: user | Data: 10/02/2026, 10:00:00",
        visible_to_user=True,
    )
    visible_read.is_read = True
    invisible_login = await create_user_notification(
        db,
        user_id=user.id,
        notification_type=NOTIFICATION_TYPE_LOGIN,
        title="Login realizado",
        message="Log interno de autenticação.",
        visible_to_user=False,
    )
    db.add_all([visible_read, invisible_login])
    await db.commit()

    token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(f"{settings.API_V1_STR}/notifications/", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert all(item["notification_type"] != NOTIFICATION_TYPE_LOGIN for item in payload)

    response = await client.get(f"{settings.API_V1_STR}/notifications/unread-count", headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 1

    unread_id = next(item["id"] for item in payload if item["is_read"] is False)
    response = await client.patch(f"{settings.API_V1_STR}/notifications/{unread_id}/read", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_read"] is True

    response = await client.get(f"{settings.API_V1_STR}/notifications/unread-count", headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 0

    response = await client.delete(f"{settings.API_V1_STR}/notifications/{unread_id}", headers=headers)
    assert response.status_code == 200

    response = await client.get(f"{settings.API_V1_STR}/notifications/", headers=headers)
    assert response.status_code == 200
    assert all(item["id"] != unread_id for item in response.json())


@pytest.mark.asyncio
async def test_login_creates_hidden_notification_log(client: AsyncClient, db: AsyncSession):
    user = User(
        username="user_login_notification",
        password=security.get_password_hash("123456"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": "user_login_notification", "password": "123456"},
    )
    assert response.status_code == 200
    assert response.json().get("access_token")

    query = await db.execute(
        select(UserNotification).where(UserNotification.user_id == user.id)
    )
    logs = query.scalars().all()
    assert any(
        item.notification_type == NOTIFICATION_TYPE_LOGIN and item.visible_to_user is False
        for item in logs
    )


@pytest.mark.asyncio
async def test_notifications_only_unread_filter_respects_read_state(client: AsyncClient, db: AsyncSession):
    user = User(
        username="user_notifications_filter",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    first = await create_user_notification(
        db,
        user_id=user.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação REC-111 finalizada",
        message="Motivo: user | Data: 11/02/2026, 09:00:00",
        visible_to_user=True,
    )
    second = await create_user_notification(
        db,
        user_id=user.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação REC-222 finalizada",
        message="Motivo: user | Data: 11/02/2026, 10:00:00",
        visible_to_user=True,
    )
    db.add_all([first, second])
    await db.commit()

    token = security.create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    unread_response = await client.get(
        f"{settings.API_V1_STR}/notifications/?only_unread=true",
        headers=headers,
    )
    assert unread_response.status_code == 200
    unread_payload = unread_response.json()
    assert len(unread_payload) == 2

    read_target_id = unread_payload[0]["id"]
    mark_read = await client.patch(
        f"{settings.API_V1_STR}/notifications/{read_target_id}/read",
        headers=headers,
    )
    assert mark_read.status_code == 200
    assert mark_read.json()["is_read"] is True

    unread_after_read = await client.get(
        f"{settings.API_V1_STR}/notifications/?only_unread=true",
        headers=headers,
    )
    assert unread_after_read.status_code == 200
    unread_after_payload = unread_after_read.json()
    assert len(unread_after_payload) == 1
    assert unread_after_payload[0]["id"] != read_target_id
    assert unread_after_payload[0]["is_read"] is False

    full_list = await client.get(f"{settings.API_V1_STR}/notifications/", headers=headers)
    assert full_list.status_code == 200
    full_payload = full_list.json()
    assert len(full_payload) == 2
    assert any(item["id"] == read_target_id and item["is_read"] is True for item in full_payload)


@pytest.mark.asyncio
async def test_admin_notifications_include_foreign_owner_metadata(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_notifications",
        full_name="Admin One",
        password=security.get_password_hash("123"),
        is_superuser=True,
        is_active=True,
    )
    doctor = User(
        username="doctor_notifications",
        full_name="Dr. House",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, doctor])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(doctor)

    own = await create_user_notification(
        db,
        user_id=admin.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação ADM-1 finalizada",
        message="Motivo: user | Data: 11/02/2026, 11:00:00",
        visible_to_user=True,
    )
    foreign = await create_user_notification(
        db,
        user_id=doctor.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação DOC-1 finalizada",
        message="Motivo: user | Data: 11/02/2026, 11:05:00",
        visible_to_user=True,
    )
    db.add_all([own, foreign])
    await db.commit()

    token = security.create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(f"{settings.API_V1_STR}/notifications/", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 2

    own_item = next((item for item in payload if item["id"] == own.id), None)
    foreign_item = next((item for item in payload if item["id"] == foreign.id), None)
    assert own_item is not None
    assert foreign_item is not None
    assert own_item["user_id"] == admin.id
    assert foreign_item["user_id"] == doctor.id
    assert foreign_item["user_name"] == "Dr. House"


@pytest.mark.asyncio
async def test_admin_notification_view_state_is_independent_from_owner(client: AsyncClient, db: AsyncSession):
    admin = User(
        username="admin_notifications_state",
        full_name="Admin State",
        password=security.get_password_hash("123"),
        is_superuser=True,
        is_active=True,
    )
    doctor = User(
        username="doctor_notifications_state",
        full_name="Dr. State",
        password=security.get_password_hash("123"),
        is_superuser=False,
        is_active=True,
    )
    db.add_all([admin, doctor])
    await db.commit()
    await db.refresh(admin)
    await db.refresh(doctor)

    foreign = await create_user_notification(
        db,
        user_id=doctor.id,
        notification_type=NOTIFICATION_TYPE_RECORD_FINISHED,
        title="Gravação DOC-STATE finalizada",
        message="Motivo: user | Data: 11/02/2026, 12:30:00",
        visible_to_user=True,
    )
    db.add(foreign)
    await db.commit()

    admin_headers = {"Authorization": f"Bearer {security.create_access_token(admin.id)}"}
    doctor_headers = {"Authorization": f"Bearer {security.create_access_token(doctor.id)}"}

    admin_list = await client.get(f"{settings.API_V1_STR}/notifications/", headers=admin_headers)
    assert admin_list.status_code == 200
    admin_item = next((item for item in admin_list.json() if item["id"] == foreign.id), None)
    assert admin_item is not None
    assert admin_item["is_read"] is False

    mark_read = await client.patch(
        f"{settings.API_V1_STR}/notifications/{foreign.id}/read",
        headers=admin_headers,
    )
    assert mark_read.status_code == 200
    assert mark_read.json()["is_read"] is True

    doctor_list_after_admin_read = await client.get(
        f"{settings.API_V1_STR}/notifications/?only_unread=true",
        headers=doctor_headers,
    )
    assert doctor_list_after_admin_read.status_code == 200
    assert any(item["id"] == foreign.id for item in doctor_list_after_admin_read.json())

    delete_for_admin = await client.delete(
        f"{settings.API_V1_STR}/notifications/{foreign.id}",
        headers=admin_headers,
    )
    assert delete_for_admin.status_code == 200

    admin_list_after_delete = await client.get(f"{settings.API_V1_STR}/notifications/", headers=admin_headers)
    assert admin_list_after_delete.status_code == 200
    assert all(item["id"] != foreign.id for item in admin_list_after_delete.json())

    doctor_list_after_admin_delete = await client.get(
        f"{settings.API_V1_STR}/notifications/",
        headers=doctor_headers,
    )
    assert doctor_list_after_admin_delete.status_code == 200
    assert any(item["id"] == foreign.id for item in doctor_list_after_admin_delete.json())

    states_query = await db.execute(
        select(UserNotificationViewerState).where(
            UserNotificationViewerState.notification_id == foreign.id,
            UserNotificationViewerState.viewer_user_id == admin.id,
        )
    )
    state = states_query.scalars().first()
    assert state is not None
    assert state.is_read is True
    assert state.deleted_by_user is True
