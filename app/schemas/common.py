"""请求 DTO。

服务层接收 ``dict`` 并做二次业务校验，这里负责类型、范围与必填的基础校验，
同时允许扩展字段（extra=allow）以兼容流程上下文。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


# ------------------------------------------------------------------ 认证
class LoginIn(InModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    captcha_id: str = Field(min_length=4, max_length=128)
    captcha_code: str = Field(min_length=1, max_length=8)


class RefreshIn(InModel):
    refresh_token: str = Field(min_length=10)


class LogoutIn(InModel):
    refresh_token: str | None = None


class ChangePasswordIn(InModel):
    old_password: str = Field(min_length=6, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)


class ResetPasswordIn(InModel):
    new_password: str = Field(min_length=8, max_length=64)


# ------------------------------------------------------------------ 审批
class ExpenseItemIn(InModel):
    category: str
    amount: Decimal
    occur_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    file_id: int | None = None


class ExpenseIn(InModel):
    project_id: int
    type: str = "OTHER"
    currency: str = "CNY"
    items: list[ExpenseItemIn] = Field(min_length=1, max_length=100)
    invoices_file_ids: list[int] = Field(default_factory=list)
    payee: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=1000)
    version: int | None = None


class ExpenseUpdateIn(InModel):
    project_id: int | None = None
    type: str | None = None
    currency: str | None = None
    items: list[ExpenseItemIn] | None = None
    invoices_file_ids: list[int] | None = None
    payee: str | None = None
    remark: str | None = None
    version: int | None = None


class LeaveIn(InModel):
    type: str = "ANNUAL"
    start_time: datetime
    end_time: datetime
    duration: Decimal
    reason: str = Field(default="", max_length=1000)
    handover_user_id: int | None = None
    project_id: int | None = None
    version: int | None = None


class LeaveUpdateIn(InModel):
    type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration: Decimal | None = None
    reason: str | None = None
    handover_user_id: int | None = None
    project_id: int | None = None
    version: int | None = None


class DocumentIn(InModel):
    title: str = Field(min_length=1, max_length=255)
    category: str = "INSTITUTION"
    secret_level: str = "INTERNAL"
    content: str | None = None
    file_id: int | None = None
    effect_date: date | None = None
    project_id: int | None = None
    version: int | None = None


class DocumentUpdateIn(InModel):
    title: str | None = None
    category: str | None = None
    secret_level: str | None = None
    content: str | None = None
    file_id: int | None = None
    effect_date: date | None = None
    project_id: int | None = None
    version: int | None = None


class WorkflowActionIn(InModel):
    action: str
    task_id: int | None = None
    comment: str | None = Field(default=None, max_length=1000)
    target_user_id: int | None = None
    target_user_ids: list[int] | None = None
    back_to: str = "INITIATOR"
    mode: str = "ANY"
    cc_user_ids: list[int] | None = None
    attachments: list[int] | None = None


class WorkflowDefinitionIn(InModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    nodes_json: dict[str, Any]
    enabled: bool = True
    remark: str | None = None


# ------------------------------------------------------------------ 项目
class ProjectIn(InModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = "OTHER"
    customer_id: int | None = None
    manager_id: int | None = None
    dept_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    budget_amount: Decimal = Decimal("0")
    contract_amount: Decimal = Decimal("0")
    secret_level: str = "INTERNAL"
    description: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class ProjectUpdateIn(InModel):
    name: str | None = None
    type: str | None = None
    customer_id: int | None = None
    manager_id: int | None = None
    dept_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    budget_amount: Decimal | None = None
    contract_amount: Decimal | None = None
    secret_level: str | None = None
    description: str | None = None
    version: int | None = None


class InitiationIn(InModel):
    project_id: int | None = None
    name: str | None = None
    type: str = "OTHER"
    manager_id: int | None = None
    budget_amount: Decimal | None = None
    contract_amount: Decimal | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    background: str = Field(default="", max_length=2000)
    goal: str = Field(default="", max_length=2000)
    estimate_cost: Decimal = Decimal("0")
    estimate_income: Decimal = Decimal("0")
    risk_desc: str | None = Field(default=None, max_length=2000)
    submit: bool = True


class WBSIn(InModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None
    code: str | None = None
    owner_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    progress: int = Field(default=0, ge=0, le=100)
    is_milestone: bool = False
    sort: int = 0


class WBSUpdateIn(InModel):
    name: str | None = None
    parent_id: int | None = None
    owner_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    is_milestone: bool | None = None
    sort: int | None = None


class TaskIn(InModel):
    name: str = Field(min_length=1, max_length=255)
    wbs_id: int | None = None
    owner_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    progress: int = Field(default=0, ge=0, le=100)
    status: str = "TODO"
    priority: str = "MEDIUM"
    estimate_hours: Decimal = Decimal("0")


class TaskUpdateIn(InModel):
    name: str | None = None
    wbs_id: int | None = None
    owner_id: int | None = None
    plan_start: date | None = None
    plan_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    status: str | None = None
    priority: str | None = None
    estimate_hours: Decimal | None = None
    actual_hours: Decimal | None = None
    version: int | None = None


class MilestoneIn(InModel):
    name: str = Field(min_length=1, max_length=255)
    plan_date: date | None = None


class MilestoneCompleteIn(InModel):
    actual_date: date | None = None
    acceptance_file_id: int | None = None


class ChangeIn(InModel):
    type: str
    after: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)
    submit: bool = True


class AcceptanceIn(InModel):
    acceptor: str | None = Field(default=None, max_length=128)
    result: str = "PASS"
    sign_file_id: int | None = None
    accept_date: date | None = None
    accept_amount: Decimal = Decimal("0")
    remark: str | None = Field(default=None, max_length=1000)
    submit: bool = True


class IssueIn(InModel):
    title: str = Field(min_length=1, max_length=255)
    level: str = "MEDIUM"
    owner_id: int | None = None
    due_date: date | None = None
    status: str = "OPEN"
    solution: str | None = Field(default=None, max_length=2000)


class IssueUpdateIn(InModel):
    title: str | None = None
    level: str | None = None
    owner_id: int | None = None
    due_date: date | None = None
    status: str | None = None
    solution: str | None = None


class ProjectReportIn(InModel):
    type: str = "WEEKLY"
    period: str = Field(min_length=4, max_length=16)
    progress: int = Field(default=0, ge=0, le=100)
    content: str = ""
    issues: str | None = None
    next_plan: str | None = None


class MemberIn(InModel):
    user_id: int
    role: str = "MEMBER"


class ArchiveIn(InModel):
    doc_type: str = Field(min_length=1, max_length=64)
    file_id: int | None = None


class CloseProjectIn(InModel):
    force: bool = False
    reason: str | None = None


# ------------------------------------------------------------------ 供应商 / 合同
class ContactIn(InModel):
    name: str = Field(min_length=1, max_length=64)
    title: str | None = None
    phone: str | None = None
    email: str | None = None
    is_default: bool = False


class BankIn(InModel):
    bank_name: str = Field(min_length=1, max_length=128)
    account_no: str = Field(min_length=4, max_length=64)
    account_name: str = Field(min_length=1, max_length=128)
    is_default: bool = False


class LicenseIn(InModel):
    name: str = Field(min_length=1, max_length=128)
    no: str | None = None
    file_id: int | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class VendorIn(InModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = "SERVICE"
    tax_no: str | None = None
    owner_user_id: int | None = None
    intro: str | None = Field(default=None, max_length=2000)
    level: str | None = None
    contacts: list[ContactIn] = Field(default_factory=list)
    banks: list[BankIn] = Field(default_factory=list)
    licenses: list[LicenseIn] = Field(default_factory=list)
    submit: bool = True
    version: int | None = None


class VendorUpdateIn(InModel):
    name: str | None = None
    type: str | None = None
    tax_no: str | None = None
    owner_user_id: int | None = None
    intro: str | None = None
    level: str | None = None
    version: int | None = None


class BlacklistIn(InModel):
    reason: str = Field(min_length=3, max_length=500)


class ContractIn(InModel):
    vendor_id: int
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    amount: Decimal = Decimal("0")
    currency: str = "CNY"
    sign_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    pay_terms: list[dict[str, Any]] = Field(default_factory=list)
    file_id: int | None = None
    remark: str | None = None
    activate: bool = False
    version: int | None = None


class ContractStatusIn(InModel):
    status: str
    reason: str | None = None


class BindProjectIn(InModel):
    project_id: int
    contract_id: int | None = None
    role: str = "分包商"
    contract_amount: Decimal = Decimal("0")


class EvaluationIn(InModel):
    project_id: int | None = None
    quality_score: Decimal
    schedule_score: Decimal
    cooperate_score: Decimal
    comment: str | None = Field(default=None, max_length=1000)
    eval_date: date | None = None


# ------------------------------------------------------------------ 财务
class PaymentIn(InModel):
    project_id: int
    vendor_id: int | None = None
    contract_id: int | None = None
    expense_id: int | None = None
    amount: Decimal
    currency: str = "CNY"
    pay_date: date | None = None
    method: str = "BANK"
    account_code: str = "5401"
    remark: str | None = Field(default=None, max_length=1000)
    installments: list[dict[str, Any]] = Field(default_factory=list)
    version: int | None = None


class PayIn(InModel):
    pay_date: date | None = None


class ReceiptIn(InModel):
    project_id: int
    customer_id: int | None = None
    contract_id: int | None = None
    amount: Decimal
    currency: str = "CNY"
    receipt_date: date | None = None
    method: str = "BANK"
    remark: str | None = Field(default=None, max_length=1000)


class RevenueIn(InModel):
    project_id: int
    customer_id: int | None = None
    contract_id: int | None = None
    amount: Decimal
    currency: str = "CNY"
    confirm_date: date | None = None
    remark: str | None = Field(default=None, max_length=1000)
    confirm: bool = True


class BudgetIn(InModel):
    project_id: int
    account_code: str = Field(min_length=1, max_length=32)
    year: int = Field(ge=2000, le=2100)
    amount: Decimal
    remark: str | None = Field(default=None, max_length=255)
    version: int | None = None


class PeriodIn(InModel):
    period: str = Field(min_length=7, max_length=7)
    remark: str | None = None


class ReverseIn(InModel):
    reason: str = Field(min_length=2, max_length=500)


# ------------------------------------------------------------------ IAM
class UserIn(InModel):
    username: str = Field(min_length=2, max_length=64)
    real_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=64)
    dept_id: int | None = None
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    role_ids: list[int] = Field(default_factory=list)
    status: str = "ACTIVE"
    first_login: bool = True


class UserUpdateIn(InModel):
    real_name: str | None = None
    dept_id: int | None = None
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    role_ids: list[int] | None = None
    status: str | None = None
    version: int | None = None


class RoleIn(InModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    data_scope: str = "SELF"
    permission_ids: list[int] | None = None
    status: str = "ACTIVE"
    remark: str | None = None


class DeptIn(InModel):
    name: str = Field(min_length=1, max_length=128)
    code: str | None = None
    parent_id: int | None = None
    leader_user_id: int | None = None
    sort: int = 0
    status: str = "ACTIVE"


class DictIn(InModel):
    dict_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=128)
    sort: int = 0
    status: str = "ACTIVE"
    remark: str | None = None


class ConfigIn(InModel):
    value: Any
    description: str | None = None


class CustomerIn(InModel):
    name: str = Field(min_length=1, max_length=128)
    code: str | None = None
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    status: str = "ACTIVE"


# ------------------------------------------------------------------ 通知
class NotificationReadIn(InModel):
    ids: list[int] = Field(default_factory=list)
    all: bool = False


class ReportQuery(InModel):
    start: str | None = None
    end: str | None = None
    group_by: str | None = None
    project_id: int | None = None
    year: int | None = None
