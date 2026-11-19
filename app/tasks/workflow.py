from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import session_scope
from app.workflow.engine import overdue_tasks

logger = get_logger("eoms.tasks.workflow")


@celery_app.task(name="eoms.workflow.overdue_remind")
def overdue_remind(limit: int = 200) -> dict[str, int]:
    with session_scope() as db:
        count = overdue_tasks(db, limit=limit)
    if count:
        logger.info("已发送审批超时提醒 %s 条", count)
    return {"reminded": count}
