"""Celery 任务集合。

导入各任务模块以确保 worker 启动时完成注册。
"""

from app.tasks import budget, cost, email, project, reports, vendor, workflow  # noqa: F401

__all__ = ["budget", "cost", "email", "project", "reports", "vendor", "workflow"]
