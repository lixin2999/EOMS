"""API v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    auth,
    contracts,
    dashboard,
    files,
    finance,
    iam,
    meta,
    notifications,
    projects,
    reports,
    vendors,
    workflow,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(meta.router)
api_router.include_router(dashboard.router)
api_router.include_router(approvals.router)
api_router.include_router(workflow.router)
api_router.include_router(projects.router)
api_router.include_router(vendors.router)
api_router.include_router(contracts.router)
api_router.include_router(finance.router)
api_router.include_router(reports.router)
api_router.include_router(files.router)
api_router.include_router(notifications.router)
api_router.include_router(iam.router)
