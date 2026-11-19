"""演示数据初始化脚本（幂等：默认检测到已有公司则跳过）。

用法：
    .venv\\Scripts\\python.exe scripts\\seed.py --reset
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: E402,F401  注册模型
from app.core.config import settings
from app.core.security import encrypt_text, hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.approval import Document, Expense, ExpenseItem, Leave, LeaveBalance
from app.models.finance import Account, Budget, Payment, Period, Receipt, RevenueConfirm
from app.models.iam import Company, Dept, Permission, Role, RolePermission, SysConfig, SysDict, User
from app.models.platform import Customer, Notification, Sequence
from app.models.project import (
    WBS,
    Acceptance,
    Change,
    Issue,
    Milestone,
    Project,
    ProjectMember,
    ProjectReport,
    Risk,
    Task,
)
from app.models.vendor import (
    Contract,
    Evaluation,
    Vendor,
    VendorBank,
    VendorContact,
    VendorLicense,
    VendorProject,
)
from app.models.workflow import WorkflowDefinition, WorkflowInstance, WorkflowRecord, WorkflowTask
from app.services.cost.ledger import record_cost
from app.services.report.pnl import generate_project_pnl
from app.services.report.service import generate_company_snapshots
from app.utils.datetime import now, today
from app.workflow.definitions import DEFAULT_DEFINITIONS

DEMO_PASSWORD = "Eoms@2026"

MENUS: list[tuple[str, str, str | None, str | None, str | None, str | None, int]] = [
    ("dashboard", "工作台", None, "/dashboard", "dashboard/index", "Odometer", 1),
    ("menu:approval", "审批中心", None, None, None, "Stamp", 10),
    ("approval:expense", "费用报销", "menu:approval", "/approvals/expenses", "approvals/Expenses", "Money", 11),
    ("approval:leave", "请假管理", "menu:approval", "/approvals/leaves", "approvals/Leaves", "Calendar", 12),
    ("approval:document", "文件审批", "menu:approval", "/approvals/documents", "approvals/Documents", "Document", 13),
    ("workflow:task", "我的待办", "menu:approval", "/approvals/tasks", "approvals/Tasks", "List", 14),
    ("workflow:instance", "流程实例", "menu:approval", "/approvals/instances", "approvals/Instances", "Connection", 15),
    ("project:view", "项目管理", None, "/projects", "projects/Index", "Folder", 20),
    ("vendor:view", "供应商管理", None, "/vendors", "vendors/Index", "OfficeBuilding", 30),
    ("contract:view", "合同管理", None, "/contracts", "contracts/Index", "Tickets", 40),
    ("menu:finance", "财务管理", None, None, None, "Coin", 50),
    ("finance:cost", "成本台账", "menu:finance", "/finance/costs", "finance/Costs", "DataLine", 51),
    ("finance:payment", "付款管理", "menu:finance", "/finance/payments", "finance/Payments", "Wallet", 52),
    ("finance:receipt", "收款管理", "menu:finance", "/finance/receipts", "finance/Receipts", "CreditCard", 53),
    ("finance:revenue", "计收确认", "menu:finance", "/finance/revenue", "finance/Revenue", "TrendCharts", 54),
    ("finance:budget", "预算管理", "menu:finance", "/finance/budgets", "finance/Budgets", "PieChart", 55),
    ("finance:period", "财务期间", "menu:finance", "/finance/periods", "finance/Periods", "Calendar", 56),
    ("report:view", "报表中心", None, "/reports", "reports/Index", "BarChart", 60),
    ("menu:system", "系统管理", None, None, None, "Setting", 90),
    ("system:user", "用户管理", "menu:system", "/system/users", "system/Users", "User", 91),
    ("system:role", "角色权限", "menu:system", "/system/roles", "system/Roles", "Key", 92),
    ("system:dept", "部门管理", "menu:system", "/system/depts", "system/Depts", "Grid", 93),
    ("workflow:definition", "流程配置", "menu:system", "/system/workflows", "system/Workflows", "Share", 94),
    ("system:audit", "审计日志", "menu:system", "/system/audit", "system/Audit", "Notebook", 95),
    ("system:config", "系统配置", "menu:system", "/system/config", "system/Config", "Tools", 96),
]

APIS: list[tuple[str, str]] = [
    ("project:create", "新建项目"),
    ("project:manage", "项目维护"),
    ("project:change", "项目变更"),
    ("project:acceptance", "项目验收"),
    ("project:close", "项目关闭"),
    ("project:force-close", "强制关闭项目"),
    ("vendor:create", "新建供应商"),
    ("vendor:manage", "供应商维护"),
    ("vendor:evaluate", "供应商评价"),
    ("vendor:sensitive", "查看敏感信息"),
    ("contract:manage", "合同维护"),
    ("finance:view", "财务数据查看"),
    ("report:export", "报表导出"),
    ("report:snapshot", "生成报表快照"),
    ("file:view", "文件查看"),
    ("file:upload", "文件上传"),
    ("file:delete", "文件删除"),
]

ROLE_SPECS: list[tuple[str, str, str, str]] = [
    ("ADMIN", "系统管理员", "ALL", "系统管理员：全部权限"),
    ("DIRECTOR", "董事", "ALL", "董事：全局查看与决策审批"),
    ("MANAGER", "总经理/经理", "DEPT_TREE", "经理：本部门及下级部门"),
    ("DEPT_LEADER", "部门负责人", "DEPT", "部门负责人：本部门"),
    ("FINANCE", "财务专员", "COMPANY", "财务：全公司财务数据"),
    ("PM", "项目经理", "PROJECT", "项目经理：所负责项目"),
    ("PURCHASE", "采购专员", "COMPANY", "采购：供应商与合同"),
    ("AUDITOR", "审计员", "COMPANY", "审计：全公司只读"),
    ("EMPLOYEE", "发起人（员工）", "SELF", "员工：仅本人数据"),
]

APPROVAL_ITEMS = ["approval:expense", "approval:leave", "approval:document"]
WORKFLOW_ITEMS = ["workflow:task", "workflow:instance"]
FINANCE_ITEMS = [
    "finance:cost",
    "finance:payment",
    "finance:receipt",
    "finance:revenue",
    "finance:budget",
    "finance:period",
]
FILE_ALL = ["file:view", "file:upload", "file:delete"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "DIRECTOR": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        *WORKFLOW_ITEMS,
        "project:view",
        "vendor:view",
        "contract:view",
        "menu:finance",
        *FINANCE_ITEMS,
        "report:view",
        "system:audit",
        *FILE_ALL,
        "project:create",
        "project:manage",
        "project:change",
        "project:acceptance",
        "project:close",
        "vendor:create",
        "vendor:manage",
        "vendor:evaluate",
        "vendor:sensitive",
        "contract:manage",
        "finance:view",
        "report:export",
        "report:snapshot",
    ],
    "MANAGER": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        *WORKFLOW_ITEMS,
        "project:view",
        "project:create",
        "project:manage",
        "project:change",
        "project:acceptance",
        "project:close",
        "vendor:view",
        "vendor:create",
        "vendor:manage",
        "vendor:evaluate",
        "contract:view",
        "menu:finance",
        "finance:view",
        "finance:cost",
        "finance:budget",
        "report:view",
        "report:export",
        "file:view",
        "file:upload",
    ],
    "DEPT_LEADER": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        "workflow:task",
        "workflow:instance",
        "project:view",
        "project:manage",
        "project:change",
        "vendor:view",
        "contract:view",
        "finance:view",
        "finance:cost",
        "report:view",
        "file:view",
        "file:upload",
    ],
    "FINANCE": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        *WORKFLOW_ITEMS,
        "project:view",
        "vendor:view",
        "contract:view",
        "menu:finance",
        *FINANCE_ITEMS,
        "finance:view",
        "report:view",
        "report:export",
        "report:snapshot",
        "system:audit",
        *FILE_ALL,
    ],
    "PM": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        "workflow:task",
        "workflow:instance",
        "project:view",
        "project:create",
        "project:manage",
        "project:change",
        "project:acceptance",
        "project:close",
        "vendor:view",
        "vendor:create",
        "vendor:manage",
        "vendor:evaluate",
        "vendor:sensitive",
        "contract:view",
        "menu:finance",
        "finance:view",
        "finance:cost",
        "finance:budget",
        "report:view",
        "report:export",
        *FILE_ALL,
    ],
    "PURCHASE": [
        "dashboard",
        "menu:approval",
        *APPROVAL_ITEMS,
        "workflow:task",
        "workflow:instance",
        "vendor:view",
        "vendor:create",
        "vendor:manage",
        "vendor:evaluate",
        "vendor:sensitive",
        "contract:view",
        "contract:manage",
        "project:view",
        "finance:view",
        "report:view",
        "file:view",
        "file:upload",
    ],
    "AUDITOR": [
        "dashboard",
        "workflow:instance",
        "project:view",
        "vendor:view",
        "contract:view",
        "menu:finance",
        *FINANCE_ITEMS,
        "finance:view",
        "report:view",
        "report:export",
        "system:audit",
        "file:view",
    ],
    "EMPLOYEE": [
        "dashboard",
        "approval:expense",
        "approval:leave",
        "approval:document",
        "workflow:task",
        "file:view",
        "file:upload",
    ],
}


def _d(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _month(month: int, day: int = 15, year: int = 2026) -> date:
    return date(year, month, min(day, 28))


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[seed] 数据库已重置")

def ensure_database() -> None:
    Base.metadata.create_all(bind=engine)


def sync_sequences(db: Session, company_code: str) -> None:
    """把演示数据里硬编码的业务编号回填到序列表，避免新建业务单据时重号。"""
    from sqlalchemy import func

    year = today().year
    prefix = f"PRJ-{year}-{company_code.upper()}-"
    max_no = db.execute(select(func.max(Project.no)).where(Project.no.like(f"{prefix}%"))).scalar()
    if not max_no:
        return
    name = f"PRJ:{year}:{company_code.upper()}"
    current = int(str(max_no).rsplit("-", 1)[-1])
    row = db.execute(select(Sequence).where(Sequence.name == name)).scalar_one_or_none()
    if row is None:
        db.add(Sequence(name=name, current=current))
    elif int(row.current) < current:
        row.current = current
    db.flush()


def seed_permissions(db: Session) -> dict[str, Permission]:
    existing = {row.code: row for row in db.execute(select(Permission)).scalars().all()}
    created: dict[str, Permission] = {}
    for code, name, parent_code, path, component, icon, order in MENUS:
        row = existing.get(code)
        if row is None:
            row = Permission(
                code=code,
                name=name,
                type="menu",
                path=path,
                component=component,
                icon=icon,
                sort=order,
                visible=True,
            )
            db.add(row)
            db.flush()
        row.parent_id = created[parent_code].id if parent_code and parent_code in created else (
            existing[parent_code].id if parent_code and parent_code in existing else None
        )
        created[code] = row
    for index, (code, name) in enumerate(APIS):
        row = existing.get(code)
        if row is None:
            row = Permission(code=code, name=name, type="api", sort=100 + index, visible=False)
            db.add(row)
            db.flush()
        created[code] = row
    db.flush()
    return created


def seed_roles(db: Session, perms: dict[str, Permission]) -> dict[str, Role]:
    result: dict[str, Role] = {}
    admin = Role(
        company_id=None,
        code="ADMIN",
        name="系统管理员",
        data_scope="ALL",
        is_builtin=True,
        remark="系统内置超级管理员",
    )
    db.add(admin)
    db.flush()
    result["ADMIN"] = admin
    for code, name, scope, remark in ROLE_SPECS:
        if code == "ADMIN":
            continue
        role = Role(company_id=None, code=code, name=name, data_scope=scope, is_builtin=True, remark=remark)
        db.add(role)
        db.flush()
        result[code] = role
    all_codes = [*[item[0] for item in MENUS], *[item[0] for item in APIS]]
    for code, role in result.items():
        codes = all_codes if code == "ADMIN" else ROLE_PERMISSIONS.get(code, [])
        for perm_code in codes:
            perm = perms.get(perm_code)
            if perm is None:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()
    return result


def seed_company_users(db: Session, roles: dict[str, Role]) -> tuple[Company, dict[str, Dept], dict[str, User]]:
    company = Company(
        name="示例建设科技有限公司",
        code="DEMO",
        tax_no="91310000MA1FL8X24P",
        address="上海市浦东新区世纪大道 1000 号",
        contact="021-68888888",
        status="ACTIVE",
    )
    db.add(company)
    db.flush()

    root = Dept(company_id=company.id, name="总部", code="HQ", path="/", sort=1)
    db.add(root)
    db.flush()
    root.path = f"/{root.id}/"

    specs = [
        ("GEN", "综合管理部"),
        ("FIN", "财务部"),
        ("PMO", "项目管理部"),
        ("PUR", "采购部"),
        ("TECH", "技术部"),
        ("MKT", "市场部"),
    ]
    depts: dict[str, Dept] = {"HQ": root}
    for index, (code, name) in enumerate(specs, start=2):
        dept = Dept(company_id=company.id, parent_id=root.id, name=name, code=code, path="/", sort=index)
        db.add(dept)
        db.flush()
        dept.path = f"/{root.id}/{dept.id}/"
        depts[code] = dept
    db.flush()

    user_specs = [
        ("admin", "系统管理员", None, "ADMIN", None),
        ("director", "陈董事", None, "DIRECTOR", "总经理办公室"),
        ("manager", "王经理", "PMO", "MANAGER", "项目管理部经理"),
        ("leader", "李主管", "TECH", "DEPT_LEADER", "技术部负责人"),
        ("pm", "张项目经理", "PMO", "PM", "高级项目经理"),
        ("finance", "赵会计", "FIN", "FINANCE", "财务专员"),
        ("purchase", "孙采购", "PUR", "PURCHASE", "采购专员"),
        ("employee", "周员工", "TECH", "EMPLOYEE", "实施工程师"),
        ("auditor", "吴审计", "GEN", "AUDITOR", "内审专员"),
    ]
    users: dict[str, User] = {}
    for username, real_name, dept_code, role_code, position in user_specs:
        dept = depts.get(dept_code) if dept_code else None
        user = User(
            company_id=company.id,
            dept_id=dept.id if dept else None,
            username=username,
            password_hash=hash_password(DEMO_PASSWORD, username=username),
            real_name=real_name,
            position=position,
            phone_enc=encrypt_text("1380000" + str(1000 + len(users))),
            email=f"{username}@demo-eoms.cn",
            role_ids=[roles[role_code].id],
            status="ACTIVE",
            is_super=role_code == "ADMIN",
            first_login=username == "admin",
            password_updated_at=now(),
        )
        db.add(user)
        db.flush()
        users[username] = user

    depts["HQ"].leader_user_id = users["director"].id
    depts["GEN"].leader_user_id = users["auditor"].id
    depts["FIN"].leader_user_id = users["finance"].id
    depts["PMO"].leader_user_id = users["manager"].id
    depts["PUR"].leader_user_id = users["purchase"].id
    depts["TECH"].leader_user_id = users["leader"].id
    depts["MKT"].leader_user_id = users["manager"].id
    db.flush()
    return company, depts, users


def seed_dictionary(db: Session, company_id: int) -> None:
    dictionaries = [
        ("expense_type", "差旅费", "TRAVEL"),
        ("expense_type", "业务招待费", "ENTERTAIN"),
        ("expense_type", "办公费", "OFFICE"),
        ("expense_type", "分包费", "SUBCONTRACT"),
        ("expense_type", "材料费", "MATERIAL"),
        ("expense_type", "其他", "OTHER"),
        ("leave_type", "年假", "ANNUAL"),
        ("leave_type", "事假", "PERSONAL"),
        ("leave_type", "病假", "SICK"),
        ("leave_type", "调休", "COMP"),
        ("vendor_type", "劳务分包", "SUBCONTRACT"),
        ("vendor_type", "材料供应", "MATERIAL"),
        ("vendor_type", "服务外包", "SERVICE"),
        ("vendor_type", "设备租赁", "LEASE"),
        ("project_type", "工程施工", "CONSTRUCTION"),
        ("project_type", "技术服务", "SERVICE"),
        ("project_type", "产品交付", "PRODUCT"),
        ("project_type", "其他", "OTHER"),
    ]
    for index, (dict_type, label, value) in enumerate(dictionaries):
        db.add(SysDict(company_id=company_id, dict_type=dict_type, label=label, value=value, sort=index))
    configs = [
        ("workflow.due_hours", {"value": 24}, "审批节点默认时限（小时）"),
        ("budget.alert_threshold", {"value": 0.9}, "预算预警阈值"),
        ("security.login_captcha", {"value": True}, "登录图形验证码开关"),
        ("report.snapshot_period", {"value": "month"}, "报表快照周期"),
    ]
    for key, value, description in configs:
        db.add(SysConfig(key=key, value=value, description=description))
    db.flush()


def seed_accounts(db: Session, company_id: int) -> None:
    specs = [
        ("1001", "库存现金", "ASSET"),
        ("1002", "银行存款", "ASSET"),
        ("1122", "应收账款", "ASSET"),
        ("2202", "应付账款", "LIABILITY"),
        ("5401", "分包成本", "COST"),
        ("5402", "材料成本", "COST"),
        ("5601", "差旅费", "EXPENSE"),
        ("5602", "业务招待费", "EXPENSE"),
        ("5603", "办公费", "EXPENSE"),
        ("5609", "其他费用", "EXPENSE"),
        ("6001", "主营业务收入", "REVENUE"),
    ]
    for code, name, type_ in specs:
        db.add(Account(company_id=company_id, code=code, name=name, type=type_, level=1, status="ACTIVE"))
    db.flush()


def seed_customers(db: Session, company_id: int, creator_id: int) -> dict[str, Customer]:
    specs = [
        ("C001", "华东建设集团有限公司", "刘总", "13900001111"),
        ("C002", "星海数据科技有限公司", "何总", "13900002222"),
        ("C003", "城投发展有限公司", "徐总", "13900002223"),
    ]
    result: dict[str, Customer] = {}
    for code, name, contact, phone in specs:
        item = Customer(
            company_id=company_id,
            code=code,
            name=name,
            contact=contact,
            phone_enc=encrypt_text(phone),
            email=f"{code.lower()}@customer.cn",
            address="上海市",
            status="ACTIVE",
            creator_id=creator_id,
        )
        db.add(item)
        db.flush()
        result[code] = item
    return result


def seed_workflow_definitions(db: Session, company_id: int) -> dict[str, WorkflowDefinition]:
    result = {}
    for code, spec in DEFAULT_DEFINITIONS.items():
        row = WorkflowDefinition(
            company_id=company_id,
            code=code,
            name=spec["name"],
            version=1,
            nodes_json=spec["nodes_json"],
            enabled=True,
            remark="系统预置流程",
        )
        db.add(row)
        db.flush()
        result[code] = row
    return result


def seed_vendors(db: Session, company_id: int, users: dict[str, User]) -> dict[str, Vendor]:
    specs = [
        ("V001", "华建劳务有限公司", "SUBCONTRACT", "A", "ACTIVE", 92.5),
        ("V002", "恒通建材有限公司", "MATERIAL", "B", "ACTIVE", 86.0),
        ("V003", "迅达设备租赁有限公司", "LEASE", "B", "ACTIVE", 81.5),
        ("V004", "智联技术服务有限公司", "SERVICE", "C", "ACTIVE", 74.0),
        ("V005", "新元管理咨询有限公司", "SERVICE", "C", "PENDING", 0),
    ]
    result: dict[str, Vendor] = {}
    for code, name, type_, level, status, score in specs:
        item = Vendor(
            company_id=company_id,
            dept_id=users["purchase"].dept_id,
            code=code,
            name=name,
            tax_no=f"91310000{code}XX",
            type=type_,
            level=level,
            status=status,
            owner_user_id=users["purchase"].id,
            intro=f"{name}，长期合作供应商。",
            score=Decimal(str(score)),
            creator_id=users["purchase"].id,
        )
        db.add(item)
        db.flush()
        result[code] = item

        db.add(
            VendorContact(
                company_id=company_id,
                vendor_id=item.id,
                name="业务联系人",
                title="商务经理",
                phone_enc=encrypt_text("1370000" + code[-3:]),
                email=f"contact@{code.lower()}.cn",
                is_default=True,
            )
        )
        db.add(
            VendorBank(
                company_id=company_id,
                vendor_id=item.id,
                bank_name="中国银行上海分行",
                account_no_enc=encrypt_text("6222020200" + code[-3:] + "8888"),
                account_name=name,
                is_default=True,
            )
        )
        db.add(
            VendorLicense(
                company_id=company_id,
                vendor_id=item.id,
                name="营业执照",
                no=f"LIC-{code}",
                valid_from=_d("2020-01-01"),
                valid_to=today() + timedelta(days=20 if code == "V003" else 400),
            )
        )
        db.add(
            VendorContact(
                company_id=company_id,
                vendor_id=item.id,
                name="财务联系人",
                title="财务",
                phone_enc=encrypt_text("1370001" + code[-3:]),
                email=f"finance@{code.lower()}.cn",
                is_default=False,
            )
        )
    db.flush()
    return result


def seed_projects(
    db: Session, company_id: int, users: dict[str, User], customers: dict[str, Customer]
) -> dict[str, Project]:
    specs = [
        (
            "PRJ-2026-DEMO-0001",
            "智慧园区一期建设项目",
            "CONSTRUCTION",
            "C001",
            "pm",
            "EXECUTE",
            "ACTIVE",
            "2026-01-05",
            "2027-03-31",
            "3000000",
            "5000000",
            62,
            "INTERNAL",
        ),
        (
            "PRJ-2026-DEMO-0002",
            "城市数据中台交付项目",
            "SERVICE",
            "C002",
            "pm",
            "EXECUTE",
            "ACTIVE",
            "2026-03-01",
            "2026-12-20",
            "1800000",
            "2600000",
            78,
            "INTERNAL",
        ),
        (
            "PRJ-2026-DEMO-0003",
            "运维服务年度项目",
            "SERVICE",
            "C003",
            "manager",
            "EXECUTE",
            "ACTIVE",
            "2025-12-01",
            "2026-10-31",
            "900000",
            "1200000",
            55,
            "INTERNAL",
        ),
        (
            "PRJ-2026-DEMO-0004",
            "智能制造管理咨询",
            "OTHER",
            "C002",
            "pm",
            "LAUNCH",
            "PENDING",
            "2026-12-01",
            "2027-06-30",
            "500000",
            "0",
            0,
            "SECRET",
        ),
    ]
    result: dict[str, Project] = {}
    for no, name, type_, customer, manager, stage, status, start, end, budget, contract, progress, secret in specs:
        manager_user = users[manager]
        item = Project(
            company_id=company_id,
            dept_id=manager_user.dept_id,
            no=no,
            name=name,
            type=type_,
            customer_id=customers[customer].id,
            manager_id=manager_user.id,
            stage=stage,
            status=status,
            plan_start=_d(start),
            plan_end=_d(end),
            actual_start=_d(start) if status == "ACTIVE" else None,
            budget_amount=Decimal(budget),
            contract_amount=Decimal(contract),
            progress=progress,
            secret_level=secret,
            description=f"{name}，按合同约定交付。",
            creator_id=manager_user.id,
        )
        db.add(item)
        db.flush()
        result[no[-4:]] = item

        members = [
            (manager_user, "PM"),
            (users["employee"], "MEMBER"),
            (users["finance"], "MEMBER"),
            (users["purchase"], "OBSERVER"),
        ]
        for member, role in members:
            db.add(
                ProjectMember(
                    company_id=company_id,
                    project_id=item.id,
                    user_id=member.id,
                    role=role,
                    join_at=item.plan_start,
                )
            )
    db.flush()
    return result


def seed_project_plan(db: Session, company_id: int, projects: dict[str, Project], users: dict[str, User]) -> None:
    for key, project in projects.items():
        if project.status == "PENDING":
            continue
        wbs_specs = [
            ("1", "项目启动与准备", 1, 100),
            ("2", "实施与交付", 2, project.progress),
            ("3", "验收与收尾", 2, 0),
        ]
        wbs_items: dict[str, WBS] = {}
        for index, (code, name, level, progress) in enumerate(wbs_specs):
            wbs = WBS(
                company_id=company_id,
                project_id=project.id,
                code=code,
                name=name,
                level=level,
                owner_id=project.manager_id,
                plan_start=_month(1 + index * 3),
                plan_end=_month(3 + index * 3),
                progress=progress,
                is_milestone=False,
                sort=index,
            )
            db.add(wbs)
            db.flush()
            wbs_items[code] = wbs

        task_specs = [
            ("需求调研", "1", "DONE", 100, "2026-01-05", "2026-02-10"),
            ("方案设计", "1", "DONE", 100, "2026-02-11", "2026-03-20"),
            ("开发实施", "2", "DOING", max(project.progress - 10, 0), "2026-03-21", "2026-10-31"),
            ("联调测试", "2", "TODO", 0, "2026-11-01", "2026-12-15"),
            ("验收交付", "3", "TODO", 0, "2026-12-16", "2027-01-31"),
        ]
        for name, wbs_code, status, progress, start, end in task_specs:
            db.add(
                Task(
                    company_id=company_id,
                    wbs_id=wbs_items[wbs_code].id,
                    project_id=project.id,
                    name=name,
                    owner_id=users["employee"].id if status != "DONE" else project.manager_id,
                    plan_start=_d(start),
                    plan_end=_d(end),
                    actual_start=_d(start) if status != "TODO" else None,
                    actual_end=_d(end) if status == "DONE" else None,
                    progress=progress,
                    status=status,
                    priority="HIGH" if name in {"开发实施", "验收交付"} else "MEDIUM",
                    estimate_hours=Decimal("80") if status != "TODO" else Decimal("40"),
                    actual_hours=(
                        Decimal("72")
                        if status == "DONE"
                        else Decimal("36")
                        if status == "DOING"
                        else Decimal("0")
                    ),
                )
            )
        db.add(
            Milestone(
                company_id=company_id,
                project_id=project.id,
                name="主体交付完成",
                plan_date=_d("2026-12-15"),
                status="PENDING",
            )
        )
        db.add(
            Issue(
                company_id=company_id,
                project_id=project.id,
                title="现场协调资源不足",
                level="HIGH" if key == "0003" else "MEDIUM",
                owner_id=project.manager_id,
                due_date=today() + timedelta(days=7),
                status="OPEN",
                creator_id=project.manager_id,
            )
        )
        db.add(
            Risk(
                company_id=company_id,
                project_id=project.id,
                title="关键人员流失风险",
                level="MEDIUM",
                owner_id=project.manager_id,
                due_date=today() + timedelta(days=30),
                status="OPEN",
                creator_id=project.manager_id,
            )
        )
        db.add(
            ProjectReport(
                company_id=company_id,
                project_id=project.id,
                type="WEEKLY",
                period="2026-W45",
                progress=project.progress,
                content="本周按计划推进，完成核心模块联调。",
                issues="部分接口依赖第三方，存在延迟。",
                next_plan="完成剩余接口联调并准备阶段验收。",
                reporter_id=project.manager_id,
            )
        )
    db.flush()


def seed_contracts(
    db: Session,
    company_id: int,
    users: dict[str, User],
    vendors: dict[str, Vendor],
    projects: dict[str, Project],
) -> dict[str, Contract]:
    specs = [
        ("HT-2026-0001", "V001", "0001", "智慧园区劳务分包合同", "1200000", "2026-01-10", "2026-01-10", "2026-12-31"),
        ("HT-2026-0002", "V002", "0001", "智慧园区材料采购合同", "600000", "2026-02-01", "2026-02-01", "2026-12-31"),
        ("HT-2026-0003", "V003", "0002", "数据中台设备租赁合同", "300000", "2026-03-05", "2026-03-05", "2026-11-25"),
        ("HT-2026-0004", "V004", "0003", "运维服务外包合同", "200000", "2026-01-20", "2026-01-20", "2027-01-19"),
        ("HT-2026-0005", "V001", "0003", "运维项目劳务补充合同", "150000", "2026-02-15", "2026-02-15", "2026-12-31"),
    ]
    result: dict[str, Contract] = {}
    for no, vendor_code, project_key, name, amount, sign, start, end in specs:
        vendor = vendors[vendor_code]
        project = projects[project_key]
        contract = Contract(
            company_id=company_id,
            dept_id=users["purchase"].dept_id,
            project_id=project.id,
            no=no,
            vendor_id=vendor.id,
            name=name,
            amount=Decimal(amount),
            currency="CNY",
            sign_date=_d(sign),
            start_date=_d(start),
            end_date=_d(end),
            pay_terms_json=[
                {"phase": "预付款", "ratio": 0.3, "days": 15},
                {"phase": "进度款", "ratio": 0.5, "days": 30},
                {"phase": "尾款", "ratio": 0.2, "days": 60},
            ],
            status="ACTIVE",
            remark="电子合同已归档",
            creator_id=users["purchase"].id,
        )
        db.add(contract)
        db.flush()
        result[no] = contract
        db.add(
            VendorProject(
                company_id=company_id,
                vendor_id=vendor.id,
                project_id=project.id,
                contract_id=contract.id,
                role="分包商" if vendor.type == "SUBCONTRACT" else "供应商",
                contract_amount=contract.amount,
                paid_amount=Decimal("0"),
                settled_amount=Decimal("0"),
                score=vendor.score,
            )
        )
    db.flush()
    return result


def seed_budgets(db: Session, company_id: int, projects: dict[str, Project], operator: User) -> None:
    specs = {
        "0001": [("5401", "1500000"), ("5402", "800000"), ("5601", "200000"), ("5603", "100000")],
        "0002": [("5401", "800000"), ("5601", "300000"), ("5603", "100000")],
        "0003": [("5401", "400000"), ("5602", "80000"), ("5601", "150000")],
        "0004": [("5401", "300000")],
    }
    for key, rows in specs.items():
        project = projects[key]
        for account_code, amount in rows:
            db.add(
                Budget(
                    company_id=company_id,
                    project_id=project.id,
                    account_code=account_code,
                    year=2026,
                    amount=Decimal(amount),
                    remark="年度预算",
                    creator_id=operator.id,
                )
            )
    db.flush()


def seed_payments_and_costs(
    db: Session,
    company_id: int,
    users: dict[str, User],
    vendors: dict[str, Vendor],
    projects: dict[str, Project],
    contracts: dict[str, Contract],
) -> None:
    specs = [
        ("2026-03-15", "0001", "V001", "HT-2026-0001", "300000", "5401", "工程预付款"),
        ("2026-06-20", "0001", "V001", "HT-2026-0001", "250000", "5401", "工程进度款"),
        ("2026-09-10", "0001", "V001", "HT-2026-0001", "180000", "5401", "工程进度款"),
        ("2026-04-12", "0001", "V002", "HT-2026-0002", "200000", "5402", "材料款"),
        ("2026-08-22", "0001", "V002", "HT-2026-0002", "120000", "5402", "材料款"),
        ("2026-05-08", "0002", "V003", "HT-2026-0003", "90000", "5401", "设备租赁费"),
        ("2026-10-12", "0002", "V003", "HT-2026-0003", "60000", "5401", "设备租赁费"),
        ("2026-07-19", "0002", "V004", "HT-2026-0004", "50000", "5401", "技术服务费"),
        ("2026-02-10", "0003", "V001", "HT-2026-0005", "120000", "5401", "运维劳务费"),
        ("2026-06-15", "0003", "V003", "HT-2026-0003", "45000", "5401", "设备租赁费"),
    ]
    for index, (
        pay_date,
        project_key,
        vendor_code,
        contract_no,
        amount,
        account_code,
        remark,
    ) in enumerate(specs, start=1):
        project = projects[project_key]
        vendor = vendors[vendor_code]
        contract = contracts[contract_no]
        payment = Payment(
            company_id=company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            no=f"PAY-2026-DEMO-{index:04d}",
            vendor_id=vendor.id,
            contract_id=contract.id,
            applicant_id=users["finance"].id,
            amount=Decimal(amount),
            currency="CNY",
            pay_date=_d(pay_date),
            method="BANK",
            status="PAID",
            account_code=account_code,
            remark=remark,
            approved_by=users["director"].id,
            creator_id=users["finance"].id,
        )
        db.add(payment)
        db.flush()
        record_cost(
            db,
            company_id=company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            biz_type="PAYMENT",
            biz_id=payment.id,
            account_code=account_code,
            amount=payment.amount,
            occur_date=payment.pay_date,
            vendor_id=vendor.id,
            contract_id=contract.id,
            applicant_id=users["finance"].id,
            source_no=payment.no,
            cash_date=payment.pay_date,
        )
        binding = db.execute(
            select(VendorProject).where(
                VendorProject.vendor_id == vendor.id,
                VendorProject.project_id == project.id,
                VendorProject.contract_id == contract.id,
            )
        ).scalar_one_or_none()
        if binding is not None:
            binding.paid_amount = Decimal(str(binding.paid_amount or 0)) + payment.amount
    db.flush()


def seed_receipts_revenue(
    db: Session,
    company_id: int,
    users: dict[str, User],
    customers: dict[str, Customer],
    projects: dict[str, Project],
) -> None:
    receipts = [
        ("2026-04-10", "0001", "C001", "1500000", "合同首付款"),
        ("2026-08-15", "0001", "C001", "800000", "进度款"),
        ("2026-06-28", "0002", "C002", "900000", "里程碑款"),
        ("2026-10-20", "0002", "C002", "500000", "验收款"),
        ("2026-03-05", "0003", "C003", "600000", "年度服务费"),
    ]
    for index, (receipt_date, project_key, customer_code, amount, remark) in enumerate(receipts, start=1):
        project = projects[project_key]
        receipt = Receipt(
            company_id=company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            no=f"RCPT-2026-DEMO-{index:04d}",
            customer_id=customers[customer_code].id,
            amount=Decimal(amount),
            currency="CNY",
            receipt_date=_d(receipt_date),
            method="BANK",
            status="REGISTERED",
            remark=remark,
            creator_id=users["finance"].id,
        )
        db.add(receipt)
        db.flush()
        record_cost(
            db,
            company_id=company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            biz_type="RECEIPT",
            biz_id=receipt.id,
            account_code="1002",
            amount=receipt.amount,
            occur_date=receipt.receipt_date,
            applicant_id=users["finance"].id,
            source_no=receipt.no,
            cash_date=receipt.receipt_date,
        )

    revenue_rows = [
        ("2026-03-31", "0001", "C001", "1200000", "CONFIRMED", "一期进度确认"),
        ("2026-08-31", "0001", "C001", "1000000", "CONFIRMED", "二期进度确认"),
        ("2026-11-15", "0001", "C001", "400000", "DRAFT", "本期暂估计收"),
        ("2026-05-31", "0002", "C002", "800000", "CONFIRMED", "中台一期确认"),
        ("2026-09-30", "0002", "C002", "600000", "CONFIRMED", "中台二期确认"),
        ("2026-02-28", "0003", "C003", "500000", "CONFIRMED", "年度服务确认"),
        ("2026-10-31", "0003", "C003", "300000", "CONFIRMED", "年度服务确认"),
    ]
    for index, (confirm_date, project_key, customer_code, amount, status, remark) in enumerate(revenue_rows, start=1):
        project = projects[project_key]
        day = _d(confirm_date)
        revenue = RevenueConfirm(
            company_id=company_id,
            dept_id=project.dept_id,
            project_id=project.id,
            no=f"REV-2026-DEMO-{index:04d}",
            customer_id=customers[customer_code].id,
            amount=Decimal(amount),
            currency="CNY",
            confirm_date=day,
            period=day.strftime("%Y-%m"),
            source_type="MANUAL",
            status=status,
            remark=remark,
            creator_id=users["finance"].id,
        )
        db.add(revenue)
        db.flush()
        if status == "CONFIRMED":
            record_cost(
                db,
                company_id=company_id,
                dept_id=project.dept_id,
                project_id=project.id,
                biz_type="RECEIVABLE",
                biz_id=revenue.id,
                account_code="6001",
                amount=revenue.amount,
                occur_date=revenue.confirm_date,
                applicant_id=users["finance"].id,
                source_no=revenue.no,
            )
    db.flush()


def seed_expenses(
    db: Session,
    company_id: int,
    depts: dict[str, Dept],
    users: dict[str, User],
    projects: dict[str, Project],
) -> dict[str, Expense]:
    specs = [
        ("EXP-2026-DEMO-0001", "employee", "TRAVEL", "PAID", "0002", "4860", "2026-09-18", "上海-北京出差差旅"),
        ("EXP-2026-DEMO-0002", "employee", "OFFICE", "APPROVED", "0002", "1200", "2026-10-22", "办公耗材采购"),
        ("EXP-2026-DEMO-0003", "pm", "ENTERTAIN", "RUNNING", "0001", "8500", "2026-11-12", "客户项目沟通招待"),
        (
            "EXP-2026-DEMO-0004",
            "employee",
            "TRAVEL",
            "DRAFT",
            "0001",
            "65000",
            "2026-11-15",
            "海外考察差旅（阈值升级演示）",
        ),
        ("EXP-2026-DEMO-0005", "finance", "OTHER", "DRAFT", "0002", "2300", "2026-11-14", "银行手续费"),
    ]
    result: dict[str, Expense] = {}
    for no, username, type_, status, project_key, amount, occur, remark in specs:
        user = users[username]
        project = projects[project_key]
        total = Decimal(amount)
        expense = Expense(
            company_id=company_id,
            dept_id=user.dept_id,
            project_id=project.id,
            no=no,
            applicant_id=user.id,
            type=type_,
            amount_total=total,
            currency="CNY",
            items_json=[
                {
                    "category": type_,
                    "amount": float(total),
                    "occur_date": occur,
                    "description": remark,
                }
            ],
            invoices_file_ids=[],
            payee=user.real_name,
            remark=remark,
            status=status,
            submitted_at=now() if status in {"RUNNING", "APPROVED", "PAID"} else None,
            creator_id=user.id,
        )
        if status == "PAID":
            expense.paid_at = now()
            expense.verified_at = now()
        elif status == "APPROVED":
            expense.verified_at = None
        db.add(expense)
        db.flush()
        db.add(
            ExpenseItem(
                expense_id=expense.id,
                category=type_,
                amount=total,
                occur_date=_d(occur),
                description=remark,
            )
        )
        result[no[-4:]] = expense
    db.flush()

    for expense in result.values():
        if expense.status not in {"APPROVED", "PAID"}:
            continue
        record_cost(
            db,
            company_id=company_id,
            dept_id=expense.dept_id,
            project_id=expense.project_id,
            biz_type="EXPENSE",
            biz_id=expense.id,
            account_code="5603" if expense.type == "OFFICE" else "5601",
            amount=Decimal(str(expense.amount_total)),
            occur_date=expense.created_at.date(),
            applicant_id=expense.applicant_id,
            source_no=expense.no,
            cash_date=expense.paid_at.date() if expense.paid_at else None,
        )
    db.flush()
    return result


def seed_leaves(db: Session, company_id: int, users: dict[str, User]) -> None:
    for user in users.values():
        if user.username == "admin":
            continue
        for type_, total in (("ANNUAL", "10"), ("COMP", "3"), ("SICK", "8")):
            db.add(
                LeaveBalance(
                    company_id=company_id,
                    user_id=user.id,
                    year=2026,
                    type=type_,
                    total=Decimal(total),
                    used=Decimal("3") if type_ == "ANNUAL" else Decimal("0"),
                    remain=Decimal(total) - (Decimal("3") if type_ == "ANNUAL" else Decimal("0")),
                )
            )
    db.add(
        Leave(
            company_id=company_id,
            dept_id=users["employee"].dept_id,
            no="LV-2026-DEMO-0001",
            applicant_id=users["employee"].id,
            type="ANNUAL",
            start_time=datetime(2026, 11, 18, 9, 0),
            end_time=datetime(2026, 11, 20, 18, 0),
            duration=Decimal("3"),
            reason="家庭事务",
            handover_user_id=users["leader"].id,
            status="RUNNING",
            submitted_at=now(),
            creator_id=users["employee"].id,
        )
    )
    db.add(
        Leave(
            company_id=company_id,
            dept_id=users["pm"].dept_id,
            no="LV-2026-DEMO-0002",
            applicant_id=users["pm"].id,
            type="COMP",
            start_time=datetime(2026, 10, 8, 9, 0),
            end_time=datetime(2026, 10, 8, 18, 0),
            duration=Decimal("1"),
            reason="调休",
            status="APPROVED",
            submitted_at=datetime(2026, 10, 6, 10, 0),
            creator_id=users["pm"].id,
        )
    )
    db.flush()


def seed_documents(db: Session, company_id: int, users: dict[str, User]) -> None:
    specs = [
        ("DOC-2026-DEMO-0001", "关于发布《项目交付管理办法》的通知", "INSTITUTION", "INTERNAL", "RUNNING"),
        ("DOC-2026-DEMO-0002", "智慧园区项目投标用印申请", "SEAL", "SECRET", "APPROVED"),
        ("DOC-2026-DEMO-0003", "关于开展年度内部审计的通知", "DISPATCH", "INTERNAL", "DRAFT"),
    ]
    for doc_no, title, category, secret, status in specs:
        db.add(
            Document(
                company_id=company_id,
                dept_id=users["admin"].dept_id,
                doc_no=doc_no,
                title=title,
                category=category,
                secret_level=secret,
                content=f"{title}，请各部门遵照执行。",
                effect_date=today(),
                status=status,
                submitted_at=now() if status in {"RUNNING", "APPROVED"} else None,
                creator_id=users["admin"].id,
            )
        )
    db.flush()


def seed_running_workflows(
    db: Session,
    company_id: int,
    users: dict[str, User],
    defs: dict[str, WorkflowDefinition],
    expenses: dict[str, Expense],
    projects: dict[str, Project],
    vendors: dict[str, Vendor],
) -> None:
    running = [
        ("EXPENSE", "EXPENSE", expenses["0003"].id, "费用报销审批：客户招待费", "employee", "APPROVER_1", "部门负责人"),
        ("LEAVE", "LEAVE", None, "请假审批：周员工 年假 3 天", "employee", "APPROVER_1", "部门负责人"),
        ("DOCUMENT", "DOCUMENT", None, "文件审批：项目交付管理办法", "admin", "APPROVER_1", "部门负责人"),
        ("PROJECT_CHANGE", "PROJECT_CHANGE", None, "项目变更：智慧园区预算调整", "pm", "APPROVER_2", "部门经理"),
        (
            "VENDOR_ONBOARD",
            "VENDOR_ONBOARD",
            vendors["V005"].id,
            "供应商准入：新元管理咨询有限公司",
            "purchase",
            "APPROVER_2",
            "部门经理",
        ),
    ]
    assignee_map = {
        "部门负责人": users["leader"].id,
        "部门经理": users["manager"].id,
        "董事": users["director"].id,
    }
    change = Change(
        company_id=company_id,
        dept_id=users["pm"].dept_id,
        project_id=projects["0001"].id,
        applicant_id=users["pm"].id,
        type="BUDGET",
        before_json={"budget_amount": "3000000"},
        after_json={"budget_amount": "3400000"},
        reason="客户新增建设内容，申请预算调整。",
        status="RUNNING",
        creator_id=users["pm"].id,
    )
    db.add(change)
    db.flush()

    for def_code, biz_type, biz_id, title, initiator, node_code, node_name in running:
        initiator_user = users[initiator]
        def_row = defs[def_code]
        actual_biz_id = biz_id
        if def_code == "LEAVE":
            leave = db.execute(
                select(Leave).where(Leave.no == "LV-2026-DEMO-0001")
            ).scalar_one()
            actual_biz_id = leave.id
            leave.instance_id = None
        elif def_code == "DOCUMENT":
            document = db.execute(
                select(Document).where(Document.doc_no == "DOC-2026-DEMO-0001")
            ).scalar_one()
            actual_biz_id = document.id
        elif def_code == "PROJECT_CHANGE":
            actual_biz_id = change.id
            change.instance_id = None
        instance = WorkflowInstance(
            company_id=company_id,
            dept_id=initiator_user.dept_id,
            def_id=def_row.id,
            def_code=def_code,
            biz_type=biz_type,
            biz_id=actual_biz_id,
            title=title,
            initiator_id=initiator_user.id,
            current_node=node_code,
            status="RUNNING",
            context_json={
                "initiator_name": initiator_user.real_name,
                "def_version": 1,
                "amount": float(expenses["0003"].amount_total) if def_code == "EXPENSE" else None,
            },
            creator_id=initiator_user.id,
        )
        db.add(instance)
        db.flush()
        db.add(
            WorkflowTask(
                company_id=company_id,
                dept_id=initiator_user.dept_id,
                instance_id=instance.id,
                node_code=node_code,
                node_name=node_name,
                assignee_id=assignee_map[node_name],
                candidate_ids=[],
                status="PENDING",
                mode="ANY",
                seq=1,
                arrive_at=now(),
                due_at=now() + timedelta(hours=24),
            )
        )
        db.add(
            WorkflowRecord(
                company_id=company_id,
                instance_id=instance.id,
                node_code="START",
                node_name="发起人提交",
                operator_id=initiator_user.id,
                operator_name=initiator_user.real_name,
                action="SUBMIT",
                comment="提交审批",
            )
        )
        if def_code == "LEAVE":
            leave = db.execute(select(Leave).where(Leave.no == "LV-2026-DEMO-0001")).scalar_one()
            leave.instance_id = instance.id
        elif def_code == "DOCUMENT":
            document = db.execute(
                select(Document).where(Document.doc_no == "DOC-2026-DEMO-0001")
            ).scalar_one()
            document.instance_id = instance.id
        elif def_code == "PROJECT_CHANGE":
            change.instance_id = instance.id
        elif def_code == "EXPENSE":
            expense = expenses["0003"]
            expense.instance_id = instance.id
        elif def_code == "VENDOR_ONBOARD":
            vendors["V005"].instance_id = instance.id
    db.flush()


def seed_notifications(db: Session, company_id: int, users: dict[str, User]) -> None:
    db.add(
        Notification(
            company_id=company_id,
            user_id=users["pm"].id,
            title="项目健康预警：运维服务年度项目",
            content="项目计划完成日 2026-10-31 已逾期，请关注进度。",
            type="ALERT",
            biz_type="PROJECT",
            biz_id=None,
            link="/projects",
        )
    )
    db.add(
        Notification(
            company_id=company_id,
            user_id=users["manager"].id,
            title="待审批提醒",
            content="您有 2 条待审批任务，请及时处理。",
            type="APPROVAL",
            link="/approvals/tasks",
        )
    )
    db.add(
        Notification(
            company_id=company_id,
            user_id=users["finance"].id,
            title="预算预警：智慧园区一期建设项目",
            content="分包成本科目预算使用率已达 48.7%。",
            type="ALERT",
            biz_type="BUDGET",
            link="/finance/budgets",
        )
    )
    db.flush()


def seed_periods(db: Session, company_id: int, operator: User) -> None:
    for month in range(1, 13):
        period = f"2026-{month:02d}"
        closed = month <= 10
        db.add(
            Period(
                company_id=company_id,
                period=period,
                status="CLOSED" if closed else "OPEN",
                closed_by=operator.id if closed else None,
                closed_at=datetime(2026, month + 1, 3, 9, 0) if closed and month < 12 else None,
                remark="月结" if closed else None,
            )
        )
    db.flush()


def seed_analytics(db: Session, company_id: int, projects: dict[str, Project]) -> None:
    for project in projects.values():
        if project.status in {"ACTIVE", "CLOSED"}:
            # 损益快照为「截至当期」累计口径，仅生成最新一期
            generate_project_pnl(db, project, "2026-11", persist=True)
    generate_company_snapshots(db, company_id, "2026-11")
    db.flush()


def run(reset: bool = False, snapshots: bool = True) -> None:
    if reset:
        reset_database()
    else:
        ensure_database()
    db: Session = SessionLocal()
    try:
        db.begin()
        exists = db.execute(select(Company).where(Company.code == "DEMO")).scalar_one_or_none()
        if exists is not None:
            print("[seed] 已存在演示公司，如需重建请使用 --reset")
            db.rollback()
            return
        perms = seed_permissions(db)
        roles = seed_roles(db, perms)
        company, depts, users = seed_company_users(db, roles)
        seed_dictionary(db, company.id)
        seed_accounts(db, company.id)
        customers = seed_customers(db, company.id, users["manager"].id)
        defs = seed_workflow_definitions(db, company.id)
        vendors = seed_vendors(db, company.id, users)
        projects = seed_projects(db, company.id, users, customers)
        seed_project_plan(db, company.id, projects, users)
        contracts = seed_contracts(db, company.id, users, vendors, projects)
        seed_budgets(db, company.id, projects, users["finance"])
        seed_payments_and_costs(db, company.id, users, vendors, projects, contracts)
        seed_receipts_revenue(db, company.id, users, customers, projects)
        expenses = seed_expenses(db, company.id, depts, users, projects)
        seed_leaves(db, company.id, users)
        seed_documents(db, company.id, users)
        seed_running_workflows(db, company.id, users, defs, expenses, projects, vendors)
        seed_notifications(db, company.id, users)
        seed_periods(db, company.id, users["finance"])
        sync_sequences(db, company.code)
        for index, vendor_code in enumerate(vendors, start=1):
            vendor = vendors[vendor_code]
            db.add(
                Evaluation(
                    company_id=company.id,
                    vendor_id=vendor.id,
                    project_id=projects["0001"].id if index % 2 else projects["0002"].id,
                    evaluator_id=users["pm"].id,
                    quality_score=Decimal("90") - index,
                    schedule_score=Decimal("88") - index,
                    cooperate_score=Decimal("92") - index,
                    total_score=vendor.score or Decimal("80"),
                    grade=vendor.level,
                    comment="年度履约评价",
                    eval_date=_month(10, 20),
                )
            )
        db.add(
            Acceptance(
                company_id=company.id,
                dept_id=projects["0002"].dept_id,
                project_id=projects["0002"].id,
                applicant_id=users["pm"].id,
                acceptor="星海数据科技有限公司",
                result="PASS",
                accept_date=_d("2026-10-25"),
                accept_amount=Decimal("600000"),
                remark="阶段验收通过",
                status="APPROVED",
                creator_id=users["pm"].id,
            )
        )
        db.flush()
        if snapshots:
            seed_analytics(db, company.id, projects)
        db.commit()
        print("[seed] 演示数据初始化完成")
        print(f"[seed] 登录账号：admin / {DEMO_PASSWORD}（首次登录需改密）")
        print("       其他账号：director/manager/leader/pm/finance/purchase/employee/auditor")
        print(f"[seed] 数据库：{settings.resolved_database_url}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="EOMS 演示数据初始化")
    parser.add_argument("--reset", action="store_true", help="删除全部数据后重建（仅限开发环境）")
    parser.add_argument("--no-snapshot", action="store_true", help="跳过报表快照与项目损益生成")
    args = parser.parse_args()
    if args.reset and settings.is_prod:
        raise SystemExit("生产环境禁止 --reset")
    run(reset=args.reset, snapshots=not args.no_snapshot)


if __name__ == "__main__":
    main()
