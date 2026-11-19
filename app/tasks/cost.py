from __future__ import annotations

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.cost.pending import post_pending_costs

logger = get_logger("eoms.tasks.cost")


@celery_app.task(name="eoms.cost.post_pending")
def post_pending(company_id: int | None = None, limit: int = 200) -> dict[str, int]:
    """把期间关账时暂存的成本补记到 ``fin_cost_record``（幂等，可重复执行）。"""
    with session_scope() as db:
        result = post_pending_costs(db, company_id=company_id, limit=limit)
    logger.info("待补记成本处理完成：%s", result)
    return result