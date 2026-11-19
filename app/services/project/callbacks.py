"""项目域审批回调：立项 / 变更 / 验收。"""

from __future__ import annotations

from app.services.project import acceptance, change, project
from app.workflow.callbacks import register


@register("PROJECT_INITIATION", "approved")
def _initiation_approved(db, instance):
    project.on_initiation_approved(db, instance)


@register("PROJECT_INITIATION", "rejected")
def _initiation_rejected(db, instance):
    project.on_initiation_rejected(db, instance)


@register("PROJECT_INITIATION", "withdrawn")
def _initiation_withdrawn(db, instance):
    project.on_initiation_withdrawn(db, instance)


@register("PROJECT_CHANGE", "approved")
def _change_approved(db, instance):
    change.on_change_approved(db, instance)


@register("PROJECT_CHANGE", "rejected")
def _change_rejected(db, instance):
    change.on_change_rejected(db, instance)


@register("PROJECT_CHANGE", "withdrawn")
def _change_withdrawn(db, instance):
    change.on_change_withdrawn(db, instance)


@register("PROJECT_ACCEPTANCE", "approved")
def _acceptance_approved(db, instance):
    acceptance.on_acceptance_approved(db, instance)


@register("PROJECT_ACCEPTANCE", "rejected")
def _acceptance_rejected(db, instance):
    acceptance.on_acceptance_rejected(db, instance)


@register("PROJECT_ACCEPTANCE", "withdrawn")
def _acceptance_withdrawn(db, instance):
    acceptance.on_acceptance_withdrawn(db, instance)
