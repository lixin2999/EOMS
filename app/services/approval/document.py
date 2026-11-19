from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.scope import ScopeContext, scope_condition
from app.models.approval import Document
from app.models.enums import DocumentCategory, DocumentStatus, SecretLevel
from app.models.iam import User
from app.models.workflow import WorkflowInstance
from app.services.common import company_code, ensure_files
from app.services.iam.audit import snapshot, write_audit
from app.utils.datetime import now, to_date
from app.utils.numbering import next_no
from app.workflow import engine

DOC_CATEGORIES = {item.value for item in DocumentCategory}
SECRET_LEVELS = {item.value for item in SecretLevel}
FILE_REQUIRED_CATEGORIES = {DocumentCategory.SEAL.value, DocumentCategory.CONTRACT.value}


def _base_query(ctx: ScopeContext) -> Select:
    stmt = select(Document)
    condition = scope_condition(ctx, Document)
    return stmt.where(condition) if condition is not None else stmt


def list_documents(
    db: Session,
    ctx: ScopeContext,
    params: PageParams,
    *,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = _base_query(ctx)
    if status:
        stmt = stmt.where(Document.status == status)
    if category:
        stmt = stmt.where(Document.category == category)
    if keyword:
        stmt = stmt.where(or_(Document.title.like(f"%{keyword}%"), Document.doc_no.like(f"%{keyword}%")))
    stmt = stmt.order_by(Document.id.desc())
    total = int(db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one())
    items = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_document(db: Session, ctx: ScopeContext, doc_id: int) -> Document:
    doc = db.execute(_base_query(ctx).where(Document.id == doc_id)).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("文件不存在或无权访问")
    return doc


def create_document(db: Session, user: User, ctx: ScopeContext, payload: dict[str, Any]) -> Document:
    category = str(payload.get("category") or "INSTITUTION")
    secret_level = str(payload.get("secret_level") or "INTERNAL")
    if category not in DOC_CATEGORIES:
        raise BusinessRuleError("文件类别非法")
    if secret_level not in SECRET_LEVELS:
        raise BusinessRuleError("密级非法")
    file_id = payload.get("file_id")
    if file_id:
        ensure_files(db, [int(file_id)], user.company_id)
    doc = Document(
        company_id=user.company_id,
        dept_id=user.dept_id,
        project_id=payload.get("project_id"),
        creator_id=user.id,
        doc_no=next_no(db, "DOC", company_code=company_code(db, user.company_id), period=now().strftime("%Y%m")),
        title=str(payload.get("title") or "").strip()[:255],
        category=category,
        secret_level=secret_level,
        content=(payload.get("content") or "")[:20000],
        file_id=int(file_id) if file_id else None,
        effect_date=to_date(payload.get("effect_date")),
        status=DocumentStatus.DRAFT.value,
    )
    if not doc.title:
        raise BusinessRuleError("文件标题不能为空")
    db.add(doc)
    db.flush()
    write_audit(db, user=user, action="CREATE_DOCUMENT", target_type="DOCUMENT", target_id=doc.id, after=snapshot(doc))
    return doc


def update_document(db: Session, user: User, ctx: ScopeContext, doc_id: int, payload: dict[str, Any]) -> Document:
    doc = get_document(db, ctx, doc_id)
    if doc.creator_id != user.id and not user.is_super:
        raise BusinessRuleError("只能修改本人发起的文件")
    if doc.status not in {DocumentStatus.DRAFT.value, DocumentStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许修改")
    expected = payload.get("version")
    if expected is not None and int(expected) != doc.version:
        raise ConflictError("文件已被修改，请刷新后重试")
    before = snapshot(doc)
    if payload.get("title") is not None:
        title = str(payload["title"]).strip()
        if not title:
            raise BusinessRuleError("文件标题不能为空")
        doc.title = title[:255]
    if payload.get("category") is not None:
        if payload["category"] not in DOC_CATEGORIES:
            raise BusinessRuleError("文件类别非法")
        doc.category = payload["category"]
    if payload.get("secret_level") is not None:
        if payload["secret_level"] not in SECRET_LEVELS:
            raise BusinessRuleError("密级非法")
        doc.secret_level = payload["secret_level"]
    if payload.get("content") is not None:
        doc.content = str(payload["content"])[:20000]
    if payload.get("file_id") is not None:
        file_id = int(payload["file_id"]) if payload["file_id"] else None
        if file_id:
            ensure_files(db, [file_id], user.company_id)
        doc.file_id = file_id
    if payload.get("effect_date") is not None:
        doc.effect_date = to_date(payload["effect_date"])
    doc.version = int(doc.version or 1) + 1
    db.flush()
    write_audit(
        db,
        user=user,
        action="UPDATE_DOCUMENT",
        target_type="DOCUMENT",
        target_id=doc.id,
        before=before,
        after=snapshot(doc),
    )
    return doc


def submit_document(db: Session, user: User, ctx: ScopeContext, doc_id: int) -> Document:
    doc = get_document(db, ctx, doc_id)
    if doc.creator_id != user.id and not user.is_super:
        raise BusinessRuleError("只能提交本人发起的文件")
    if doc.status not in {DocumentStatus.DRAFT.value, DocumentStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许提交")
    if not (doc.content or doc.file_id):
        raise BusinessRuleError("请填写文件内容或上传附件")
    if doc.category in FILE_REQUIRED_CATEGORIES and not doc.file_id:
        raise BusinessRuleError("用印/合同类文件必须上传附件")
    if doc.file_id:
        ensure_files(db, [doc.file_id], user.company_id)
    doc.status = DocumentStatus.RUNNING.value
    doc.submitted_at = now()
    doc.workflow_version = int(doc.workflow_version or 0) + 1
    doc.version = int(doc.version or 1) + 1
    db.flush()
    instance = engine.start_workflow(
        db,
        company_id=user.company_id,
        dept_id=doc.dept_id,
        project_id=doc.project_id,
        initiator=user,
        def_code="DOCUMENT",
        biz_type="DOCUMENT",
        biz_id=doc.id,
        title=f"文件审批 {doc.doc_no}：{doc.title}",
        context={
            "category": doc.category,
            "secret_level": doc.secret_level,
            "type": doc.category,
            "amount": "0",
        },
        version=doc.workflow_version,
    )
    doc.instance_id = instance.id
    db.flush()
    write_audit(
        db,
        user=user,
        action="SUBMIT_DOCUMENT",
        target_type="DOCUMENT",
        target_id=doc.id,
        after={"instance_id": instance.id},
    )
    return doc


def cancel_document(db: Session, user: User, ctx: ScopeContext, doc_id: int) -> Document:
    doc = get_document(db, ctx, doc_id)
    if doc.creator_id != user.id and not user.is_super:
        raise BusinessRuleError("只能取消本人发起的文件")
    if doc.status not in {DocumentStatus.DRAFT.value, DocumentStatus.REJECTED.value}:
        raise BusinessRuleError("当前状态不允许取消")
    doc.status = DocumentStatus.CANCELED.value
    db.flush()
    write_audit(db, user=user, action="CANCEL_DOCUMENT", target_type="DOCUMENT", target_id=doc.id)
    return doc


def withdraw_document(db: Session, user: User, ctx: ScopeContext, doc_id: int) -> Document:
    doc = get_document(db, ctx, doc_id)
    if not doc.instance_id:
        raise BusinessRuleError("该文件尚未提交审批")
    engine.act(db, user=user, instance_id=doc.instance_id, action="WITHDRAW")
    db.refresh(doc)
    return doc


def on_approved(db: Session, instance: WorkflowInstance) -> None:
    doc = db.get(Document, instance.biz_id)
    if doc is None:
        raise BusinessRuleError("文件不存在")
    doc.status = DocumentStatus.APPROVED.value
    db.flush()
    write_audit(
        db,
        user=None,
        action="DOCUMENT_APPROVED",
        target_type="DOCUMENT",
        target_id=doc.id,
        company_id=doc.company_id,
    )


def on_rejected(db: Session, instance: WorkflowInstance) -> None:
    doc = db.get(Document, instance.biz_id)
    if doc and doc.status == DocumentStatus.RUNNING.value:
        doc.status = DocumentStatus.REJECTED.value
        db.flush()


def on_withdrawn(db: Session, instance: WorkflowInstance) -> None:
    doc = db.get(Document, instance.biz_id)
    if doc and doc.status == DocumentStatus.RUNNING.value:
        doc.status = DocumentStatus.DRAFT.value
        db.flush()
