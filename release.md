# EOMS 版本发布记录（Release Notes）

本文件用于记录 EOMS 企业运营管理系统的全部版本变更，作为版本管理与交付验收的基线文档。

## 版本管理约定

### 版本号规则

版本号采用 `V主版本.次版本.修订号`（语义化版本）格式：

| 变更类型 | 版本号变化 | 示例 | 说明 |
| --- | --- | --- | --- |
| 首次发布 / 不兼容重构 | 主版本 +1 | `V1.0.0 → V2.0.0` | 架构或接口不兼容，需要专项升级方案 |
| 功能新增 / 功能变更 | 次版本 +1，修订号归零 | `V1.0.0 → V1.1.0` | 新增页面、接口、业务流程或调整既有功能 |
| 问题修复 / 功能完善 | 修订号 +1 | `V1.1.0 → V1.1.1` | 缺陷修复、文案/交互优化、性能与稳定性改进 |

> 一次发布同时包含新功能与缺陷修复时，按较高优先级取版本号（功能新增优先，即次版本 +1）。

### 记录方式

1. **每次发版必须更新本文件**，不得只在提交信息中体现。
2. **任何一次功能开发、功能变更或问题修复都必须新增版本条目**，不得把多次变更合并进同一个版本记录；同一天多次发版同样按顺序递增。
3. 版本号默认按上面表格递增：功能新增/变更递增第二位（次版本，修订号归零），问题修复/功能完善递增第三位（修订号）。
4. 在文末“版本详情”中**追加**当前版本的完整说明（新版本写在已有内容之后）。
5. 在下方“版本索引”表格**顶部**新增一行，保持最新版本在最上方。
6. 版本详情至少包含：发布日期、版本类型、变更概述、新增功能、变更/优化、问题修复、数据库变更、升级说明、验证情况、已知限制。

### 版本索引

| 版本号 | 发布日期 | 类型 | 摘要 |
| --- | --- | --- | --- |
| V1.2.9 | 2026-11-25 | 问题修复 | 修复 PostgreSQL 营收报表分组错误，兼容演示数据初始化与报表快照生成 |
| V1.2.8 | 2026-11-25 | 问题修复 | 部署前检查 HTTP 与监控端口冲突，明确提示修改 Prometheus/Grafana 端口 |
| V1.2.7 | 2026-11-25 | 问题修复 | MinIO 初始化、备份与恢复改用后端镜像内置 SDK，彻底移除独立 mc 镜像依赖 |
| V1.2.6 | 2026-11-25 | 问题修复 | MinIO 与 mc 固定到可用历史 release，优先国内缓存源并彻底移除 latest 依赖 |
| V1.2.5 | 2026-11-25 | 问题修复 | MinIO 与 mc 改用显式加速镜像并支持多源回退，备份恢复统一复用 Compose 镜像 |
| V1.2.4 | 2026-11-25 | 问题修复 | 支持安全合并现有 daemon.json 的 registry-mirrors，保留原配置、备份并重启 Docker |
| V1.2.3 | 2026-11-25 | 问题修复 | 修复跳过 Docker 安装时未配置镜像加速，导致 MinIO 等镜像从 Docker Hub 拉取超时 |
| V1.2.2 | 2026-11-25 | 问题修复 | 修复 Docker 构建 pip 升级绕过镜像源与下载超时，统一依赖源并启用重试和缓存 |
| V1.2.1 | 2026-11-21 | 问题修复 | 一键部署收尾完善：端口变更同步 origin、IPv6 地址、帮助免 Docker、参数校验与依赖检测 |
| V1.2.0 | 2026-11-20 | 功能新增 | Ubuntu 22.04 一键 Docker 部署、eoms 运维命令、监控组件按需启停与构建加速 |
| V1.1.0 | 2026-11-19 | 功能新增 | 系统管理增强：部门删除、修改密码菜单页、账号开通（随机密码/启停开关）与用户字段清空修复 |
| V1.0.1 | 2026-11-19 | 问题修复 | 修复：RLS 通知、付款幂等与并发、审批入账解耦、报表口径与导出审计、令牌与会话安全加固 |
| V1.0.0 | 2026-11-18 | 首次正式发布 | EOMS 全模块上线：审批、项目、供应商、合同、成本、报表、平台管理、容器化与监控 |

---

## 版本详情

### V1.0.0（2026-11-18）

**版本类型**：首次正式发布（Initial Release）

**变更概述**

依据《企业运营管理系统（EOMS）概要设计文档》完成 P0–P9 全量交付，覆盖后端服务、前端 SPA、数据库迁移、演示数据、自动化测试、容器化部署、监控告警、备份恢复与项目文档。系统支持多公司、多部门、多项目的数据域隔离，具备完整的审批闭环与经营分析能力。

**新增功能**

- **认证与账号安全**
  - JWT 双令牌（access 30 分钟 / refresh 7 天）+ Redis 黑名单，支持令牌轮换。
  - Argon2 密码哈希、图形验证码、登录失败锁定、并发会话上限。
  - 首次登录强制改密、密码有效期与强度校验、密码重置。
  - 登出、会话清理、审计留痕。
- **权限体系**
  - RBAC 角色权限 + 按钮/菜单/API 三级权限点。
  - 数据域：`ALL / COMPANY / DEPT / DEPT_TREE / PROJECT / SELF`，多角色权限取并集并收敛到公司边界。
  - PostgreSQL 行级安全（RLS）兜底，可通过 `EOMS_RLS_ENABLED` 开关。
- **审批中心**
  - 费用报销：草稿、提交、撤回、驳回、取消、财务复核、付款、归档全流程；发票附件校验；成本自动入账。
  - 请假：年假/事假/病假/调休，余额校验、时长精度 0.5 天、时间重叠校验、交接人；审批通过自动扣减余额。
  - 文件审批：制度文件、通知公告、用印申请、合同文本；密级管理；用印/合同类必须上传附件。
  - 流程动作：同意、驳回、转办、加签、会签、撤回、催办、抄送。
  - 四级可配置流程：线性四级 + 金额/天数/密级阈值升级 + 节点内加签/会签（按设计不支持并行分支）。
  - 我的待办、流程实例、审批记录与流转轨迹。
- **项目管理**
  - 项目立项（含审批）、计划确认、执行、收尾、归档全生命周期。
  - WBS、任务、里程碑、项目成员、周报/月报、问题与风险、变更管理。
  - 验收管理（通过/有条件通过/不通过）与验收审批。
  - 项目计划基线、进度/成本偏差、关账校验、归档清单、项目损益。
- **供应商与合同**
  - 供应商准入审批、分级（A/B/C）、状态管理（待准入/合作中/暂停/黑名单）、恢复。
  - 联系人、银行账户、资质证照（到期预警）、项目绑定、年度评价与年度报告。
  - 合同签订、生效、到期、终止；合同到期风险提醒；合同付款关联。
- **成本、资金与预算**
  - 成本台账、成本冲销（负数流水、防重复冲销）、成本口径统一。
  - 付款单（待付款/已付款/已取消）、收款登记与作废、计收确认与取消。
  - 项目预算编制、预算执行状态、阈值预警。
  - 会计期间关账/反关账，关账后业务拦截。
  - 付款/收款/计收/报销与项目、供应商、合同的关联校验。
- **报表中心**
  - 七类报表：经营总览、营收报表、现金流量表、利润表、项目损益表、供应商支出分析、审批效率报表。
  - 支持按期间/项目/客户等维度筛选，Excel/PDF 导出，月度快照生成与查询。
- **平台管理**
  - 用户、角色、权限树、部门树、字典、系统参数、客户主档。
  - 审计日志（操作人、动作、目标、前后快照、IP、trace_id）。
  - 站内通知、未读数、批量已读；邮件通知通过 Outbox + Celery 异步发送。
  - 文件中心：分块上传、sha256 内容寻址去重、鉴权下载、共享对象保护删除。
- **工作台**
  - 年度营收/成本/毛利、待办与未读、项目健康度、经营趋势、风险提醒、最近通知。
- **工程与交付**
  - FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic；Celery worker/beat；Redis；MinIO（本地文件降级）。
  - 请求级事务、幂等键、乐观锁、分布式锁、统一错误码与 `trace_id`。
  - Prometheus 指标、Grafana 面板、Loki/Promtail 日志聚合、5 条告警规则。
  - Docker 多阶段构建、非 root 运行、HEALTHCHECK、Nginx 反代与安全响应头。
  - `scripts/seed.py --reset` 演示数据与 9 类角色账号；`scripts/backup.sh` 数据库与对象存储备份。
  - 交付文档：README、概要设计、用户手册、部署与运维文档、版本发布记录（`release.md`）。
  - GitHub Actions CI：ruff、mypy、单测覆盖率门槛、前端构建、PostgreSQL 迁移、镜像构建与容器冒烟。

**数据库变更**

- 初始迁移 `c463c99b405d`：创建平台、IAM、审批、项目、供应商、合同、成本、报表等全部业务表与索引。
- 迁移 `4053432b8727`：启用 PostgreSQL 行级安全策略（SQLite 下自动跳过）。
- 演示数据由 `scripts/seed.py --reset` 初始化，包含公司、部门、角色、权限、用户、项目、供应商、合同、成本、报表快照等。

**升级说明**

- 首个正式版本，无历史版本升级路径。
- 全新部署：执行 `alembic upgrade head` 后按需执行 `python scripts/seed.py --reset`。
- 生产环境禁止在 `EOMS_ENV=prod` 下执行 `--reset`，演示数据仅用于验收与培训环境。

**验证情况**

- `ruff check .`：通过。
- `mypy app`：104 个源文件无类型错误。
- `pytest tests --cov=app --cov-fail-under=80`：106 项测试全部通过，覆盖率 82.08%。
- 前端 `npm run build`：构建成功，全部页面完成浏览器验收。
- Docker Compose、Prometheus、Grafana、Loki、Promtail 配置完成 YAML/JSON 静态校验。
- 本机未安装 Docker，镜像构建与容器冒烟未在本机执行，已纳入 CI 流水线。

**已知限制**

- 扫码登录、SSO 单点登录仅保留扩展位，未启用。
- 审批流按设计仅支持线性节点与节点内加签/会签，不支持并行分支与条件分支编排。
- 本地无 Redis/MinIO 时自动降级为进程内缓存与本地文件存储，仅适用于开发与测试。
- PDF 导出为服务端基础排版，复杂打印样式需按企业模板二次定制。

**关联文档**

- `README.md`：项目概览、快速开始与运维速查。
- `docs/用户手册.md`：面向业务用户的操作说明。
- `docs/部署文档.md`：面向运维的部署、升级、备份与故障处理。
- `docs/企业运营管理系统（EOMS）概要设计文档.md`：需求与设计基线。

### V1.0.1（2026-11-19）

**版本类型**：问题修复（Bug Fix）

**变更概述**

依据《EOMS 代码审查报告》完成 3 个 P0、11 个 P1、15 个 P2 的全量修复，重点覆盖资金并发正确性、审批与成本归集解耦、报表口径与导出合规、令牌与会话安全、列表性能与纵深防御。不新增业务功能，接口响应结构除认证与报表 `meta` 字段外保持兼容。

**新增功能**

- 成本待补记：新增 `fin_pending_cost` 暂存表、`GET /api/v1/finance/pending-costs` 查询接口与每 10 分钟定时补记任务（`eoms.cost.post_pending`）。
- 会话 Cookie：登录改为下发 HttpOnly 会话 Cookie（`eoms_at` / `eoms_rt`）+ 双提交 CSRF（`eoms_csrf` + `X-CSRF-Token`），响应体不再返回令牌明文。
- 报表 `meta`：报表与导出返回 `meta.source`（`SNAPSHOT` / `REALTIME`），便于区分快照与实时口径。

**变更/优化**

- 付款金额同步由「累加」改为按 Payment 聚合重算；副作用（预算告警、供应商项目回写、合同超付校验）仅在真正新建成本记录时执行。
- 报表在满足条件（公司维度、无项目筛选、单月且期间已关账）时直接读期间快照，审批效率改为 SQL 聚合（不再全量载入 ORM 对象），超时率分母按业务类型任务数计算。
- 项目偏差基线改为取最新版本，避免多次确认计划后指标翻倍。
- 列表接口统一加上限（默认 200、最大 500）：项目验收/基线/变更、供应商评价/合作项目/联系人/银行账户/资质。
- 供应商合同风险、项目预算概览、用户列表改为批量查询，消除 N+1。
- 邮件出箱改为「认领 → 提交 → 逐条发送」，缩短事务持有时间；SMTP 未配置或收件人为空记 `SKIPPED` 并告警。
- MinIO 上传按 `sha256` 判重跳过重复对象；文件下载流改为 `BackgroundTask` 关闭句柄，避免连接泄漏。
- 中间件顺序调整为 `SecurityHeaders → RateLimit → Idempotency → CSRF → Context → CORS`，使 429/409/403 响应带 CORS 头；文件下载独立限流桶（默认 60 次/分钟）。
- 刷新令牌有效期默认由 7 天调整为 3 天。

**问题修复**

- P0-1：通知中心 RLS 作用域下沉到 `get_current_user`，避免旁路查询漏隔离。
- P0-2：付款并发重复入账——`pay_payment` / `cancel_payment` 增加行锁，成本记录按 `record_key` 幂等。
- P0-3：生产密钥缺失时启动即失败（`model_validator` + `docker-compose` 必填校验）。
- P1-1：关账后审批不再整体回滚，成本进入待补记表，反关账或定时任务自动补记。
- P1-2：提交类操作（报销/请假/文档/供应商/发起流程）补行锁与版本校验。
- P1-3：同一报销单重复创建付款单被部分唯一索引拦截，返回业务错误。
- P1-4：分布式锁覆盖到事务提交（`cache.hold` + 会话收尾释放），TTL 取 `max(workflow_lock_seconds, 语句超时 + 30s)`。
- P1-5：报表导出写入 `EXPORT_REPORT` 审计（含筛选条件与导出条数）。
- P1-6：报表按口径走期间快照，未命中才实时聚合。
- P1-7：项目偏差只统计最新基线版本。
- P1-8：审批超时率分母修正为该业务类型的任务数。
- P1-9：刷新令牌原子轮换，重复使用触发重放检测（拉黑令牌、清空该用户会话、写审计）。
- P1-10：PDF 导出对 `Paragraph` 内容做 XML 转义，超 2000 行给出截断提示。
- P1-11：登录页不再预填演示账号密码，演示提示仅在开发构建显示。
- P2-1：项目关闭校验排除已取消任务。
- P2-2：流程定义版本并发改为捕获唯一约束冲突后重试。
- P2-3：`CC` 节点在流程推进时写入抄送记录并发送站内通知，不再被静默跳过。
- P2-4：变更单撤回后置 `CANCELED` 并留审计，避免悬挂。
- P2-5：`record_cost` 并发幂等（`record_key` 冲突回查）。
- P2-6：Excel 导出对以 `= + - @` 等开头的单元格前置 `'`，防公式注入。
- P2-7：邮件出箱长事务与吞错问题修复（见上）。
- P2-8：三处 N+1 查询优化。
- P2-9：明细列表补上限，避免超大响应。
- P2-10：幂等键并发互斥，抢占失败返回 409。
- P2-11：nginx 静态资源与 `index.html` 重复声明安全响应头。
- P2-12：登录与文件下载独立限流桶。
- P2-13：MinIO 重复上传与连接占用。
- P2-14：文档密级影响可见性——非超管仅可见非密级文件与本人创建的密件。
- P2-15：前端令牌改为 HttpOnly Cookie + CSRF（见上）。

**数据库变更**

- 新增迁移 `a1f7c2d9e4b6`：建 `fin_pending_cost` 表（含 `uq_fin_pending_cost_record_key` 与 `(company_id, status, period)` 等索引）、`fin_payment` 部分唯一索引 `uq_fin_payment_expense_active`（`expense_id` 非空且状态为 `PENDING`/`PAID` 时唯一），PostgreSQL 下同时启用 RLS 策略。
- 新增迁移 `b7e3d5a10c48`：建 `wf_instance` 部分唯一索引 `uq_wf_instance_biz_running`（`company_id, biz_type, biz_id`，仅约束 `status='RUNNING'`）。

**升级说明**

1. 备份数据库后执行 `alembic upgrade head`（依次应用 `a1f7c2d9e4b6`、`b7e3d5a10c48`）。
2. `wf_instance` 部分唯一索引要求存量不存在同一业务单据的多条 `RUNNING` 实例。排查 SQL：
   `SELECT company_id, biz_type, biz_id, count(*) FROM wf_instance WHERE status='RUNNING' GROUP BY 1,2,3 HAVING count(*) > 1;`
   若有结果，需先人工关停多余实例，否则迁移会失败。
3. 同理由 `fin_payment` 部分唯一索引约束的存量重复付款单需先行处理（保留一条、其余置 `CANCELED`）。
4. 启用 Cookie 会话后生产必须通过 HTTPS 访问，并设置 `EOMS_COOKIE_SECURE=true`；反向代理需透传 `X-Forwarded-Proto`，否则安全 Cookie 不会被浏览器回传。
5. 仍使用 `Authorization: Bearer` 的脚本与第三方集成不受影响（CSRF 仅对 Cookie 来源生效），建议逐步迁移至 Cookie。

**验证情况**

- `ruff check .`、`mypy app`、`pytest tests --cov=app --cov-fail-under=80`、`cd web && npm run build` 全部通过。
- 新增 `tests/test_13_hardening.py` 覆盖：关账后待补记成本、付款幂等、部分唯一索引、导出审计、超时率分母、基线版本、关闭校验、PDF 转义、Cookie/CSRF、刷新令牌重放、CC 节点。
- 本机无 Docker：nginx 头继承、PG RLS、MinIO 判重需在 CI/预发复验。

**已知限制**

- 报表快照仅在「公司维度 + 单月已关账」等条件命中时生效，带项目筛选或自定义分组仍走实时聚合。
- 待补记成本依赖 Celery Beat 与 Redis，纯单机无 Celery 环境需在反关账时手工触发补记。
- 密级隔离只作用于文件审批列表与详情，工作流待办仍按流程可见性展示。

**关联文档**

- `README.md`：认证方式已更新为 Cookie + CSRF。
- `docs/用户手册.md`：补充重新登录提示、成本待补记、文档密级可见性说明。
- `docs/部署文档.md`：补迁移顺序、HTTPS 与反代要求。

---

### V1.1.0（2026-11-19）

**版本类型**：功能新增（Feature）

**变更概述**

面向「系统管理」模块补齐管理闭环：组织部门支持删除并做占用校验，系统管理下新增「修改密码」菜单页，账号开通增加随机初始密码、复制与列表启停开关；同时修复用户编辑无法清空部门/岗位/联系方式的问题。权限范围按评审结论保持「仅系统管理员可见」。

**新增功能**

- **组织部门删除**
  - 部门树操作列新增「删除」，二次确认后删除并刷新部门树与下拉选项。
  - 新增接口 `DELETE /api/v1/iam/depts/{dept_id}`（权限 `system:dept`）。
  - 占用校验：存在子部门或仍有用户归属时拒绝删除并提示具体数量，避免组织树断链与用户失联。
  - 删除成功写入 `DELETE_DEPT` 审计（含删除前部门快照）。
- **系统管理 →「修改密码」页**
  - 新增路由 `/system/password` 与菜单权限点 `system:password`，页面展示账号信息（账号/姓名/部门/角色/最近登录/密码状态）。
  - 改密表单含强度指示、与原密码相同校验、两次输入一致校验；成功后清空本地会话并跳转登录页。
  - 与头像下拉「修改密码」复用同一后端接口 `PUT /api/v1/auth/password`。
- **账号开通增强（用户管理）**
  - 初始密码支持一键「随机」生成（覆盖大写、小写、数字、符号四类）与「复制」到剪贴板（含非 HTTPS 环境降级方案）。
  - 列表状态改为开关，可直接启用/停用账号，携带 `version` 乐观锁，冲突提示刷新后重试；停用当前登录账号由后端拦截。
  - 页面文案调整为「账号开通」语义，重置密码入口保留并显性展示。

**变更/优化**

- 用户菜单图标白名单补充 `Lock`，避免新菜单回退为默认文件夹图标。
- 部门管理操作列宽度与按钮布局调整，容纳「新增子部门 / 编辑 / 删除」。

**问题修复**

- `update_user` 对 `dept_id / position / email / phone` 由 `is not None` 改为「是否显式传参」判断：传 `null` 现在可以真正清空部门、岗位、邮箱、手机号（原实现导致前端清空无效，并会阻塞部门删除）。

**数据库变更**

- 新增迁移 `c8d21f4b7a53`：`sys_permission` 增加菜单 `system:password`（名称「修改密码」，父节点 `menu:system`，路径 `/system/password`，组件 `system/Password`，图标 `Lock`），并为 `ADMIN` 角色授权。脚本幂等：记录已存在则跳过，权限点未初始化（空库）时跳过并由 `scripts/seed` 负责整体写入。

**升级说明**

1. 备份数据库后执行 `alembic upgrade head`（应用 `c8d21f4b7a53`）。
2. 若数据库由脚本初始化且未纳入 Alembic 管理，可重跑 `python -m scripts.seed`（幂等）补齐权限点，或按迁移内容手工插入。
3. 默认仅 `ADMIN` 获得「修改密码」菜单；如需其他角色使用，请到「角色权限」为其勾选 `system:password`。
4. 部门删除为物理删除，前置条件是先清理子部门并迁移成员归属；相关操作均有审计可追溯。

**验证情况**

- `ruff check .`、`mypy app`、`pytest tests --cov=app --cov-fail-under=80`（123 passed，覆盖率 82.28%）、`cd web && npm run build` 全部通过。
- 新增 `tests/test_14_system_admin.py` 覆盖：部门删除的子部门/成员拦截与审计、ADMIN 菜单包含「修改密码」、账号停用后无法登录、启用后恢复登录、改密后旧密码失效。
- 迁移在本地演示库实际执行成功（`c8d21f4b7a53` 为 head），权限点与角色授权已落库校验。

**已知限制**

- 「修改密码」菜单项按评审结论仅对系统管理员（`ADMIN`）可见；普通用户的改密入口仍为头像下拉。
- 部门删除为物理删除且不级联，不做批量迁移工具，组织大调整需逐级操作。
- 前端交互仅通过生产构建校验，浏览器端点击回归需在联调环境补验。

**关联文档**

- `docs/用户手册.md`：10.1 用户管理（账号开通）、10.3 组织架构（删除约束）、10.7 修改密码，以及常见错误新增「该部门下还有 N 个子部门/用户」。

---

### V1.2.0（2026-11-20）

**版本类型**：功能新增（Feature）

**变更概述**

面向 Ubuntu 22.04 服务器交付一键 Docker 部署能力：新增 `deploy/install.sh` 自动安装 Docker、生成随机密钥、构建并启动、健康检查与演示数据初始化；新增 `eoms` 运维命令覆盖启停、日志、升级、备份恢复与监控开关；监控组件改为 Compose profile 按需启停。

**新增功能**

- **一键部署脚本 `deploy/install.sh`**
  - 自动检测 Ubuntu/Debian，安装 Docker Engine、Buildx 与 Compose v2。
  - `--cn-mirror` 使用阿里云 Docker 源，并配置 Docker 镜像加速与 pip/npm 国内源。
  - 自动生成 `.env` 并随机生成 JWT、AES、PostgreSQL、MinIO、Grafana 密钥，权限 `600`；重复执行不覆盖现有密钥。
  - 自动推断 `EOMS_PUBLIC_ORIGIN`、`EOMS_TRUSTED_HOSTS`、`EOMS_COOKIE_SECURE`，支持 `--origin https://...` 适配外部 TLS 网关。
  - 构建镜像、启动服务、轮询 `/healthz`，首次部署默认初始化演示数据。
  - 自动安装 `/usr/local/bin/eoms`。
- **运维命令 `deploy/eoms.sh`**
  - `status / info / health / doctor` 状态与诊断。
  - `up / down / start / stop / restart / logs / shell / dbshell` 日常运维。
  - `update` 支持升级前自动备份、Git 拉取、重建与滚动启动。
  - `backup / restore` 封装数据库与 MinIO 备份恢复，恢复前校验 sha256。
  - `monitoring enable|disable|status` 动态启停监控组件。
  - `seed`、`config`、`destroy` 等辅助命令。

**变更/优化**

- `docker-compose.yml` 为 Prometheus/Grafana/Loki/Promtail 增加 `monitoring` profile，默认仍随一键部署启动，`--minimal` 可关闭。
- 后端与前端 Dockerfile 增加 BuildKit 缓存挂载，并支持 `PIP_INDEX_URL`、`NPM_REGISTRY` 构建参数加速依赖安装。
- 新增 `.gitattributes`，保证 Shell 脚本在 Windows 检出后仍以 LF 换行执行。
- CI 增加部署脚本语法与 Compose 配置校验。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 已有部署可直接拉取代码后执行 `eoms update`，或 `docker compose build && docker compose up -d`。
2. 已有 `.env` 不会被一键脚本覆盖；如需启用监控 profile，确认 `.env` 含 `COMPOSE_PROFILES=monitoring` 或执行 `eoms monitoring enable`。
3. 公网部署请配置 HTTPS，并使用 `--origin https://域名` 或手动设置 `EOMS_COOKIE_SECURE=true`。

**验证情况**

- `bash -n deploy/install.sh`、`bash -n deploy/eoms.sh`、`bash -n scripts/backup.sh` 均通过。
- 使用模拟 Docker CLI 验证 `.env` 密钥生成、重复执行幂等、端口/域名/HTTPS 参数、监控开关与恢复流程。
- CI 新增部署资产校验任务：Shell 语法、默认与 `--minimal` 两种 Compose 配置。
- 真实 Docker 镜像构建与容器启动待在 Ubuntu 22.04 服务器复核。

**已知限制**

- 一键脚本不自动申请 TLS 证书；HTTPS 建议由云负载均衡/独立网关终止，或按部署文档手工配置。
- 国内镜像源可用性随第三方服务变化，失败时可在 `.env` 中改回官方源。
- `eoms restore` 会停止写入，恢复时长取决于备份体积，需在维护窗口执行。

**关联文档**

- `README.md`：Docker 部署章节更新为一键部署 + 手动部署 + `eoms` 命令。
- `docs/部署文档.md`：新增「0. 一键部署」、监控 profile 说明与命令速查。

### V1.2.1（2026-11-21）

**版本类型**：问题修复 / 功能完善（Patch）

**变更概述**

对 V1.2.0 一键部署能力做收尾完善，修复重复部署时端口与对外地址不一致的问题，补齐 IPv6、帮助信息与参数校验，并改进系统依赖检测，降低首次部署失败率。

**问题修复**

- **端口变更后 origin 不同步**：已有 `.env` 时执行 `--port` 修改端口，`EOMS_PUBLIC_ORIGIN` 仍指向旧端口，导致浏览器 CORS 校验失败。现自动将 HTTP 直连地址同步为新端口；`https://` 外部网关地址保持不变，不会被误加端口。
- **IPv6 公网地址格式**：自动探测到 IPv6 时按规范生成 `http://[地址]:端口`，避免 URL 解析失败。
- **`eoms` 帮助不可用**：未安装 Docker 或缺少 `.env` 时执行 `eoms help` 会直接报错。现帮助信息在任何环境均可查看，且无参数执行等同于 `help`。

**变更/优化**

- 依赖按需安装：`curl`、`python3` 改为检测命令是否存在后再安装，兼容精简系统镜像。
- 参数校验增强：`--origin` 必须是 `http(s)://` 开头且不含路径；`--domain` 禁止携带 `http://`、`https://` 前缀与端口。
- 安装完成后提示补充「非 root 用户需重新登录以生效 docker 组」，并输出详细部署文档位置。

**数据库变更**

- 无数据库迁移。

**升级说明**

- 本版本仅涉及部署脚本，已部署实例无需重建镜像；拉取代码后重新执行 `sudo bash deploy/install.sh` 即可应用脚本修复，现有 `.env` 与数据卷不受影响。
- 若曾用 `--port` 改过端口，可执行一次安装脚本自动校正 `EOMS_PUBLIC_ORIGIN`，或手动修改 `.env` 后 `eoms up`。

**验证情况**

- `bash -n` 校验 `deploy/install.sh`、`deploy/eoms.sh`、`scripts/backup.sh`、`docker/entrypoint.sh` 全部通过。
- WSL 模拟 Docker CLI 验证：连续执行 `--port 18098 → 18099` 时 origin 正确同步；切换到 `--origin https://eoms.example.com` 后再改端口，HTTPS origin 保持不变；`eoms help`、`eoms info`、`eoms health` 正常。
- `git diff --check` 无空白错误，`.gitattributes` 保证脚本 LF 换行。

**已知限制**

- 本机无 Docker，真实镜像构建与容器启动仍需在 Ubuntu 22.04 服务器或 CI 复核。
- 端口同步仅作用于 `http://` 直连地址；HTTPS 由外部网关终止时，对外端口仍需在网关侧同步调整。

**关联文档**

- `README.md`：一键部署参数与 `eoms` 命令说明。
- `docs/部署文档.md`：一键部署与排障章节。

---

### V1.2.2（2026-11-25）

**版本类型**：问题修复 / 功能完善（Patch）

**变更概述**

修复 Docker 镜像构建过程中 pip 自身升级未使用配置镜像源、直连 PyPI 下载超时的问题。后端所有 pip 下载统一遵循 `PIP_INDEX_URL`，并增加网络超时、自动重试与有效的 BuildKit 缓存，降低国内或弱网环境下的部署失败率。

**问题修复**

- **pip 升级绕过镜像源**：原 `pip install --upgrade pip` 未传入 `--index-url`，即使执行 `--cn-mirror` 仍会访问官方 PyPI。现改为 `python -m pip install --upgrade --index-url "$PIP_INDEX_URL" pip`，与项目依赖安装使用同一镜像源。
- **依赖下载读取超时**：针对 `files.pythonhosted.org` 等源出现 `ReadTimeoutError` 导致构建中断的问题，增加 pip 网络重试与更合理的读取超时。

**变更/优化**

- 增加 `PIP_DEFAULT_TIMEOUT=120` 与 `PIP_RETRIES=5`，适配慢速网络并允许短暂中断自动恢复。
- 移除 `PIP_NO_CACHE_DIR=1`，使 `--mount=type=cache,target=/root/.cache/pip` 生效，重复构建可复用已下载依赖。
- pip 命令统一使用 `python -m pip`，避免虚拟环境中可执行文件解析差异。
- 取消 `.gitignore` 对 `docs/` 的整体忽略，确保部署与运维文档可随版本提交和同步。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `docker/Dockerfile`；仅涉及后端镜像构建，无需修改数据库或业务配置。
2. 国内服务器可重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`，脚本会保留现有 `.env` 密钥并写入国内 pip/npm 源。
3. 已手动配置 `.env` 中 `PIP_INDEX_URL` 的环境，可执行 `docker compose build api` 后运行 `docker compose up -d api worker beat` 应用新镜像。

**验证情况**

- 根据部署失败日志确认根因为 pip 升级阶段读取 PyPI 超时，并核对 Dockerfile 中镜像源参数未作用于 pip 自身升级。
- `git diff --check` 通过，Dockerfile 修改无空白错误。
- 完整镜像构建与容器启动需在服务器或 CI 网络环境复验。

**已知限制**

- 第三方镜像源可用性由外部服务决定，持续断网时重试无法替代网络修复。
- 超时与重试会延长构建失败前的等待时间；网络长期不可达时应先检查 DNS、代理与出站策略。

**关联文档**

- `README.md`：补充 Docker 构建依赖源说明、pip 超时排障与版本维护约定。
- `docs/部署文档.md`：适用版本更新为 V1.2.2，补充构建源、超时重试与缓存说明。

---

### V1.2.3（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复一键部署脚本在同时指定 `--skip-docker-install` 与 `--cn-mirror` 时未配置 Docker 镜像加速的问题。已安装 Docker 的服务器现在也会应用 `registry-mirrors`，避免 MinIO、PostgreSQL、Grafana 等基础镜像因 Docker Hub 访问超时而中断部署。

**问题修复**

- **镜像加速分支被跳过**：原 `configure_docker_mirror` 仅在安装 Docker 的分支中调用，使用 `--skip-docker-install` 时不会执行。现将其移到 Docker 安装条件分支之后统一调用。
- **Docker Hub 拉取超时**：修复后，国内网络执行 `--skip-docker-install --cn-mirror` 时会先写入 `/etc/docker/daemon.json` 并重启 Docker，再构建和拉取镜像。

**变更/优化**

- 脚本参数说明与部署文档明确：`--skip-docker-install` 只跳过安装，不跳过 `--cn-mirror` 的镜像加速配置。
- 文档补充 Docker Hub 拉取超时的识别与重试命令。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `deploy/install.sh`，无需重建已成功的业务镜像。
2. 在服务器重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`；脚本会配置镜像加速、复用构建缓存并继续拉取基础镜像。
3. 若服务器已有 `/etc/docker/daemon.json`，脚本会提示跳过自动配置，需人工合并 `registry-mirrors` 后执行 `sudo systemctl restart docker`。

**验证情况**

- 根据部署日志确认业务镜像已构建成功，失败发生在 `minio/mc:latest` 拉取阶段，错误为 `registry-1.docker.io` 请求超时。
- 核对脚本调用路径，确认原实现导致 `--skip-docker-install` 分支跳过 `configure_docker_mirror`。
- `bash -n deploy/install.sh` 与 `git diff --check` 通过。

**已知限制**

- 第三方 Docker 镜像加速服务可用性由外部服务决定。
- 已有 `daemon.json` 时不会自动覆盖，需人工合并镜像地址；脚本会输出提示。

**关联文档**

- `README.md`：补充参数组合说明与 Docker Hub 拉取超时排障。
- `docs/部署文档.md`：适用版本更新为 V1.2.3，补充已安装 Docker 场景的镜像加速说明。

---

### V1.2.4（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

完善 Docker 镜像加速配置：服务器已有 `/etc/docker/daemon.json` 时不再直接跳过，而是安全合并 `registry-mirrors`。原有其他配置与已有镜像地址均保留，新增地址自动去重，修改前生成带时间戳的备份，写入后重启并检查 Docker 服务。

**问题修复**

- **已有 daemon.json 导致加速不生效**：原实现检测到文件存在就退出，国内服务器仍直连 Docker Hub。现使用 Python 解析并合并 JSON，不再跳过现有配置。
- **配置覆盖风险**：新实现只更新 `registry-mirrors` 字段，保留其他 Docker daemon 配置、文件权限与已有镜像地址；非法 JSON 或字段类型错误时终止且不覆盖原文件。

**变更/优化**

- 合并前自动备份为 `/etc/docker/daemon.json.eoms-backup-时间戳`。
- 使用临时文件原子替换，避免写入中断产生半截配置。
- 配置未变化时跳过重启；配置变化后执行 `systemctl restart docker` 并通过 `docker info` 验证服务恢复。
- 将 `python3` 依赖检查前移，确保执行 JSON 合并前可用。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `deploy/install.sh`。
2. 在服务器重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`。
3. 脚本会合并现有 `/etc/docker/daemon.json`、输出备份路径、重启 Docker，并继续构建或拉取镜像。
4. 如合并失败，检查终端错误并修复 `daemon.json`；原文件不会被覆盖，备份文件可用于人工恢复。

**验证情况**

- 根据部署日志确认脚本已进入镜像加速流程，但因 `/etc/docker/daemon.json` 已存在而跳过，随后 Docker Hub 拉取仍超时。
- 核对合并逻辑覆盖保留其他字段、镜像地址去重、备份、原子写入与重启验证。
- `bash -n deploy/install.sh` 与 `git diff --check` 通过。

**已知限制**

- 第三方镜像加速服务可用性由外部服务决定。
- 服务器实际 Docker 重启与镜像拉取需在部署环境复验。

**关联文档**

- `README.md`：更新 Docker Hub 超时排障版本与 daemon.json 自动合并说明。
- `docs/部署文档.md`：适用版本更新为 V1.2.4，补充自动合并、备份与失败处理说明。

---

### V1.2.5（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复 Docker daemon 镜像加速已生效但 MinIO 仍回退 Docker Hub 的问题。国内部署现在会显式拉取 MinIO 与 `mc` 的完整加速镜像地址，按多个加速源依次回退，并将成功地址写入 `.env`。备份与恢复也改为通过 Compose 运行 `minio-init`，统一使用已配置的 `mc` 镜像。

**问题修复**

- **MinIO 仍回退 Docker Hub**：原 Compose 使用 `minio/minio:latest`、`minio/mc:latest`，加速源未命中时会回退官方仓库。现改为 `MINIO_IMAGE`、`MINIO_MC_IMAGE` 可配置，并在 `--cn-mirror` 下显式选择加速地址。
- **备份恢复再次拉取官方 mc**：原脚本硬编码 `minio/mc:latest`。现统一使用 `docker compose run ... minio-init`，复用部署时选定的镜像。

**变更/优化**

- 支持 `docker.m.daocloud.io`、`docker.1ms.run`、`dockerproxy.net` 三个显式加速源依次回退。
- 优先复用本地镜像或 `.env` 中自定义的完整镜像地址；自定义地址失败后再尝试默认加速源。
- 成功选择后写入 `.env` 并导出当前进程变量；全部失败时终止，并提示人工设置完整镜像地址。
- `.env.docker.example` 增加 `MINIO_IMAGE`、`MINIO_MC_IMAGE` 配置项。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `docker-compose.yml`、`.env.docker.example`、`deploy/install.sh`、`deploy/eoms.sh` 与 `scripts/backup.sh`。
2. 在服务器重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`。
3. 脚本会在业务镜像构建后显式拉取 MinIO 与 `mc`，输出选中的完整镜像地址并继续启动。
4. 若全部加速源失败，在 `.env` 设置 `MINIO_IMAGE` 或 `MINIO_MC_IMAGE` 为可用完整地址后重试。

**验证情况**

- 根据部署日志确认 `daemon.json` 已成功合并、备份并重启，但 MinIO 仍请求 `registry-1.docker.io` 且连接被拒绝。
- 核对 Compose、安装、备份与恢复路径均已参数化或复用 `minio-init`。
- 三个 Shell 脚本的 `bash -n`、Compose YAML 解析与 `git diff --check` 通过；本机未安装 Docker，完整 Compose 校验与镜像拉取需在服务器执行。

**已知限制**

- 第三方镜像加速源可能缓存滞后或暂时不可用，脚本会依次回退。
- 加速源中的镜像 tag 与 Docker Hub 是否同步取决于第三方服务。

**关联文档**

- `README.md`：更新 MinIO 拉取排障与恢复命令。
- `docs/部署文档.md`：适用版本更新为 V1.2.5，补充显式镜像、多源回退与配置项说明。

---

### V1.2.6（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复 MinIO `latest` 镜像从各加速源返回 `denied` 或 `manifest unknown` 导致部署中断的问题。MinIO 与 `mc` 改为固定历史 release，优先拉取仍可访问的国内缓存镜像，并保留多个回退源。Compose 与环境模板默认值同步固定版本。

**问题修复**

- **latest 已不可用**：DaoCloud 返回 denied，1ms 与 dockerproxy 返回 manifest unknown。现固定 MinIO `RELEASE.2025-09-07T16-13-09Z`、`mc` `RELEASE.2025-08-13T08-35-41Z`。
- **候选源缺少可用缓存**：新增轩辕镜像与阿里云 FastGPT 缓存源作为优先候选，后续仍回退 DaoCloud、1ms、dockerproxy 与 Quay。
- **旧环境仍引用 latest**：安装脚本将 `minio/minio:latest`、`minio/mc:latest` 识别为旧默认值，本地无镜像时不再直连该失效 tag。

**变更/优化**

- `docker-compose.yml` 与 `.env.docker.example` 默认镜像改为固定 release。
- 成功后仍将完整镜像地址写入 `.env`，备份与恢复继续通过 Compose 复用。
- 文档明确上游历史版本停止维护，生产环境应规划迁移到持续维护的 S3 兼容实现。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `docker-compose.yml`、`.env.docker.example` 与 `deploy/install.sh`。
2. 在服务器重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`。
3. 脚本将优先尝试 `docker.xuanyuan.run` 的固定 release 镜像，成功后写入 `.env` 并继续启动。
4. 若全部候选失败，在 `.env` 设置 `MINIO_IMAGE` 或 `MINIO_MC_IMAGE` 为可用完整地址后重试。

**验证情况**

- 根据部署日志确认三个 `latest` 加速源均失败，错误分别为 denied 与 manifest unknown。
- 核对固定 release、候选顺序、旧 latest 兼容判断与 Compose 默认值。
- 三个 Shell 脚本的 `bash -n`、Compose YAML 解析与 `git diff --check` 通过；实际拉取需在服务器复验。

**已知限制**

- 固定 release 为上游停止维护前的历史版本，第三方缓存源不保证长期可用。
- 生产环境应评估迁移到持续维护的 S3 兼容对象存储，并先验证数据兼容性与备份恢复。

**关联文档**

- `README.md`：更新固定版本说明与 MinIO 镜像失败排障。
- `docs/部署文档.md`：适用版本更新为 V1.2.6，补充固定 release、缓存源与维护风险说明。

---

### V1.2.7（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复 MinIO 服务镜像已可拉取、但独立 `minio/mc` 客户端镜像从所有候选源返回 unauthorized、denied 或 manifest unknown，导致部署在启动前中断的问题。bucket 初始化、对象备份与恢复改为复用已构建的 `eoms-api` 镜像和项目已有的 Python MinIO SDK，不再依赖额外客户端镜像。

**问题修复**

- **独立 mc 镜像不可用**：轩辕镜像要求登录，DaoCloud 返回 denied，1ms、dockerproxy 返回 manifest unknown，Quay 返回 unauthorized。现删除 `MINIO_MC_IMAGE` 拉取与运行依赖。
- **启动被客户端镜像阻断**：`minio-init` 改为 `eoms-api:1.0.0`，通过 `/app/scripts/minio_storage.py init` 等待 MinIO 就绪并幂等创建 bucket。
- **备份恢复连带失败**：`scripts/backup.sh` 与 `deploy/eoms.sh` 改为调用同一 Python 脚本的 `backup`、`restore` 子命令，不再使用 `mc alias` 或 `mc mirror`。
- **恢复路径穿越风险**：恢复对象名拒绝绝对路径、`..` 与反斜杠，并校验解析后的目标仍位于备份目录内。

**新增功能**

- 无新增业务功能；仅新增部署与运维辅助能力。

**变更/优化**

- 新增 `scripts/minio_storage.py`，复用 `minio>=7.2` SDK，支持初始化、递归备份与递归恢复。
- 备份保留对象相对路径作为 key，恢复自动创建父目录；空 bucket 生成空备份目录。
- 一次性管理容器以 root 运行，确保可读取历史备份挂载目录；业务 API、worker、beat 仍保持非 root 运行。
- 国内部署优先使用已在服务器验证可拉取的阿里云 FastGPT MinIO 缓存源，其余候选源继续回退。
- 旧 `.env` 中的 `MINIO_MC_IMAGE` 不再生效，可从模板和配置说明中移除。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `docker-compose.yml`、`deploy/install.sh`、`scripts/backup.sh`、`deploy/eoms.sh`、`scripts/minio_storage.py` 与 `.env.docker.example`。
2. 在服务器重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`。
3. 安装脚本只选择 MinIO 服务镜像；随后 `minio-init` 复用刚构建的后端镜像完成 bucket 初始化。
4. 已有 `.env` 可保留 `MINIO_MC_IMAGE`，但新编排不会读取；建议人工删除该 obsolete 配置项。

**验证情况**

- 根据部署日志确认阿里云 FastGPT 的 MinIO 固定 release 已成功拉取，失败仅发生在所有 `mc` 候选镜像。
- 新增单元测试覆盖对象 key 生成、递归备份、恢复目录创建与路径穿越拒绝。
- 执行 Shell 语法、Python 编译、全量 Ruff、完整 Pytest、Compose YAML 解析与 `git diff --check`；完整服务启动和真实 MinIO 备份恢复仍需服务器复验。

**已知限制**

- 固定 MinIO release 为上游停止维护前的历史版本，第三方缓存源不保证长期可用。
- 新备份恢复不保留空目录标记对象之外的本地空目录，也不保留对象自定义元数据；EOMS 业务文件不受影响。
- 生产环境应评估迁移到持续维护的 S3 兼容对象存储，并先验证数据兼容性与备份恢复。

**关联文档**

- `README.md`：更新目录结构、V1.2.7 说明、对象恢复命令与 MinIO 客户端镜像排障。
- `docs/部署文档.md`：适用版本更新为 V1.2.7，更新组件表、备份恢复步骤与配置说明。

---

### V1.2.8（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复监控端口被其他应用占用时，安装脚本直到 `docker compose up` 才报 `address already in use`，导致业务镜像构建和多个服务启动完成后才中断的问题。部署前现在会校验 HTTP、Prometheus 与 Grafana 端口，并区分 EOMS 已有容器与其他进程占用。

**问题修复**

- **监控端口冲突发现过晚**：原脚本只检查 `HTTP_PORT`，未检查 `PROMETHEUS_PORT` 与 `GRAFANA_PORT`。现均在构建前检查并终止，给出对应配置项。
- **端口归属判断不准确**：原实现只要任意 Docker 容器占用端口就放行。现仅允许 `com.docker.compose.project=eoms` 的已有容器占用对应端口。
- **端口配置相互冲突**：新增监控端口与 HTTP 端口、Prometheus 与 Grafana 端口之间的重复校验，并校验数字及 `1-65535` 范围。

**变更/优化**

- 从 `.env` 读取监控端口并导出到当前部署进程，确保预检、Compose 与终端提示使用同一配置。
- 端口冲突提示明确区分 HTTP 与监控组件：HTTP 使用 `--port`，监控端口修改 `.env`；不需要监控时可使用 `--minimal`。
- 环境模板、README 与部署文档补充端口修改及 `GRAFANA_ROOT_URL` 同步说明。

**数据库变更**

- 无数据库迁移。

**升级说明**

1. 同步更新 `deploy/install.sh`、`.env.docker.example` 与相关文档。
2. 在服务器 `.env` 设置例如 `PROMETHEUS_PORT=19090`、`GRAFANA_PORT=13000`，并同步 `GRAFANA_ROOT_URL=http://localhost:13000`。
3. 重新执行 `sudo bash deploy/install.sh --skip-docker-install --cn-mirror`。
4. 若端口仍冲突，使用 `ss -ltnp` 定位占用进程；不需要监控组件时可改用 `--minimal`。

**验证情况**

- 根据部署日志确认失败原因为 `127.0.0.1:9090` 已被其他应用占用，MinIO 初始化及 API 健康检查已成功。
- 执行 Shell 语法、Compose YAML 解析与 `git diff --check`；端口冲突实际提示需在服务器复验。

**已知限制**

- 脚本依赖 `ss` 检查监听端口；若系统未安装 `ss`，仍由 Docker 在启动阶段报告绑定失败。
- 脚本不会自动选择空闲端口，避免与现有运维约定和防火墙规则冲突。

**关联文档**

- `README.md`：补充 V1.2.8 端口预检说明与 `address already in use` 排障。
- `docs/部署文档.md`：适用版本更新为 V1.2.8，补充监控端口修改示例与冲突处理。

---

### V1.2.9（2026-11-25）

**版本类型**：问题修复（Bug Fix）

**变更概述**

修复生产 PostgreSQL 执行 `eoms seed` 或生成报表快照时，营收报表查询报 `GroupingError` 的问题。原查询始终选择期间、项目、客户三个维度，却只按用户选择的一个维度分组；SQLite 的宽松行为掩盖了缺陷，PostgreSQL 会直接拒绝执行。现查询仅选择并分组当前维度，确保初始化、实时报表、导出与快照使用同一严格口径。

**新增功能**

- 无新增业务功能。

**变更/优化**

- `revenue_report` 按 `period / project / customer` 动态选择查询列与 `GROUP BY` 列；非法维度统一回退为 `period`，响应中的 `group_by` 与实际分组保持一致。
- 分组响应仅填充当前维度，其余维度字段返回 `null`，避免把任意一行的未分组值误当成整个分组的属性。
- 新增三种维度的聚合结果回归测试，以及 PostgreSQL 方言 SQL 编译测试，校验查询列与分组列一致。
- PostgreSQL CI 在迁移校验后增加演示数据初始化与报表快照生成步骤，覆盖真实数据库的分组约束。

**问题修复**

- **`eoms seed` 中断**：修复 `column "fin_revenue_confirm.project_id" must appear in the GROUP BY clause or be used in an aggregate function`。
- **报表快照任务中断**：`generate_company_snapshots` 调用同一营收指标，现可在 PostgreSQL 正常生成公司级快照。
- **维度语义不稳定**：按项目或客户分组时不再返回 SQLite 任意选取的期间、项目或客户字段，也不再产生同一维度的重复分组行。

**数据库变更**

- 无数据库迁移，仅修改查询与统计逻辑。

**升级说明**

1. 同步更新 `app/services/report/metrics.py`、`tests/test_01_reports.py`、`.github/workflows/ci.yml` 与相关文档。
2. 在服务器重新执行部署脚本并保持原有端口及访问地址参数，重建 API、worker、beat 所使用的后端镜像。
3. 初始化脚本使用事务，上次失败会回滚本次写入；升级后直接执行 `eoms seed --yes`，无需执行 `--reset` 或数据库迁移。
4. 打开营收报表分别切换期间、项目、客户维度，并生成一次报表快照，确认均返回 200。

**验证情况**

- 报表专项测试 17 项通过，覆盖三种维度的聚合数量、金额、笔数、键唯一性与 PostgreSQL 查询结构。
- 完整 Pytest 137 项通过，全量 Ruff 通过，Mypy 检查 106 个源文件无错误。
- Python 编译、CI/Compose YAML 解析与 `git diff --check` 通过。
- 本机未安装 Docker/PostgreSQL，真实 PostgreSQL 执行由新增 CI 步骤覆盖；服务器升级后的 `eoms seed` 仍需复验。

**已知限制**

- 本地自动化测试仍使用 SQLite，不能仅靠单测执行 PostgreSQL 的全部约束；必须保留 PostgreSQL CI 或等效集成测试。
- 历史错误快照若已部分写入，应重新生成覆盖；本次失败路径会回滚，不涉及存量数据修复。

**关联文档**

- `README.md`：补充 V1.2.9 说明、PostgreSQL CI 覆盖与 `GroupingError` 排障。
- `docs/部署文档.md`：适用版本更新为 V1.2.9，补充初始化失败后的升级与重试说明。
