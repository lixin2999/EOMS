from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.iam.notification import process_email_outbox

logger = get_logger("eoms.tasks.email")


@celery_app.task(name="eoms.email.process_outbox", bind=True, max_retries=3, default_retry_delay=60)
def process_outbox(self, limit: int = 50) -> dict[str, int]:
    try:
        with session_scope() as db:
            result = process_email_outbox(db, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("邮件出箱处理失败")
        raise self.retry(exc=exc) from exc
    if result.get("failed"):
        logger.warning("邮件发送存在失败记录: %s", result)
    return result
