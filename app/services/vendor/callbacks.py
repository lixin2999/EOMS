"""供应商域审批回调：准入。"""

from __future__ import annotations

from app.services.vendor import vendor
from app.workflow.callbacks import register


@register("VENDOR_ONBOARD", "approved")
def _vendor_approved(db, instance):
    vendor.on_vendor_approved(db, instance)


@register("VENDOR_ONBOARD", "rejected")
def _vendor_rejected(db, instance):
    vendor.on_vendor_rejected(db, instance)
