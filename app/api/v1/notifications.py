"""站内通知：列表、未读数、标记已读。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.response import ok
from app.api.serializers import notification as serialize_notification
from app.core.deps import CurrentUser, DbSession
from app.core.pagination import PageParams
from app.models.platform import Notification
from app.schemas.common import NotificationReadIn
from app.services.iam import notification as notification_service

router = APIRouter(prefix="/notifications", tags=["通知中心"])


@router.get("", summary="我的通知")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    params: PageParams = Depends(),
    unread: bool = False,
    notice_type: str | None = None,
) -> dict:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    if notice_type:
        stmt = stmt.where(Notification.type == notice_type)
    total = int(
        db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    )
    rows = list(
        db.execute(stmt.order_by(Notification.id.desc()).limit(params.page_size).offset(params.offset))
        .scalars()
        .all()
    )
    return ok(
        {
            "items": [serialize_notification(row) for row in rows],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }
    )


@router.get("/unread-count", summary="未读通知数量")
def unread_count(db: DbSession, user: CurrentUser) -> dict:
    return ok({"count": notification_service.unread_count(db, user)})


@router.post("/read", summary="批量标记已读")
def mark_read(payload: NotificationReadIn, db: DbSession, user: CurrentUser) -> dict:
    if payload.all:
        count = notification_service.mark_all_read(db, user)
        return ok({"count": count}, "全部通知已标记为已读")
    count = 0
    if payload.ids:
        rows = db.execute(
            select(Notification).where(
                Notification.user_id == user.id, Notification.id.in_(payload.ids)
            )
        ).scalars()
        from app.utils.datetime import now

        for item in rows:
            if item.read_at is None:
                item.read_at = now()
                count += 1
        db.flush()
    return ok({"count": count}, "通知已标记为已读")


@router.post("/{notification_id}/read", summary="标记单条已读")
def mark_one(notification_id: int, db: DbSession, user: CurrentUser) -> dict:
    notification_service.mark_read(db, user, notification_id)
    return ok(None, "通知已标记为已读")
