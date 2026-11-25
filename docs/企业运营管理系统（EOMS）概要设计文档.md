# 企业运营管理系统（EOMS）概要设计文档

**版本**：V1.0  **日期**：2026-11-16  **状态**：评审稿
**技术基线**：Python 3.12 / FastAPI / PostgreSQL 16 / Redis 7 / Docker Compose / 单工程（Monorepo）

---

## 1. 项目概述

### 1.1 建设目标
构建一套面向中小型企业的一体化运营管理系统，把「日常审批 — 项目全生命周期 — 供应商 — 成本核算 — 经营报表」串成一条数据闭环：审批单据与项目、合同、供应商强关联，费用自动归集到项目，项目损益自动汇总为公司经营报表，消除 Excel 台账与数据孤岛。

### 1.2 业务范围
| 域 | 核心能力 |
|---|---|
| 日常审批 | 报销、请假、文件（用印/发文/制度）审批，四级流程：发起人→负责人→经理→董事 |
| 项目管理 | 立项、策划、计划、执行、收尾五阶段全过程管理 |
| 供应商管理 | 供应商档案、资质、合同、参与项目、评价与分级 |
| 成本管理 | 计收、收款、付款、报销四类单据的项目费用核算与预算对比 |
| 企业运营 | 营收、现金流、利润三类报表及多维汇总 |
| 平台能力 | 组织、用户、角色权限、数据隔离、审计、文件、通知、字典 |

### 1.3 设计约束
- 单工程部署，不拆微服务；模块化分层，保证后期可拆分。
- 所有业务数据必须带数据域（公司/部门/项目），实现行级隔离。
- 敏感数据（银行账号、身份证、报价）加密存储 + 权限脱敏。
- 审批流四级可配置（可裁剪为二级/三级），不硬编码在业务代码中。

### 1.4 角色（预置）
发起人（员工）、部门负责人、财务专员、项目经理、采购专员、总经理/经理、董事、系统管理员、审计员。

---

## 2. 总体架构

### 2.1 架构分层
```
接入层  Nginx（反向代理/TLS/限流）
        │
应用层  FastAPI（REST API + 统一中间件：鉴权/数据域/日志/异常/幂等）
        │  ├─ 领域服务层（approval / project / vendor / cost / report / iam）
        │  ├─ 工作流引擎（自研轻量状态机 + 任务队列）
        │  └─ 定时任务（Celery Beat：预算预警、报表快照、超时催办）
数据层  PostgreSQL 16（业务数据） | Redis 7（缓存/分布式锁/任务队列）
        │  MinIO（附件、合同、发票影像）
运维层  Prometheus + Grafana（指标）｜Loki（日志）｜pg_dump 定时备份
```

### 2.2 技术选型
| 层次 | 选型 | 说明 |
|---|---|---|
| 语言/运行时 | Python 3.12 | 全栈统一 |
| Web 框架 | FastAPI + Uvicorn | 异步、自动 OpenAPI |
| ORM/迁移 | SQLAlchemy 2.0 + Alembic | 版本化 DDL |
| 校验/序列化 | Pydantic v2 | 出入参契约 |
| 任务队列 | Celery + Redis | 审批通知、报表计算、文件解析 |
| 数据库 | PostgreSQL 16 | 事务、JSONB、行级安全 |
| 缓存/锁 | Redis 7 | 权限缓存、流程并发锁 |
| 对象存储 | MinIO（可切 OSS） | 附件与影像 |
| 前端 | Vue3 + Element Plus（或 Jinja2 服务端渲染） | 单工程内 `web/` 目录 |
| 部署 | Docker + Docker Compose | 单机/小集群 |

### 2.3 单工程目录结构
```
eoms/
├─ app/
│  ├─ main.py            # 应用入口、路由挂载、中间件
│  ├─ core/              # 配置、安全、日志、异常、依赖注入
│  ├─ db/                # engine、session、base、pg 扩展
│  ├─ models/            # SQLAlchemy 实体（按域分包）
│  ├─ schemas/           # Pydantic DTO
│  ├─ repositories/      # 数据访问（含数据域过滤）
│  ├─ services/          # 领域服务：iam/approval/project/vendor/cost/report
│  ├─ workflow/          # 流程定义、状态机、任务分派、事件钩子
│  ├─ api/v1/            # 路由（auth/iam/approval/project/vendor/cost/report/file）
│  ├─ tasks/             # Celery 任务与定时调度
│  └─ utils/             # 编号生成、金额、加密、脱敏、导出
├─ alembic/              # 数据库迁移脚本
├─ web/                  # 前端工程
├─ scripts/              # 初始化数据、压测、运维脚本
├─ tests/                # 单元/接口/权限隔离测试
├─ docker/               # Dockerfile、nginx.conf、entrypoint
├─ docker-compose.yml
└─ pyproject.toml
```

---

## 3. 平台基础设计（IAM 与安全底座）

### 3.1 认证与授权
- 认证：账号密码（bcrypt/argon2）+ 图形验证码 → 签发 JWT（access 30min，refresh 7d，Redis 黑名单支持登出）；支持后续扩展扫码/SSO。
- 授权模型：**RBAC + 数据域**。`用户 → 角色 → 权限点（menu/api/button）`；数据域 `scope ∈ {ALL, COMPANY, DEPT, DEPT_TREE, PROJECT, SELF}`。
- 数据隔离实现（双保险）：
  1. 应用层：`DataScopeFilter` 依当前用户角色自动注入 `WHERE` 条件（`company_id/dept_id/project_id/creator_id`）；
  2. 数据库层：PostgreSQL Row-Level Security 作为兜底（会话变量 `app.user_id/app.scope`）。
- 越权防护：所有详情/更新接口做「资源归属校验」，不依赖前端隐藏按钮。

### 3.2 核心表
| 表 | 关键字段 |
|---|---|
| `sys_company` | id, name, code, tax_no, status |
| `sys_dept` | id, company_id, parent_id, name, sort |
| `sys_user` | id, company_id, dept_id, username, password_hash, real_name, phone_enc, email, role_ids, status, is_super |
| `sys_role` | id, code, name, data_scope, status |
| `sys_permission` | id, code, name, type(menu/api/button), parent_id |
| `sys_role_permission` | role_id, permission_id |
| `sys_audit_log` | id, user_id, action, target_type, target_id, before_json, after_json, ip, ua, created_at |
| `sys_file` | id, biz_type, biz_id, name, path, size, hash, uploader_id |
| `sys_dict` / `sys_config` | 字典项、系统参数（如审批超时时长、预算预警阈值） |

### 3.3 审计与合规
- 关键操作（审批、付款、供应商资料变更、权限变更、导出）全量留痕，含变更前后差异，日志表只增不改，保留 ≥ 3 年。
- 敏感字段（身份证、银行卡、手机号）AES-256 加密存储，展示按权限脱敏（`6222****1234`）。
- 密码策略、登录失败锁定、并发会话限制、接口限流（Redis 令牌桶）、SQL 参数化、XSS/CSRF 防护、HTTPS 全站。

---

## 4. 日常审批模块

### 4.1 设计思路
抽象「**流程定义 + 流程实例 + 审批任务 + 业务表单**」四件套，业务单据与流程解耦：报销/请假/文件各自保留业务表，通过 `biz_type + biz_id` 关联流程实例，新增审批类型只需加表单与配置，不改引擎。

### 4.2 四级流程模型
- 流程定义 `wf_definition`：`code(如 EXPENSE/LEAVE/DOC)`、`version`、`nodes_json`（有序节点数组）、`enabled`。
- 默认节点链（可裁剪/加会签）：
  1. `START` 发起人提交（表单校验、附件必填）
  2. `APPROVER_1` 部门负责人（或签/会签、可加签）
  3. `APPROVER_2` 部门经理 / 分管领导
  4. `APPROVER_3` 董事（或总经理→董事，按金额阈值升级）
  5. `END` 归档（触发业务回调：写成本、更新库存/假期余额）
- 条件路由：金额 ≥ 阈值、请假天数 ≥ N、涉密文件 → 强制升级至董事节点；低于阈值可跳过中间节点。
- 审批动作：同意、驳回（回上一节点/回发起人）、转办、加签、撤回（仅未开始处理时）、催办、抄送。
- 并发与一致性：流程实例行级锁 + Redis 分布式锁，防止双人同时审批造成状态错乱；审批与业务回调用本地事务保证一致，跨服务动作用 Outbox 表 + Celery 重试。

### 4.3 关键表
| 表 | 关键字段 |
|---|---|
| `wf_definition` | id, code, name, version, nodes_json, enabled |
| `wf_instance` | id, def_id, biz_type, biz_id, title, initiator_id, current_node, status(DRAFT/RUNNING/APPROVED/REJECTED/CANCELED), start_at, finish_at |
| `wf_task` | id, instance_id, node_code, assignee_id, candidate_ids, status(PENDING/APPROVED/REJECTED/TRANSFERRED), action, comment, arrive_at, finish_at, due_at |
| `wf_record` | id, instance_id, node_code, operator_id, action, comment, attachments, created_at（审批留痕） |
| `biz_expense`（报销） | id, no, applicant_id, dept_id, project_id, type(差旅/招待/办公/其他), amount_total, currency, items_json, invoices_file_ids, payee, status, instance_id |
| `biz_expense_item` | id, expense_id, category, amount, occur_date, desc, file_id |
| `biz_leave`（请假） | id, applicant_id, type(年休/事假/病假/调休), start_time, end_time, duration, reason, handover_user_id, status, instance_id |
| `biz_document`（文件） | id, doc_no, title, category(制度/发文/用印/合同), secret_level, content/file_id, effect_date, status, instance_id |
| `biz_leave_balance` | user_id, year, type, total, used, remain |

### 4.4 状态机（报销示例）
`草稿 → 已提交(审批中) → 已通过 → 财务复核 → 已付款 → 已归档`；任一节点驳回 → `已驳回`（可修改后重新提交，生成新流程版本）。

---

## 5. 项目管理模块

### 5.1 五阶段生命周期
| 阶段 | 主要对象与动作 | 关键输出 |
|---|---|---|
| 立项 | 立项申请（走审批流）、可行性/预算估算、立项评审、项目编号生成 | 项目档案、初始预算 |
| 策划 | 项目章程、组织架构与成员、WBS 分解、里程碑、资源与风险计划、采购计划 | 项目计划书、WBS 基线 |
| 计划 | 任务排期（甘特）、责任人、工期与工时预算、成本预算分解（按 WBS/费用科目） | 项目计划基线 |
| 执行 | 任务填报与进度、工时、变更申请、问题与风险跟踪、合同/付款/报销关联、周报月报 | 进度实绩、成本实绩 |
| 收尾 | 验收申请与签署、结算（计收/收款核对）、尾款、复盘总结、资料归档、项目关闭 | 验收单、项目损益表、归档包 |

### 5.2 关键表
| 表 | 关键字段 |
|---|---|
| `pm_project` | id, no, name, type, customer_id, dept_id, manager_id, stage(LAUNCH/PLAN/EXECUTE/CLOSE), status, plan_start, plan_end, actual_start, actual_end, budget_amount, contract_amount, progress, secret_level |
| `pm_project_member` | project_id, user_id, role(PM/成员/观察者), join_at |
| `pm_initiation` | id, project_id, applicant_id, background, goal, estimate_cost, estimate_income, risk_desc, instance_id, status |
| `pm_wbs` | id, project_id, parent_id, code, name, level, owner_id, plan_start, plan_end, progress, is_milestone |
| `pm_task` | id, wbs_id, project_id, name, owner_id, plan_start, plan_end, actual_start, actual_end, progress, status, priority, estimate_hours |
| `pm_milestone` | id, project_id, name, plan_date, actual_date, status, acceptance_file_id |
| `pm_change` | id, project_id, type(范围/工期/预算), before_json, after_json, reason, instance_id, status |
| `pm_issue` / `pm_risk` | id, project_id, title, level, owner_id, due_date, status, solution |
| `pm_acceptance` | id, project_id, applicant_id, acceptor, result, sign_file_id, accept_date, status |
| `pm_project_archive` | project_id, doc_type, file_id, archived_at |

### 5.3 设计要点
- **项目编码规则**：`PRJ-YYYY-公司码-流水`，全局唯一，作为成本归集主键。
- **基线机制**：计划基线（`pm_task` 快照表 `pm_task_baseline`）与实绩对比，支撑进度偏差（SV）与成本偏差（CV）分析。
- **变更闭环**：预算/工期变更必须走审批流，通过后更新项目预算并留痕，禁止直接改数。
- **收尾校验**：未完成任务、未结清付款、未归档验收单时禁止关闭项目（可配置强制关闭并留痕）。

---

## 6. 供应商管理模块

### 6.1 功能设计
- **准入**：供应商注册/录入 → 资质审核（营业执照、开户许可、行业资质、法人身份）→ 审批通过入库；支持黑名单。
- **档案**：基本信息、联系人、银行账户（加密）、资质证照（附件 + 有效期提醒）、分类（分包/材料/服务/租赁）、分级（A/B/C）。
- **合同关联**：合同主档（甲乙方、金额、币种、起止、付款条款、附件），一个供应商 ↔ 多合同，合同 ↔ 多项目（多对多）。
- **项目关联**：供应商参与项目记录（角色、合同额、已付、结算额、评价分）。
- **评价与考核**：按项目交付质量/进度/配合度打分，自动计算综合分与等级，形成年度评价报告。
- **风险提醒**：证照到期、合同到期、逾期未交付、付款超预算预警。

### 6.2 关键表
| 表 | 关键字段 |
|---|---|
| `vd_vendor` | id, code, name, tax_no, type, level, status(ACTIVE/BLACKLIST/PENDING), owner_user_id, intro |
| `vd_vendor_contact` | vendor_id, name, title, phone_enc, email |
| `vd_vendor_bank` | vendor_id, bank_name, account_no_enc, account_name, is_default |
| `vd_vendor_license` | vendor_id, name, no, file_id, valid_from, valid_to |
| `vd_contract` | id, no, vendor_id, project_id(nullable), name, amount, currency, sign_date, start_date, end_date, pay_terms_json, file_id, status |
| `vd_vendor_project` | vendor_id, project_id, contract_id, role, contract_amount, paid_amount, settled_amount, score |
| `vd_evaluation` | id, vendor_id, project_id, evaluator_id, quality_score, schedule_score, cooperate_score, total_score, comment, eval_date |

---

## 7. 成本管理模块

### 7.1 核算模型
四类源单据统一归集到「**项目 + 费用科目 + 期间**」三维：

| 单据 | 方向 | 来源 | 归集口径 |
|---|---|---|---|
| 计收（收入确认） | 收入 | 项目进度/验收确认单 | 按确认金额与期间计入营收 |
| 收款 | 现金流入 | 财务收款登记（关联合同/客户） | 计入现金流，不直接确认收入 |
| 付款 | 现金流出 | 合同付款申请（关联供应商） | 计入成本与现金流 |
| 报销费用 | 费用 | 审批通过的报销单 | 按费用科目计入项目成本 |

统一台账表 `fin_cost_record`：
`id, project_id, biz_type(RECEIVABLE/RECEIPT/PAYMENT/EXPENSE), biz_id, account_code(费用科目), amount, currency, occur_date, period(YYYY-MM), vendor_id, contract_id, applicant_id, source_no, status, created_at`

### 7.2 处理规则
- **写入时机**：单据审批通过（或财务复核通过）时，由工作流回调写入 `fin_cost_record`，幂等键 `biz_type + biz_id + account_code`，防重复入账。
- **预算对比**：`fin_budget`（项目预算，按科目/年度分解）与实际发生额对比，超支 ≥ 阈值（默认 90%）触发预警通知项目经理与财务。
- **项目损益**：`项目毛利 = 计收 − 付款 − 报销费用（− 分摊人力成本，可选）`；按项目、部门、期间汇总。
- **调整与冲销**：错账不物理删除，用红字冲销记录（`is_reversal`），保证可追溯。
- **期间管理**：支持月度关账（`fin_period` 状态：开放/关账），关账后禁止写入该期间数据。

### 7.3 关键表
`fin_account`（科目树）、`fin_budget`、`fin_cost_record`、`fin_payment`（付款申请，含供应商/合同/分期）、`fin_receipt`（收款登记）、`fin_revenue_confirm`（计收确认）、`fin_period`、`fin_project_pnl`（项目损益快照）。

---

## 8. 企业运营报表模块

### 8.1 报表清单
| 报表 | 维度 | 核心指标 |
|---|---|---|
| 经营总览（驾驶舱） | 公司/年度 | 营收、成本、毛利、利润率、应收应付、在手项目数 |
| 营收报表 | 期间/部门/项目/客户 | 计收金额、确认进度、同比环比 |
| 现金流量表 | 期间/项目 | 经营流入（收款）、流出（付款+报销）、净现金流、累计现金流 |
| 利润表 | 期间/部门/项目 | 营收−成本−费用=利润、毛利率、净利率 |
| 项目损益表 | 项目 | 预算 vs 实际、偏差率、里程碑达成 |
| 供应商支出分析 | 供应商/类别 | 合同额、已付、占比、评价分 |
| 审批效率报表 | 部门/流程 | 平均审批时长、超时率、驳回率 |

### 8.2 实现方式
- **计算策略**：明细实时查 + 汇总日/月快照（`rpt_snapshot` 表，Celery 定时跑批），报表查询走快照，保证秒级响应。
- **口径一致**：所有指标口径集中在 `report/metrics.py` 定义（单一事实来源），API 与导出共用。
- **数据权限**：报表同样受数据域约束——部门经理只见本部门及下属部门，PM 只见自己项目，董事/管理员可见全公司。
- **输出**：在线图表（ECharts）+ Excel/PDF 导出（导出行为写审计日志）。

---

## 9. 接口设计规范

- 风格：RESTful，前缀 `/api/v1`，资源名复数；统一响应体：
```json
{ "code": 0, "msg": "ok", "data": {}, "trace_id": "..." }
```
- 分页：`page`, `page_size`, `total`；排序/过滤白名单校验，禁止拼接原始 SQL。
- 幂等：写接口支持 `Idempotency-Key`（付款、报销提交、流程审批必须）。
- 并发：乐观锁 `version` 字段（任务、预算、流程实例）。
- 主要路由分组：
  - `/auth/*`：登录、刷新、登出、验证码、当前用户权限
  - `/iam/*`：用户、角色、权限、部门、审计日志
  - `/workflow/*`：流程定义、实例、我的待办/已办、审批动作
  - `/approval/expenses|leaves|documents/*`：三类单据 CRUD 与提交
  - `/projects/*`：项目、WBS、任务、里程碑、变更、验收
  - `/vendors/*`、`/contracts/*`：供应商与合同
  - `/finance/costs|payments|receipts|budgets/*`
  - `/reports/*`：overview、revenue、cashflow、profit、project-pnl
  - `/files/*`：上传、下载（鉴权 + 有效期签名 URL）

---

## 10. 非功能性设计

| 项 | 指标 / 措施 |
|---|---|
| 性能 | 常规查询 P95 < 500ms；报表 < 2s；支撑 300 并发用户、日增单据 1k 级；索引 + 分页 + 缓存 + 快照 |
| 可用性 | 目标 99.5%；Docker 健康检查 + 自动重启；DB 主备或定时备份（每日全备 + WAL 归档，RPO ≤ 24h，RTO ≤ 4h） |
| 安全 | 见 §3.3；等保二级/三级对齐：身份鉴别、访问控制、安全审计、数据保密性与完整性、备份恢复 |
| 可观测 | 结构化 JSON 日志（含 trace_id）、Prometheus 指标（QPS/延迟/错误率/队列长度）、Grafana 面板、异常告警（邮件/IM 机器人） |
| 可扩展 | 领域模块边界清晰，审批流与报表策略可插拔；后期可按域拆分为独立服务 |
| 兼容性 | 支持 Chrome/Edge 最新两个版本；移动端后续以 H5 适配 |
| 测试 | 单元测试（服务层 ≥ 80%）、接口测试、**权限隔离专项测试**（跨公司/跨部门/跨项目越权用例必须全红转绿） |

---

## 11. 部署设计（Docker）

### 11.1 服务编排
```yaml
services:
  nginx:      # 反向代理 + TLS + 静态资源
  api:        # FastAPI（uvicorn，可 scale 2 副本）
  worker:     # Celery worker（通知、报表、文件处理）
  beat:       # Celery beat（定时任务）
  db:         # postgres:16（数据卷持久化）
  redis:      # redis:7（AOF 持久化）
  minio:      # 对象存储
  prometheus / grafana / loki   # 可观测（可选生产开启）
```
- 网络：自定义 bridge 网络，`db/redis/minio` 不对外暴露端口，仅经 `nginx/api` 访问。
- 配置：`.env` 注入（数据库连接、JWT 密钥、AES 密钥、SMTP），密钥不入库不入镜像；生产使用 Docker secrets 或外部 KMS。
- 镜像：多阶段构建（builder 装依赖 → runtime 精简），非 root 用户运行，`HEALTHCHECK` 探活。
- CI/CD：Git 提交 → Lint（ruff/mypy）→ 测试 → 构建镜像 → 迁移（`alembic upgrade head`）→ 滚动更新 → 冒烟测试。
- 环境：dev / staging / prod 三套，配置隔离，prod 数据脱敏后才可用于测试。

### 11.2 数据初始化
`scripts/seed.py` 预置：公司/部门/角色/权限、审批流程定义（四级默认版）、费用科目字典、供应商分类、示例管理员账号（首次登录强制改密）。

---

## 12. 关键流程时序（文字版）

**报销审批与成本归集**
1. 员工填报销单（选项目、上传发票）→ `POST /approval/expenses` 落库为草稿。
2. 提交 → 创建 `wf_instance`（按金额路由节点）→ 生成 `wf_task`（部门负责人）→ 站内信/邮件通知。
3. 负责人→经理→董事逐级审批；每次动作写 `wf_record`，超时触发催办任务。
4. 董事通过 → 流程 `APPROVED` → 回调 `ExpenseService.on_approved()`：
 写入 `fin_cost_record`（幂等）→ 更新项目成本实绩 → 预算校验（超阈预警）→ 通知财务付款。
5. 财务付款登记 → 更新报销单状态为「已付款」→ 现金流报表数据生效。

**项目收尾与损益**
验收审批通过 → 生成最终计收确认 → 核对收款/付款/报销完整性 → 生成 `fin_project_pnl` 快照 → 项目状态置「已关闭」→ 资料打包归档。

---

## 13. 实施里程碑（建议）

| 阶段 | 内容 | 周期 |
|---|---|---|
| M1 基础平台 | 工程骨架、IAM、数据隔离、审计、文件、字典 | 3 周 |
| M2 审批中心 | 流程引擎 + 报销/请假/文件三表单 | 4 周 |
| M3 项目管理 | 五阶段、WBS/任务/里程碑/变更/验收 | 5 周 |
| M4 供应商与合同 | 档案、资质、合同、关联项目、评价 | 3 周 |
| M5 成本与报表 | 四类单据归集、预算、损益、经营报表 | 4 周 |
| M6 加固与上线 | 安全测试、权限隔离测试、性能优化、部署与培训 | 3 周 |

**主要风险**：审批流条件路由复杂度高（对策：先落地线性四级 + 阈值升级，二期加会签/并行）；成本口径与财务对不齐（对策：需求阶段与财务确认科目表与确认时点，先做口径评审再开发）；历史数据迁移（对策：提供 Excel 模板导入 + 校验报告）。

---

## 14. 附录：核心枚举
- 流程状态：`DRAFT / RUNNING / APPROVED / REJECTED / CANCELED`
- 任务状态：`PENDING / APPROVED / REJECTED / TRANSFERRED / SKIPPED`
- 项目阶段：`LAUNCH / PLAN / PLAN_CONFIRMED / EXECUTE / CLOSE / ARCHIVED`
- 供应商状态：`PENDING / ACTIVE / SUSPENDED / BLACKLIST`
- 费用类型：`TRAVEL / ENTERTAIN / OFFICE / SUBCONTRACT / MATERIAL / OTHER`
- 资金方向：`RECEIVABLE（计收）/ RECEIPT（收款）/ PAYMENT（付款）/ EXPENSE（报销）`

---
