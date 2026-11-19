"""Celery 应用与定时任务编排。

开发环境未配置 Redis 时自动切换为 eager 模式，任务在调用进程内同步执行，
生产环境通过 `celery -A app.celery_app worker/beat` 运行。
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "eoms",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.email",
        "app.tasks.workflow",
        "app.tasks.budget",
        "app.tasks.reports",
        "app.tasks.vendor",
        "app.tasks.project",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=900,
    task_soft_time_limit=840,
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    task_default_queue="eoms",
    beat_schedule={
        "email-outbox": {
            "task": "eoms.email.process_outbox",
            "schedule": 60.0,
        },
        "workflow-overdue": {
            "task": "eoms.workflow.overdue_remind",
            "schedule": crontab(minute="*/10"),
        },
        "contract-expiry": {
            "task": "eoms.vendor.contract_expiry",
            "schedule": crontab(hour=8, minute=10),
        },
        "budget-alert": {
            "task": "eoms.budget.scan_alerts",
            "schedule": crontab(hour=8, minute=30),
        },
        "report-snapshot": {
            "task": "eoms.reports.snapshot",
            "schedule": crontab(hour=1, minute=10),
        },
        "project-health": {
            "task": "eoms.project.health_check",
            "schedule": crontab(hour=9, minute=0),
        },
    },
)


@celery_app.task(name="eoms.ping")
def ping() -> str:
    """连通性探针。"""
    return "pong"
