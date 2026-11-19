from __future__ import annotations

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.core.scope import ScopeContext
from app.db.session import session_scope
from app.models.iam import Company
from app.services.common import users_by_role
from app.services.dashboard import license_alerts
from app.services.iam.notification import notify_with_email
from app.services.vendor.contract import contract_risks, mark_expired

logger = get_logger("eoms.tasks.vendor")


@celery_app.task(name="eoms.vendor.contract_expiry")
def contract_expiry(warning_days: int = 45) -> dict[str, int]:
    """合同到期/超付风险与供应商证照到期提醒，同时把过期合同置为 EXPIRED。"""
    expired = 0
    alerted = 0
    with session_scope() as db:
        expired = mark_expired(db)
        companies = db.execute(select(Company).where(Company.status == "ACTIVE")).scalars().all()
        for company in companies:
            recipients = {user.id for user in users_by_role(db, company.id, "ADMIN")}
            recipients.update(user.id for user in users_by_role(db, company.id, "PURCHASE"))
            if not recipients:
                continue

            seen_licenses: set[int] = set()
            for item in license_alerts(db, company.id, warning_days):
                if item["license_id"] in seen_licenses:
                    continue
                seen_licenses.add(item["license_id"])
                notify_with_email(
                    db,
                    company_id=company.id,
                    user_ids=sorted(recipients),
                    title=f"供应商证照到期提醒：{item['name']}",
                    content=item["message"],
                    type="ALERT",
                    biz_type="VENDOR",
                    biz_id=item["vendor_id"],
                    link=f"/vendors/{item['vendor_id']}?tab=licenses",
                    email=True,
                )
                alerted += 1

            seen_contracts: set[int] = set()
            ctx = ScopeContext(
                user_id=0,
                company_id=company.id,
                dept_id=None,
                is_super=True,
                scopes={"ALL"},
            )
            for risk in contract_risks(db, ctx, warning_days):
                if risk["contract_id"] in seen_contracts:
                    continue
                seen_contracts.add(risk["contract_id"])
                notify_with_email(
                    db,
                    company_id=company.id,
                    user_ids=sorted(recipients),
                    title=f"合同风险提醒：{risk['contract_no']}",
                    content=risk["message"],
                    type="ALERT",
                    biz_type="CONTRACT",
                    biz_id=risk["contract_id"],
                    link=f"/contracts/{risk['contract_id']}",
                    email=False,
                )
                alerted += 1
    logger.info("合同/证照到期扫描完成：过期=%s 提醒=%s", expired, alerted)
    return {"expired": expired, "alerted": alerted}
