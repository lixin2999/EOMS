"""审批业务回调注册：报销 / 请假 / 文件。

回调只做业务状态流转与成本归集，异常向上抛出由请求事务统一回滚，
保证「审批状态」与「业务数据」在本地事务内强一致。
"""

from __future__ import annotations

from app.services.approval import document, expense, leave
from app.workflow.callbacks import register


@register("EXPENSE", "approved")
def _expense_approved(db, instance):
    expense.on_approved(db, instance)


@register("EXPENSE", "rejected")
def _expense_rejected(db, instance):
    expense.on_rejected(db, instance)


@register("EXPENSE", "withdrawn")
def _expense_withdrawn(db, instance):
    expense.on_withdrawn(db, instance)


@register("LEAVE", "approved")
def _leave_approved(db, instance):
    leave.on_approved(db, instance)


@register("LEAVE", "rejected")
def _leave_rejected(db, instance):
    leave.on_rejected(db, instance)


@register("LEAVE", "withdrawn")
def _leave_withdrawn(db, instance):
    leave.on_withdrawn(db, instance)


@register("DOCUMENT", "approved")
def _document_approved(db, instance):
    document.on_approved(db, instance)


@register("DOCUMENT", "rejected")
def _document_rejected(db, instance):
    document.on_rejected(db, instance)


@register("DOCUMENT", "withdrawn")
def _document_withdrawn(db, instance):
    document.on_withdrawn(db, instance)
