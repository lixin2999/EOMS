"""报表：经营总览、营收、现金流、利润、项目损益、供应商支出、审批效率与导出。"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.api.response import ok
from app.api.serializers import to_dict
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.services.iam.audit import write_audit
from app.services.report import export as export_service
from app.services.report import service as report_service

router = APIRouter(prefix="/reports", tags=["报表中心"])

VIEW = Depends(require_permission("report:view"))
EXPORT = Depends(require_permission("report:export"))
SNAPSHOT = Depends(require_permission("report:snapshot"))


@router.get("/catalog", summary="报表目录", dependencies=[VIEW])
def catalog() -> dict:
    return ok(
        [
            {"code": code, "name": label}
            for code, label in report_service.REPORT_LABELS.items()
        ]
    )


@router.get("/snapshots", summary="报表快照列表", dependencies=[VIEW])
def list_snapshots(
    db: DbSession,
    ctx: Scope,
    report_code: str | None = None,
    limit: int = Query(default=30, ge=1, le=120),
) -> dict:
    rows = report_service.list_snapshots(db, ctx, report_code=report_code, limit=limit)
    return ok([to_dict(row) for row in rows])


@router.get("/snapshots/{report_code}", summary="最新报表快照", dependencies=[VIEW])
def get_snapshot(report_code: str, db: DbSession, ctx: Scope, period: str | None = None) -> dict:
    row = report_service.get_snapshot(db, ctx, report_code, period)
    return ok(to_dict(row))


@router.post("/snapshots/generate", summary="生成当月报表快照", dependencies=[SNAPSHOT])
def generate_snapshot(db: DbSession, ctx: Scope, period: str | None = None) -> dict:
    result = report_service.generate_company_snapshots(db, ctx.company_id, period)
    return ok(result, f"已生成 {result['count']} 张报表快照")


@router.get("/{report_code}/export", summary="导出报表（Excel/PDF）", dependencies=[EXPORT])
def export_report(
    report_code: str,
    db: DbSession,
    ctx: Scope,
    user: CurrentUser,
    fmt: str = Query(default="excel", alias="format", pattern="^(excel|pdf)$"),
    start: str | None = None,
    end: str | None = None,
    group_by: str | None = None,
    project_id: int | None = None,
    year: int | None = None,
) -> Response:
    code = report_code.upper()
    payload = report_service.build_report(
        db,
        ctx,
        code,
        start=start,
        end=end,
        group_by=group_by,
        project_id=project_id,
        year=year,
    )
    # 导出属于数据外发，必须留下审计痕迹（谁、何时、导出了什么口径的数据）。
    write_audit(
        db,
        user=user,
        action="EXPORT_REPORT",
        target_type="REPORT",
        target_id=0,
        after={
            "code": code,
            "format": fmt,
            "start": start,
            "end": end,
            "group_by": group_by,
            "project_id": project_id,
            "year": year,
            "rows": len(payload.get("items") or payload.get("monthly") or []),
        },
    )
    if fmt == "pdf":
        content = export_service.build_pdf(code, payload)
        media_type = "application/pdf"
        suffix = "pdf"
    else:
        content = export_service.build_excel(code, payload)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        suffix = "xlsx"
    title = report_service.REPORT_LABELS.get(code, code)
    filename = f"{title}-{datetime.now().strftime('%Y%m%d%H%M')}.{suffix}"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=report.{suffix}; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.get("/{report_code}", summary="在线报表数据", dependencies=[VIEW])
def get_report(
    report_code: str,
    db: DbSession,
    ctx: Scope,
    start: str | None = None,
    end: str | None = None,
    group_by: str | None = None,
    project_id: int | None = None,
    year: int | None = None,
) -> dict:
    return ok(
        report_service.build_report(
            db,
            ctx,
            report_code,
            start=start,
            end=end,
            group_by=group_by,
            project_id=project_id,
            year=year,
        )
    )
