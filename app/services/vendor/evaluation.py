"""供应商评价与分级：按项目质量/进度/配合度评分，形成年度评价报告。"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext, assert_project_access
from app.models.iam import User
from app.models.project import Project
from app.models.vendor import Contract, Evaluation, Vendor, VendorProject
from app.services.iam.audit import write_audit
from app.utils.datetime import to_date, today
from app.utils.money import to_decimal

WEIGHTS = {"quality": Decimal("0.4"), "schedule": Decimal("0.3"), "cooperate": Decimal("0.3")}


def _score(value, field_name: str) -> Decimal:
    score = to_decimal(value, field_name=field_name)
    if score < 0 or score > 100:
        raise BusinessRuleError(f"{field_name}必须在 0-100 之间")
    return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def grade_of(score: Decimal) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    return "C"


def get_evaluation(db: Session, ctx: ScopeContext, evaluation_id: int) -> Evaluation:
    item = db.get(Evaluation, evaluation_id)
    if item is None or item.company_id != ctx.company_id:
        raise NotFoundError("评价记录不存在")
    return item


def list_evaluations(
    db: Session, ctx: ScopeContext, vendor_id: int, *, year: int | None = None
) -> list[Evaluation]:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.company_id != ctx.company_id:
        raise NotFoundError("供应商不存在")
    stmt = select(Evaluation).where(Evaluation.vendor_id == vendor_id)
    if year:
        stmt = stmt.where(
            Evaluation.eval_date >= date(year, 1, 1), Evaluation.eval_date <= date(year, 12, 31)
        )
    return list(db.execute(stmt.order_by(Evaluation.eval_date.desc(), Evaluation.id.desc())).scalars().all())


def create_evaluation(
    db: Session, user: User, ctx: ScopeContext, vendor_id: int, payload: dict
) -> Evaluation:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.company_id != ctx.company_id:
        raise NotFoundError("供应商不存在")
    if vendor.status == "BLACKLIST":
        raise BusinessRuleError("黑名单供应商不能评价")
    project_id = payload.get("project_id")
    if project_id:
        project = db.get(Project, int(project_id))
        if project is None or project.company_id != ctx.company_id:
            raise BusinessRuleError("项目不存在")
        assert_project_access(db, ctx, project.id)
    quality = _score(payload.get("quality_score"), "交付质量分")
    schedule = _score(payload.get("schedule_score"), "进度分")
    cooperate = _score(payload.get("cooperate_score"), "配合度分")
    total = (quality * WEIGHTS["quality"] + schedule * WEIGHTS["schedule"] + cooperate * WEIGHTS["cooperate"]).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    grade = grade_of(total)
    item = Evaluation(
        company_id=user.company_id,
        vendor_id=vendor.id,
        project_id=int(project_id) if project_id else None,
        evaluator_id=user.id,
        quality_score=quality,
        schedule_score=schedule,
        cooperate_score=cooperate,
        total_score=total,
        grade=grade,
        comment=(payload.get("comment") or "")[:1000],
        eval_date=to_date(payload.get("eval_date")) or today(),
    )
    db.add(item)
    db.flush()

    # 综合分取最近 12 个月均值，等级自动回写供应商主档
    scores = list(
        db.execute(
            select(Evaluation.total_score)
            .where(Evaluation.vendor_id == vendor.id)
            .order_by(Evaluation.id.desc())
            .limit(20)
        ).scalars()
    )
    if scores:
        avg = (sum(Decimal(str(value)) for value in scores) / Decimal(len(scores))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vendor.score = avg
        vendor.level = grade_of(avg)
    if project_id:
        row = db.execute(
            select(VendorProject).where(
                VendorProject.vendor_id == vendor.id, VendorProject.project_id == int(project_id)
            )
        ).scalars().first()
        if row:
            row.score = total
    write_audit(
        db,
        user=user,
        action="CREATE_EVALUATION",
        target_type="VENDOR",
        target_id=vendor.id,
        after={"total_score": str(total), "grade": grade, "project_id": project_id},
    )
    return item


def annual_report(db: Session, ctx: ScopeContext, vendor_id: int, year: int) -> dict:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None or vendor.company_id != ctx.company_id:
        raise NotFoundError("供应商不存在")
    start, end = date(year, 1, 1), date(year, 12, 31)
    rows = list(
        db.execute(
            select(Evaluation)
            .where(
                Evaluation.vendor_id == vendor_id,
                Evaluation.eval_date >= start,
                Evaluation.eval_date <= end,
            )
            .order_by(Evaluation.eval_date)
        )
        .scalars()
        .all()
    )
    monthly: dict[str, dict] = {}
    for item in rows:
        key = item.eval_date.strftime("%Y-%m")
        bucket = monthly.setdefault(
            key,
            {
                "period": key,
                "count": 0,
                "total": Decimal("0"),
                "quality": Decimal("0"),
                "schedule": Decimal("0"),
                "cooperate": Decimal("0"),
            },
        )
        bucket["count"] += 1
        bucket["total"] += Decimal(str(item.total_score or 0))
        bucket["quality"] += Decimal(str(item.quality_score or 0))
        bucket["schedule"] += Decimal(str(item.schedule_score or 0))
        bucket["cooperate"] += Decimal(str(item.cooperate_score or 0))
    trend = []
    for key in sorted(monthly):
        bucket = monthly[key]
        count = max(bucket["count"], 1)
        trend.append(
            {
                "period": key,
                "count": bucket["count"],
                "total_score": float(round(bucket["total"] / count, 2)),
                "quality_score": float(round(bucket["quality"] / count, 2)),
                "schedule_score": float(round(bucket["schedule"] / count, 2)),
                "cooperate_score": float(round(bucket["cooperate"] / count, 2)),
            }
        )
    grade_count = {"A": 0, "B": 0, "C": 0}
    for item in rows:
        grade_count[item.grade] = grade_count.get(item.grade, 0) + 1
    avg_total = (sum(Decimal(str(item.total_score or 0)) for item in rows) / Decimal(len(rows))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ) if rows else Decimal("0.00")
    contract_total = db.execute(
        select(func.coalesce(func.sum(Contract.amount), 0)).where(
            Contract.vendor_id == vendor_id,
            Contract.sign_date >= start,
            Contract.sign_date <= end,
        )
    ).scalar_one()
    paid_total = db.execute(
        select(func.coalesce(func.sum(VendorProject.paid_amount), 0)).where(VendorProject.vendor_id == vendor_id)
    ).scalar_one()
    return {
        "vendor": {
            "id": vendor.id,
            "code": vendor.code,
            "name": vendor.name,
            "level": vendor.level,
            "score": float(vendor.score or 0),
        },
        "year": year,
        "evaluation_count": len(rows),
        "average_score": float(avg_total),
        "grade": grade_of(avg_total) if rows else vendor.level,
        "grade_distribution": grade_count,
        "monthly_trend": trend,
        "contract_amount": float(contract_total or 0),
        "paid_amount": float(paid_total or 0),
        "evaluations": [
            {
                "id": item.id,
                "project_id": item.project_id,
                "quality_score": float(item.quality_score or 0),
                "schedule_score": float(item.schedule_score or 0),
                "cooperate_score": float(item.cooperate_score or 0),
                "total_score": float(item.total_score or 0),
                "grade": item.grade,
                "comment": item.comment,
                "eval_date": item.eval_date.isoformat(),
            }
            for item in rows
        ],
    }
