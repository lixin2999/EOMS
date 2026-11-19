from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.workflow import WorkflowInstance

logger = get_logger("eoms.workflow")

Handler = Callable[[Session, WorkflowInstance], None]
_HANDLERS: dict[tuple[str, str], Handler] = {}


def register(biz_type: str, event: str) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        _HANDLERS[(biz_type, event)] = func
        return func

    return decorator


def dispatch(db: Session, event: str, instance: WorkflowInstance) -> None:
    ensure_handlers()
    handler = _HANDLERS.get((instance.biz_type, event))
    if handler is None:
        logger.debug("未注册审批回调: %s/%s", instance.biz_type, event)
        return
    handler(db, instance)


_loaded = False


def ensure_handlers() -> None:
    global _loaded
    if _loaded:
        return
    # 延迟导入，避免 services <-> workflow 循环依赖
    import app.services.approval.callbacks  # noqa: F401
    import app.services.project.callbacks  # noqa: F401
    import app.services.vendor.callbacks  # noqa: F401

    _loaded = True
