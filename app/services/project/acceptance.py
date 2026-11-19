from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.scope import ScopeContext
from app.models.enums import AcceptanceResult
from app.models.iam import User
from app.models.project import Acceptance, Archive, Project
from app.models.workflow import WorkflowInstance
from app.services.common import ensure_files
from app.services.iam.audit import snapshot, write_audit
from app.services.iam.notification import notify_with_email
from app.services.project.project import get_project
from app.utils.datetime import to_date, today
from app.utils.money import to_decimal
from app.workflow import engine

RESULTS = {item.value for item in AcceptanceResult}


def list_acceptances(db: Session, ctx: ScopeContext, project_id: int) -> list[Acceptance]:
    get_project(db, ctx, project_id)
    return list(
        db.execute(select(Acceptance).where(Acceptance.project_id == project_id).order_by(Acceptance.id.desc()))
        .scalars()
        .all()
    )


def get_acceptance(db: Session, ctx: ScopeContext, acceptance_id: int) -> Acceptance:
    item = db.get(Acceptance, acceptance_id)
    if item is None:
        raise NotFoundError("验收单不存在")
    get_project(db, ctx, item.project_id)
    return item


def create_acceptance(
    db: Session, user: User, ctx: ScopeContext, project_id: int, payload: dict[str, Any]
) -> Acceptance:
    project = get_project(db, ctx, project_id)
    if project.status != "ACTIVE":
        raise BusinessRuleError("只有进行中的项目可提交验收")
    result = str(payload.get("result") or "PASS")
    if result not in RESULTS:
        raise BusinessRuleError("验收结果非法")
    acceptor = str(payload.get("acceptor") or "").strip()
    if not acceptor:
        raise BusinessRuleError("请填写验收人")
    file_id = payload.get("sign_file_id")
    if not file_id:
        raise BusinessRuleError("请上传验收签署文件")
    ensure_files(db, [int(file_id)], project.company_id)
    accept_amount = to_decimal(payload.get("accept_amount"), field_name="验收计收金额")
    if accept_amount < 0:
        raise BusinessRuleError("验收计收金额不能为负数")
    if result == "FAIL" and accept_amount > 0:
        raise BusinessRuleError("验收未通过不能确认计收金额")
    item = Acceptance(
        company_id=project.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        creator_id=user.id,
        applicant_id=user.id,
        acceptor=acceptor[:128],
        result=result,
        sign_file_id=int(file_id),
        accept_date=to_date(payload.get("accept_date")) or today(),
        accept_amount=accept_amount,
        remark=(payload.get("remark") or "")[:1000],
        status="RUNNING",
    )
    db.add(item)
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=project.dept_id,
        project_id=project.id,
        initiator=user,
        def_code="PROJECT_ACCEPTANCE",
        biz_type="PROJECT_ACCEPTANCE",
        biz_id=item.id,
        title=f"项目验收：{project.no} {project.name}",
        context={
            "amount": str(accept_amount),
            "type": result,
            "project_id": project.id,
            "project_no": project.no,
        },
    )
    item.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="CREATE_ACCEPTANCE",
        target_type="ACCEPTANCE",
        target_id=item.id,
        after=snapshot(item),
    )
    return item


def on_acceptance_approved(db: Session, instance: WorkflowInstance) -> None:
    item = db.get(Acceptance, instance.biz_id)
    if item is None:
        raise BusinessRuleError("验收单不存在")
    project = db.get(Project, item.project_id)
    if project is None:
        raise BusinessRuleError("项目不存在")
    item.status = "APPROVED"
    if item.result in {"PASS", "CONDITIONAL"}:
        project.stage = "CLOSE"
        if item.sign_file_id:
            exists = db.execute(
                select(Archive).where(
                    Archive.project_id == project.id,
                    Archive.doc_type == "ACCEPTANCE",
                    Archive.file_id == item.sign_file_id,
                )
            ).first()
            if not exists:
                db.add(
                    Archive(
                        company_id=project.company_id,
                        project_id=project.id,
                        doc_type="ACCEPTANCE",
                        file_id=item.sign_file_id,
                        archived_by=item.applicant_id,
                    )
                )
        from app.services.cost.revenue import auto_from_acceptance

        auto_from_acceptance(
            db,
            project_id=project.id,
            acceptance_id=item.id,
            amount=Decimal(str(item.accept_amount)),
            accept_date=item.accept_date,
        )
    db.flush()
    write_audit(
        db,
        user=None,
        action="ACCEPTANCE_APPROVED",
        target_type="ACCEPTANCE",
        target_id=item.id,
        company_id=project.company_id,
        after={"result": item.result, "amount": str(item.accept_amount)},
    )
    notify_with_email(
        db,
        company_id=project.company_id,
        user_ids=[project.manager_id, item.applicant_id],
        title=f"验收审批通过：{project.name}",
        content=f"验收结果：{item.result}，计收金额 {item.accept_amount} 元。",
        type="APPROVAL",
        biz_type="PROJECT_ACCEPTANCE",
        biz_id=item.id,
        link=f"/projects/{project.id}?tab=acceptance",
        email=True,
    )


def on_acceptance_rejected(db: Session, instance: WorkflowInstance) -> None:
    item = db.get(Acceptance, instance.biz_id)
    if item and item.status == "RUNNING":
        item.status = "REJECTED"
        db.flush()


def on_acceptance_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    item = db.get(Acceptance, instance.biz_id)
    if item and item.status == "RUNNING":
        item.status = "DRAFT"
        db.flush()
