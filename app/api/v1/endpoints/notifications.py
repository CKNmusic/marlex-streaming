from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.user_notification import UserNotification
from app.schemas.user_notification import UserNotification as UserNotificationSchema
from app.services.user_notifications import (
    apply_owner_legacy_state_from_viewer,
    fetch_viewer_states,
    get_or_create_viewer_state,
    resolve_viewer_state,
)

router = APIRouter()


async def _read_notifications_for_viewer(
    *,
    db: AsyncSession,
    current_user: User,
    only_unread: bool,
) -> list[UserNotificationSchema]:
    if current_user.is_superuser:
        result = await db.execute(
            select(UserNotification, User)
            .join(User, User.id == UserNotification.user_id)
            .where(UserNotification.visible_to_user.is_(True))
            .order_by(UserNotification.created_at.desc())
        )
        rows = result.all()
        notifications = [row[0] for row in rows]
        owner_by_notification_id = {int(notification.id): owner for notification, owner in rows}
    else:
        result = await db.execute(
            select(UserNotification)
            .where(
                and_(
                    UserNotification.user_id == current_user.id,
                    UserNotification.visible_to_user.is_(True),
                )
            )
            .order_by(UserNotification.created_at.desc())
        )
        notifications = result.scalars().all()
        owner_by_notification_id: dict[int, User] = {}

    notification_ids = [int(item.id) for item in notifications]
    viewer_state_by_notification = await fetch_viewer_states(
        db,
        viewer_user_id=int(current_user.id),
        notification_ids=notification_ids,
    )

    payload: list[UserNotificationSchema] = []
    for notification in notifications:
        viewer_is_owner = int(notification.user_id) == int(current_user.id)
        is_read, read_at, deleted_by_user = resolve_viewer_state(
            notification=notification,
            viewer_state=viewer_state_by_notification.get(int(notification.id)),
            viewer_is_owner=viewer_is_owner,
        )
        if deleted_by_user:
            continue
        if only_unread and is_read:
            continue
        owner = owner_by_notification_id.get(int(notification.id))
        payload.append(
            UserNotificationSchema(
                id=notification.id,
                code=notification.code,
                user_id=notification.user_id,
                user_name=(owner.full_name or owner.username) if owner else None,
                record_id=notification.record_id,
                record_public_id=notification.record_public_id,
                notification_type=notification.notification_type,
                title=notification.title,
                message=notification.message,
                is_read=is_read,
                read_at=read_at,
                created_at=notification.created_at,
            )
        )
    return payload


async def _load_mutable_notification(
    *,
    db: AsyncSession,
    notification_id: int,
    current_user: User,
) -> UserNotification:
    query = select(UserNotification).where(
        and_(
            UserNotification.id == notification_id,
            UserNotification.visible_to_user.is_(True),
        )
    )
    if not current_user.is_superuser:
        query = query.where(UserNotification.user_id == current_user.id)

    result = await db.execute(query)
    notification = result.scalars().first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")
    return notification


def _serialize_notification_for_viewer(
    *,
    notification: UserNotification,
    owner: User | None,
    is_read: bool,
    read_at: datetime | None,
) -> UserNotificationSchema:
    return UserNotificationSchema(
        id=notification.id,
        code=notification.code,
        user_id=notification.user_id,
        user_name=(owner.full_name or owner.username) if owner else None,
        record_id=notification.record_id,
        record_public_id=notification.record_public_id,
        notification_type=notification.notification_type,
        title=notification.title,
        message=notification.message,
        is_read=is_read,
        read_at=read_at,
        created_at=notification.created_at,
    )


@router.get("/", response_model=List[UserNotificationSchema])
async def read_notifications(
    *,
    db: AsyncSession = Depends(get_db),
    only_unread: bool = Query(default=False),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    return await _read_notifications_for_viewer(
        db=db,
        current_user=current_user,
        only_unread=only_unread,
    )


@router.get("/unread-count")
async def read_notifications_unread_count(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    unread_items = await _read_notifications_for_viewer(
        db=db,
        current_user=current_user,
        only_unread=True,
    )
    return {"count": len(unread_items)}


@router.patch("/{notification_id}/read", response_model=UserNotificationSchema)
async def mark_notification_as_read(
    *,
    db: AsyncSession = Depends(get_db),
    notification_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    notification = await _load_mutable_notification(
        db=db,
        notification_id=notification_id,
        current_user=current_user,
    )
    viewer_state = await get_or_create_viewer_state(
        db,
        notification=notification,
        viewer_user_id=int(current_user.id),
    )
    if not viewer_state.is_read:
        viewer_state.is_read = True
        viewer_state.read_at = datetime.now(timezone.utc)

    apply_owner_legacy_state_from_viewer(
        notification=notification,
        viewer_user_id=int(current_user.id),
        viewer_state=viewer_state,
    )

    db.add(viewer_state)
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    await db.refresh(viewer_state)

    owner: User | None = None
    if current_user.is_superuser:
        owner = await db.get(User, int(notification.user_id))
    return _serialize_notification_for_viewer(
        notification=notification,
        owner=owner,
        is_read=bool(viewer_state.is_read),
        read_at=viewer_state.read_at,
    )


@router.delete("/{notification_id}", response_model=UserNotificationSchema)
async def delete_notification_from_user_view(
    *,
    db: AsyncSession = Depends(get_db),
    notification_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    notification = await _load_mutable_notification(
        db=db,
        notification_id=notification_id,
        current_user=current_user,
    )
    viewer_state = await get_or_create_viewer_state(
        db,
        notification=notification,
        viewer_user_id=int(current_user.id),
    )
    viewer_state.deleted_by_user = True
    viewer_state.deleted_at = datetime.now(timezone.utc)
    if not viewer_state.is_read:
        viewer_state.is_read = True
        viewer_state.read_at = datetime.now(timezone.utc)

    apply_owner_legacy_state_from_viewer(
        notification=notification,
        viewer_user_id=int(current_user.id),
        viewer_state=viewer_state,
    )

    db.add(viewer_state)
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    await db.refresh(viewer_state)

    owner: User | None = None
    if current_user.is_superuser:
        owner = await db.get(User, int(notification.user_id))
    return _serialize_notification_for_viewer(
        notification=notification,
        owner=owner,
        is_read=bool(viewer_state.is_read),
        read_at=viewer_state.read_at,
    )
