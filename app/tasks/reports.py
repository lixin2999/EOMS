from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.report.service import generate_all_snapshots

logger = get_logger("eoms.tasks.reports")


@celery_app.task(name="eoms.reports.snapshot")
def snapshot(period: str | None = None) -> dict[str, object]:
    with session_scope() as db:
        result = generate_all_snapshots(db, period)
    logger.info("报表快照生成完成: %s", result)
    return result
