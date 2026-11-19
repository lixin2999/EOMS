from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.iam import User
from app.models.platform import Notification, Outbox
from app.utils.datetime import now


def notify(
    db: Session,
    *,
    company_id: int,
    user_ids: list[int],
    title: str,
    content: str = "",
    type: str = "SYSTEM",
    biz_type: str | None = None,
    biz_id: int | None = None,
    link: str | None = None,
) -> list[Notification]:
    unique_ids = sorted({uid for uid in user_ids if uid})
    notifications: list[Notification] = []
    for user_id in unique_ids:
        item = Notification(
            company_id=company_id,
            user_id=user_id,
            title=title[:255],
            content=content,
            type=type,
            biz_type=biz_type,
            biz_id=biz_id,
            link=link,
        )
        db.add(item)
        notifications.append(item)
    if notifications:
        db.flush()
    return notifications


def queue_email(db: Session, *, company_id: int | None, user_ids: list[int], subject: str, content: str) -> None:
    payload = {"user_ids": sorted(set(user_ids)), "subject": subject, "content": content}
    db.add(Outbox(company_id=company_id, event_type="EMAIL", payload=payload, status="PENDING", next_retry_at=now()))
    db.flush()


def notify_with_email(
    db: Session,
    *,
    company_id: int,
    user_ids: list[int],
    title: str,
    content: str = "",
    type: str = "SYSTEM",
    biz_type: str | None = None,
    biz_id: int | None = None,
    link: str | None = None,
    email: bool = True,
) -> None:
    notify(
        db,
        company_id=company_id,
        user_ids=user_ids,
        title=title,
        content=content,
        type=type,
        biz_type=biz_type,
        biz_id=biz_id,
        link=link,
    )
    if email:
        queue_email(db, company_id=company_id, user_ids=user_ids, subject=title, content=content)


def mark_read(db: Session, user: User, notification_id: int) -> None:
    item = db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    ).scalar_one_or_none()
    if item and item.read_at is None:
        item.read_at = now()
        db.flush()


def mark_all_read(db: Session, user: User) -> int:
    rows = db.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalars()
    count = 0
    for item in rows:
        item.read_at = now()
        count += 1
    db.flush()
    return count


def unread_count(db: Session, user: User) -> int:
    from sqlalchemy import func

    return int(
        db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        ).scalar_one()
    )


def process_email_outbox(db: Session, limit: int = 50) -> dict[str, int]:
    """处理待发送邮件（认领 → 提交 → 逐条发送）。

    - 认领：先把本批记录置 ``SENDING`` 并提交，缩短行锁持有时间，
      避免 SMTP 慢调用把事务拖成长事务；
    - 掉线恢复：批次开头把 ``SENDING`` 且已过 ``next_retry_at`` 的记录重置为 ``PENDING``；
    - 未配置 SMTP 或收件人为空：置 ``SKIPPED`` 并告警，不制造失败风暴；
    - 发送失败：按指数退避重试，超过 5 次置 ``FAILED``。
    """
    from sqlalchemy import update

    from app.core.config import settings
    from app.core.logging import get_logger
    from app.services.iam.mailer import send_email

    logger = get_logger("eoms.email.outbox")

    # ① 恢复上次认领后未完成的记录（进程被杀 / 任务超时）
    db.execute(
        update(Outbox)
        .where(
            Outbox.status == "SENDING",
            Outbox.event_type == "EMAIL",
            Outbox.next_retry_at.is_not(None),
            Outbox.next_retry_at <= now(),
        )
        .values(status="PENDING")
    )
    ids = list(
        db.execute(
            select(Outbox.id)
            .where(
                Outbox.status == "PENDING",
                Outbox.event_type == "EMAIL",
                Outbox.next_retry_at.is_not(None),
                Outbox.next_retry_at <= now(),
            )
            .order_by(Outbox.id)
            .limit(limit)
        ).scalars()
    )
    if not ids:
        db.commit()
        return {"sent": 0, "failed": 0, "skipped": 0, "total": 0}

    # ② 认领并立即提交：认领窗口内其它 worker 不会重复拉取
    db.execute(
        update(Outbox)
        .where(Outbox.id.in_(ids), Outbox.status == "PENDING")
        .values(status="SENDING", next_retry_at=now() + timedelta(minutes=10))
    )
    db.commit()

    sent = failed = skipped = 0
    for outbox_id in ids:
        row = db.get(Outbox, outbox_id)
        if row is None or row.status != "SENDING":
            continue
        user_ids = row.payload.get("user_ids", [])
        users = list(db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()) if user_ids else []
        recipients = [user.email for user in users if user.email]
        subject = str(row.payload.get("subject") or "EOMS 通知")
        content = str(row.payload.get("content") or "")
        if not settings.smtp_host:
            row.status = "SKIPPED"
            row.last_error = "SMTP 未配置，已跳过发送"
            skipped += 1
        elif not recipients:
            row.status = "SKIPPED"
            row.last_error = "收件人为空，已跳过发送"
            skipped += 1
        else:
            try:
                send_email(recipients, subject, content)
                row.status = "SENT"
                row.sent_at = now()
                sent += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断批次
                row.retries = int(row.retries) + 1
                row.last_error = str(exc)[:2000]
                if row.retries >= 5:
                    row.status = "FAILED"
                else:
                    row.status = "PENDING"
                    row.next_retry_at = now() + timedelta(minutes=min(2**row.retries, 60))
                failed += 1
                logger.warning("邮件发送失败 outbox_id=%s: %s", outbox_id, exc)
        db.commit()

    if skipped:
        logger.warning("邮件出箱跳过 %s 条（SMTP 未配置或收件人为空）", skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped, "total": len(ids)}


def _payload_user_ids(payload: dict[str, Any]) -> list[int]:
    return [int(item) for item in payload.get("user_ids", []) if str(item).isdigit()]
