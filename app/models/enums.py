from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - 便于日志
        return self.value


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


class DataScope(StrEnum):
    ALL = "ALL"
    COMPANY = "COMPANY"
    DEPT = "DEPT"
    DEPT_TREE = "DEPT_TREE"
    PROJECT = "PROJECT"
    SELF = "SELF"


class PermissionType(StrEnum):
    MENU = "menu"
    API = "api"
    BUTTON = "button"


class WorkflowStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


class WorkflowTaskStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TRANSFERRED = "TRANSFERRED"
    SKIPPED = "SKIPPED"


class WorkflowAction(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    TRANSFER = "TRANSFER"
    ADD_SIGN = "ADD_SIGN"
    WITHDRAW = "WITHDRAW"
    URGE = "URGE"
    CC = "CC"


class NodeType(StrEnum):
    START = "START"
    APPROVAL = "APPROVAL"
    CC = "CC"
    END = "END"


class AssigneeMode(StrEnum):
    ANY = "ANY"
    ALL = "ALL"


class ExpenseStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    VERIFIED = "VERIFIED"
    PAID = "PAID"
    ARCHIVED = "ARCHIVED"
    CANCELED = "CANCELED"


class ExpenseType(StrEnum):
    TRAVEL = "TRAVEL"
    ENTERTAIN = "ENTERTAIN"
    OFFICE = "OFFICE"
    SUBCONTRACT = "SUBCONTRACT"
    MATERIAL = "MATERIAL"
    OTHER = "OTHER"


class LeaveType(StrEnum):
    ANNUAL = "ANNUAL"
    PERSONAL = "PERSONAL"
    SICK = "SICK"
    COMP = "COMP"


class LeaveStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    CANCELED = "CANCELED"


class DocumentCategory(StrEnum):
    INSTITUTION = "INSTITUTION"
    DISPATCH = "DISPATCH"
    SEAL = "SEAL"
    CONTRACT = "CONTRACT"


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    CANCELED = "CANCELED"


class SecretLevel(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SECRET = "SECRET"


class ProjectStage(StrEnum):
    LAUNCH = "LAUNCH"
    PLAN = "PLAN"
    PLAN_CONFIRMED = "PLAN_CONFIRMED"
    EXECUTE = "EXECUTE"
    CLOSE = "CLOSE"
    ARCHIVED = "ARCHIVED"


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    CANCELED = "CANCELED"
    ARCHIVED = "ARCHIVED"


class ProjectType(StrEnum):
    CONSTRUCTION = "CONSTRUCTION"
    SERVICE = "SERVICE"
    PRODUCT = "PRODUCT"
    OTHER = "OTHER"


class ProjectMemberRole(StrEnum):
    PM = "PM"
    MEMBER = "MEMBER"
    OBSERVER = "OBSERVER"


class TaskFlowStatus(StrEnum):
    TODO = "TODO"
    DOING = "DOING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class ChangeType(StrEnum):
    SCOPE = "SCOPE"
    SCHEDULE = "SCHEDULE"
    BUDGET = "BUDGET"


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    CLOSED = "CLOSED"


class AcceptanceResult(StrEnum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


class VendorStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLACKLIST = "BLACKLIST"


class VendorType(StrEnum):
    SUBCONTRACT = "SUBCONTRACT"
    MATERIAL = "MATERIAL"
    SERVICE = "SERVICE"
    LEASE = "LEASE"


class VendorLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class BizType(StrEnum):
    RECEIVABLE = "RECEIVABLE"
    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    EXPENSE = "EXPENSE"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELED = "CANCELED"


class ReceiptStatus(StrEnum):
    REGISTERED = "REGISTERED"
    CANCELED = "CANCELED"


class RevenueStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELED = "CANCELED"


class PeriodStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    COST = "COST"
    EXPENSE = "EXPENSE"


class NotificationType(StrEnum):
    APPROVAL = "APPROVAL"
    ALERT = "ALERT"
    SYSTEM = "SYSTEM"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class ReportCode(StrEnum):
    OVERVIEW = "OVERVIEW"
    REVENUE = "REVENUE"
    CASHFLOW = "CASHFLOW"
    PROFIT = "PROFIT"
    PROJECT_PNL = "PROJECT_PNL"
    VENDOR_SPEND = "VENDOR_SPEND"
    APPROVAL_EFFICIENCY = "APPROVAL_EFFICIENCY"


BIZ_TYPE_LABELS: dict[str, str] = {
    "EXPENSE": "报销审批",
    "LEAVE": "请假审批",
    "DOCUMENT": "文件审批",
    "PROJECT_INITIATION": "项目立项",
    "PROJECT_CHANGE": "项目变更",
    "PROJECT_ACCEPTANCE": "项目验收",
    "VENDOR_ONBOARD": "供应商准入",
}

CATEGORY_LABELS: dict[str, str] = {
    "TRAVEL": "差旅费",
    "ENTERTAIN": "招待费",
    "OFFICE": "办公费",
    "SUBCONTRACT": "分包费",
    "MATERIAL": "材料费",
    "OTHER": "其他",
    "ANNUAL": "年假",
    "PERSONAL": "事假",
    "SICK": "病假",
    "COMP": "调休",
}
