from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.approval import Leave, LeaveBalance
from app.models.enums import LeaveStatus, LeaveType
from app.models.iam import User
from app.models.workflow import WorkflowInstance
from app.services.common import claim_version, company_code
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.utils.datetime import now
from app.utils.money import to_decimal
from app.utils.numbering import next_no
from app.workflow import engine

LEAVE_TYPES = {item.value for item in LeaveType}
BALANCE_TYPES = {LeaveType.ANNUAL.value, LeaveType.COMP.value}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Leave)
    condition = scope_condition(ctx, Leave)
    return stmt.where(condition) if condition is not None else stmt


def list_leaves(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str | None = None,
    leave_type: str | None = None,
    applicant_id: int | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if status:
        stmt = stmt.where(Leave.status == status)
    if leave_type:
        stmt = stmt.where(Leave.type == leave_type)
    if applicant_id:
        stmt = stmt.where(Leave.applicant_id == applicant_id)
    stmt = stmt.order_by(Leave.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_leave(db: Session, ctx: ScopeContext, leave_id: int) -> Leave:
    leave = db.execute(_base_query(ctx).where(Leave.id == leave_id)).scalar_one_or_none()
    if leave is None:
        raise NotFoundError("请假单不存在或无权访问")
    return leave


def _validate_dates(start: datetime, end: datetime, duration: Decimal) -> None:
    if end <= start:
        raise BusinessRuleError("结束时间必须晚于开始时间")
    span_days = Decimal(str((end - start).total_seconds() / 86400))
    if duration <= 0:
        raise BusinessRuleError("请假时长必须大于 0")
    if duration > span_days + Decimal("1"):
        raise BusinessRuleError("请假时长与起止时间不匹配")
    if duration > 365:
        raise BusinessRuleError("单次请假不得超过 365 天")
    if (duration * 2) % 1 != 0:
        raise BusinessRuleError("请假时长最小精度为 0.5 天")


def _check_overlap(
    db: Session, applicant_id: int, start: datetime, end: datetime, exclude_id: int | None = None
) -> None:
    stmt = select(func.count(Leave.id)).where(
        Leave.applicant_id == applicant_id,
        Leave.status.in_([LeaveStatus.RUNNING.value, LeaveStatus.APPROVED.value]),
        Leave.start_time < end,
        Leave.end_time > start,
    )
    if exclude_id:
        stmt = stmt.where(Leave.id != exclude_id)
    if int(db.execute(stmt).scalar_one()) > 0:
        raise BusinessRuleError("该时间段已有请假记录，请勿重复申请")


def _balance(db: Session, user: User, leave_type: str, year: int) -> LeaveBalance | None:
    return db.execute(
        select(LeaveBalance).where(
            LeaveBalance.company_id == user.company_id,
            LeaveBalance.user_id == user.id,
            LeaveBalance.year == year,
            LeaveBalance.type == leave_type,
        )
    ).scalar_one_or_none()


def create_leave(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Leave:
    leave_type = str(payload.get("type") or "ANNUAL")
    if leave_type not in LEAVE_TYPES:
        raise BusinessRuleError("请假类型非法")
    start = payload.get("start_time")
    end = payload.get("end_time")
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise BusinessRuleError("请填写正确的起止时间")
    duration = to_decimal(payload.get("duration"), field_name="请假时长")
    _validate_dates(start, end, duration)
    _check_overlap(db, user.id, start, end)
    handover = payload.get("handover_user_id")
    if handover:
        target = db.get(User, int(handover))
        if target is None or target.company_id != user.company_id:
            raise BusinessRuleError("交接人不存在")
        if target.id == user.id:
            raise BusinessRuleError("交接人不能是本人")

    if leave_type in BALANCE_TYPES:
        balance = _balance(db, user, leave_type, start.year)
        if balance is None or Decimal(str(balance.remain)) < duration:
            remain = Decimal(str(balance.remain)) if balance else Decimal("0")
            raise BusinessRuleError(f"可用假期余额不足（剩余 {remain} 天）")

    leave = Leave(
        company_id=user.company_id,
        dept_id=user.dept_id,
        project_id=payload.get("project_id"),
        creator_id=user.id,
        applicant_id=user.id,
        no=next_no(db, "LV", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        type=leave_type,
        start_time=start,
        end_time=end,
        duration=duration,
        reason=(payload.get("reason") or "")[:1000],
        handover_user_id=int(handover) if handover else None,
        status=LeaveStatus.DRAFT.value,
    )
    db.add(leave)
    db.flush()
    write_audit(db, user=user, action="CREATE_LEAVE", target_type="LEAVE", target_id=leave.id, after=snapshot(leave))
    return leave


def update_leave(db: Session, user: User, ctx: ScopeContext, leave_id: int, payload: dict[str, Any]) -> Leave:
    leave = get_leave(db, ctx, leave_id)
    if leave.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能修改本人请假单")
    if leave.status not in {LeaveStatus.DRAFT.value, LeaveStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许修改")
    expected = payload.get("version")
    if expected is not None and int(expected) != leave.version:
        raise ConflictError("请假单已被修改，请刷新后重试")
    before = snapshot(leave)
    leave_type = str(payload.get("type") or leave.type)
    if leave_type not in LEAVE_TYPES:
        raise BusinessRuleError("请假类型非法")
    start = payload.get("start_time") or leave.start_time
    end = payload.get("end_time") or leave.end_time
    duration = to_decimal(payload.get("duration", leave.duration), field_name="请假时长")
    _validate_dates(start, end, duration)
    _check_overlap(db, leave.applicant_id, start, end, exclude_id=leave.id)
    if leave_type in BALANCE_TYPES:
        balance = _balance(db, user, leave_type, start.year)
        if balance is None or Decimal(str(balance.remain)) < duration:
            raise BusinessRuleError("可用假期余额不足")
    leave.type = leave_type
    leave.start_time = start
    leave.end_time = end
    leave.duration = duration
    if payload.get("reason") is not None:
        leave.reason = str(payload["reason"])[:1000]
    if payload.get("handover_user_id") is not None:
        leave.handover_user_id = int(payload["handover_user_id"]) if payload["handover_user_id"] else None
    leave.version = int(leave.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_LEAVE",
        target_type="LEAVE",
        target_id=leave.id,
        before=before,
        after=snapshot(leave),
    )
    return leave


def submit_leave(db: Session, user: User, ctx: ScopeContext, leave_id: int) -> Leave:
    leave = get_leave(db, ctx, leave_id)
    if leave.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能提交本人请假单")
    if leave.status not in {LeaveStatus.DRAFT.value, LeaveStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许提交")
    _check_overlap(db, leave.applicant_id, leave.start_time, leave.end_time, exclude_id=leave.id)
    if leave.type in BALANCE_TYPES:
        balance = _balance(db, user, leave.type, leave.start_time.year)
        if balance is None or Decimal(str(balance.remain)) < Decimal(str(leave.duration)):
            raise BusinessRuleError("可用假期余额不足")
    claim_version(
        db,
        Leave,
        leave,
        allowed_status={LeaveStatus.DRAFT.value, LeaveStatus.REJECTED.value},
    )
    leave.status = LeaveStatus.RUNNING.value
    leave.submitted_at = now()
    leave.workflow_version = int(leave.workflow_version or 0) + 1
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=leave.dept_id,
        project_id=leave.project_id,
        initiator=user,
        def_code="LEAVE",
        biz_type="LEAVE",
        biz_id=leave.id,
        title=f"请假单 {leave.no}（{leave.duration} 天）",
        context={
            "days": str(leave.duration),
            "type": leave.type,
            "no": leave.no,
            "project_id": leave.project_id,
        },
        version=leave.workflow_version,
    )
    leave.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="SUBMIT_LEAVE",
        target_type="LEAVE",
        target_id=leave.id,
        after={"instance_id": instance.id, "duration": str(leave.duration)},
    )
    return leave


def cancel_leave(db: Session, user: User, ctx: ScopeContext, leave_id: int) -> Leave:
    leave = get_leave(db, ctx, leave_id)
    if leave.applicant_id != user.id and not user.is_super:
        raise BusinessRuleError("只能取消本人请假单")
    if leave.status not in {LeaveStatus.DRAFT.value, LeaveStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许取消")
    leave.status = LeaveStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_LEAVE", target_type="LEAVE", target_id=leave.id)
    return leave


def withdraw_leave(db: Session, user: User, ctx: ScopeContext, leave_id: int) -> Leave:
    leave = get_leave(db, ctx, leave_id)
    if not leave.instance_id:
        raise BusinessRuleError("该请假单尚未提交审批")
    engine.act(db, user=user, instance_id=leave.instance_id, action="WITHDRAW")
    db.refresh(leave)
    return leave


def leave_balance_list(db: Session, user: User, year: int | None = None) -> list[LeaveBalance]:
    year = year or now().year
    return list(
        db.execute(
            select(LeaveBalance)
            .where(
                LeaveBalance.company_id == user.company_id,
                LeaveBalance.user_id == user.id,
                LeaveBalance.year == year,
            )
            .order_by(LeaveBalance.type)
        )
        .scalars()
        .all()
    )


def on_approved(db: Session, instance: WorkflowInstance) -> None:
    leave = db.get(Leave, instance.biz_id)
    if leave is None:
        raise BusinessRuleError("请假单不存在")
    if leave.status == LeaveStatus.APPROVED.value:
        return
    if leave.type in BALANCE_TYPES:
        balance = db.execute(
            select(LeaveBalance)
            .where(
                LeaveBalance.company_id == leave.company_id,
                LeaveBalance.user_id == leave.applicant_id,
                LeaveBalance.year == leave.start_time.year,
                LeaveBalance.type == leave.type,
            )
            .with_for_update()
        ).scalar_one_or_none()
        duration = Decimal(str(leave.duration))
        if balance is None or Decimal(str(balance.remain)) < duration:
            raise BusinessRuleError("假期余额不足，无法完成审批归档")
        balance.used = Decimal(str(balance.used)) + duration
        balance.remain = Decimal(str(balance.remain)) - duration
    leave.status = LeaveStatus.APPROVED.value
    db.flush()
    handover = db.get(User, leave.handover_user_id) if leave.handover_user_id else None
    notify_with_email(
        db,
        company_id=leave.company_id,
        user_ids=[leave.applicant_id] + ([handover.id] if handover else []),
        title=f"请假审批通过：{leave.no}",
        content=f"请假 {leave.start_time:%Y-%m-%d %H:%M} 至 {leave.end_time:%Y-%m-%d %H:%M} 已批准。",
        type="APPROVAL",
        biz_type="LEAVE",
        biz_id=leave.id,
        link=f"/approvals/leaves/{leave.id}",
        email=False,
    )
    write_audit(
        db,
        user=None,
        action="LEAVE_APPROVED",
        target_type="LEAVE",
        target_id=leave.id,
        company_id=leave.company_id,
        after={"duration": str(leave.duration)},
    )


def on_rejected(db: Session, instance: WorkflowInstance) -> None:
    leave = db.get(Leave, instance.biz_id)
    if leave and leave.status == LeaveStatus.RUNNING.value:
        leave.status = LeaveStatus.REJECTED.value
        db.flush()


def on_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    leave = db.get(Leave, instance.biz_id)
    if leave and leave.status == LeaveStatus.RUNNING.value:
        leave.status = LeaveStatus.DRAFT.value
        db.flush()
