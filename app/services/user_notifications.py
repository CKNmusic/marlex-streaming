from datetime import datetime
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import Record
from app.models.user_notification import UserNotification
from app.models.user_notification_viewer_state import UserNotificationViewerState


NOTIFICATION_TYPE_DOWNLOAD_SUCCESS = "download_success"
NOTIFICATION_TYPE_DOWNLOAD_ERROR = "download_error"
NOTIFICATION_TYPE_RECORD_ERROR = "record_error"
NOTIFICATION_TYPE_RECORD_FINISHED = "record_finished"
NOTIFICATION_TYPE_LOGIN = "auth_login"


def is_record_failure(*, stop_reason: Optional[str], final_status: Optional[str]) -> bool:
    normalized_status = str(final_status or "").strip().lower()
    normalized_reason = str(stop_reason or "").strip().lower()
    if normalized_status.startswith("error_"):
        return True
    return normalized_reason in {"connection", "disconnect", "timeout", "error"}


async def build_notification_code(db: AsyncSession, user_id: int) -> str:
    pending_codes = {
        item.code
        for item in db.new
        if isinstance(item, UserNotification) and bool(getattr(item, "code", None))
    }
    while True:
        candidate = f"{user_id:05d}_{time.time_ns()}"
        if candidate in pending_codes:
            continue
        existing = await db.scalar(
            select(UserNotification.id).where(UserNotification.code == candidate).limit(1)
        )
        if existing is None:
            return candidate


async def create_user_notification(
    db: AsyncSession,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    visible_to_user: bool = True,
    record: Optional[Record] = None,
    record_id: Optional[int] = None,
    record_public_id: Optional[str] = None,
) -> UserNotification:
    normalized_record_id = record_id if record_id is not None else (record.id if record else None)
    normalized_record_public_id = (
        record_public_id
        if record_public_id is not None
        else (record.public_id if record else None)
    )
    notification = UserNotification(
        code=await build_notification_code(db, user_id),
        user_id=user_id,
        record_id=normalized_record_id,
        record_public_id=normalized_record_public_id,
        notification_type=notification_type,
        title=title.strip(),
        message=message.strip(),
        visible_to_user=visible_to_user,
    )
    db.add(notification)
    return notification


async def fetch_viewer_states(
    db: AsyncSession,
    *,
    viewer_user_id: int,
    notification_ids: list[int],
) -> dict[int, UserNotificationViewerState]:
    if not notification_ids:
        return {}
    result = await db.execute(
        select(UserNotificationViewerState).where(
            UserNotificationViewerState.viewer_user_id == viewer_user_id,
            UserNotificationViewerState.notification_id.in_(notification_ids),
        )
    )
    items = result.scalars().all()
    return {int(item.notification_id): item for item in items}


def resolve_viewer_state(
    *,
    notification: UserNotification,
    viewer_state: UserNotificationViewerState | None,
    viewer_is_owner: bool,
) -> tuple[bool, datetime | None, bool]:
    if viewer_state is not None:
        return bool(viewer_state.is_read), viewer_state.read_at, bool(viewer_state.deleted_by_user)
    if viewer_is_owner:
        return bool(notification.is_read), notification.read_at, bool(notification.deleted_by_user)
    return False, None, False


async def get_or_create_viewer_state(
    db: AsyncSession,
    *,
    notification: UserNotification,
    viewer_user_id: int,
) -> UserNotificationViewerState:
    result = await db.execute(
        select(UserNotificationViewerState).where(
            UserNotificationViewerState.notification_id == notification.id,
            UserNotificationViewerState.viewer_user_id == viewer_user_id,
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        return existing

    viewer_is_owner = int(notification.user_id) == int(viewer_user_id)
    state = UserNotificationViewerState(
        notification_id=notification.id,
        viewer_user_id=viewer_user_id,
        is_read=bool(notification.is_read) if viewer_is_owner else False,
        read_at=notification.read_at if viewer_is_owner and notification.is_read else None,
        deleted_by_user=bool(notification.deleted_by_user) if viewer_is_owner else False,
    )
    db.add(state)
    await db.flush()
    return state


def apply_owner_legacy_state_from_viewer(
    *,
    notification: UserNotification,
    viewer_user_id: int,
    viewer_state: UserNotificationViewerState,
) -> None:
    if int(notification.user_id) != int(viewer_user_id):
        return
    notification.is_read = bool(viewer_state.is_read)
    notification.read_at = viewer_state.read_at
    notification.deleted_by_user = bool(viewer_state.deleted_by_user)
