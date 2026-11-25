# EOMS 企业运营管理系统

一体化企业运营管理平台：审批流、项目管理、供应商与合同、成本与预算、经营报表、平台管理。
后端 FastAPI + SQLAlchemy 2.0 + Celery，前端 Vue 3 + Element Plus，生产环境以 Docker Compose 编排。

设计依据：[`docs/企业运营管理系统（EOMS）概要设计文档.md`](docs/企业运营管理系统（EOMS）概要设计文档.md)

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [用户手册](docs/用户手册.md) | 按角色与页面说明登录、审批、项目、供应商、财务、报表与系统管理操作 |
| [部署与运维文档](docs/部署文档.md) | 环境准备、配置、构建启动、HTTPS、升级回滚、备份恢复、监控排障与上线清单 |
| [版本发布记录](release.md) | 版本号规则、版本索引与每个版本的变更说明 |

---

## 1. 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端框架 | FastAPI、Pydantic v2、SQLAlchemy 2.0（同步 Session）、Alembic |
| 数据库 | PostgreSQL 16（生产）/ SQLite（本地降级） |
| 缓存与队列 | Redis 7、Celery（worker / beat） |
| 文件存储 | MinIO（生产）/ 本地文件系统（开发） |
| 前端 | Vue 3、Vite 6、Element Plus、Pinia、Vue Router、ECharts |
| 可观测 | Prometheus、Grafana、Loki + Promtail、JSON 结构化日志（trace_id） |
| 部署 | Docker 多阶段构建、非 root 运行、HEALTHCHECK、Nginx 反代 |

## 2. 功能范围

- **认证与权限**：JWT 双令牌（access 30min / refresh 3d），浏览器会话通过 HttpOnly Cookie（`eoms_at` / `eoms_rt`）下发并配合双提交 CSRF（`eoms_csrf` + `X-CSRF-Token`），脚本/第三方集成仍可用 `Authorization: Bearer`；Redis 黑名单与刷新令牌原子轮换/重放检测，Argon2 密码、图形验证码、登录失败锁定、并发会话上限、首登/过期强制改密；RBAC + 数据域（`ALL / COMPANY / DEPT / DEPT_TREE / PROJECT / SELF`），多角色取并集且收敛到公司边界，PostgreSQL RLS 兜底。
- **审批中心**：费用报销、请假、公文发文；四级可配置流程（线性四级 + 金额阈值升级 + 节点内加签/会签），支持同意/驳回/转办/加签/撤回/催办/抄送，DB 行锁 + Redis 分布式锁保证并发安全。
- **项目管理**：立项、变更、验收、结项归档，里程碑与进度，项目成员与数据域联动，版本乐观锁。
- **供应商与合同**：供应商准入/评价/黑名单、合同签订与续签/终止、敏感字段加密与脱敏。
- **成本与预算**：成本记录（幂等 `record_key`、冲销生成负数流水）、付款登记、预算占用与阈值预警、会计期间关账校验。
- **经营报表**：项目损益、收入、现金流、审批效率等报表，快照生成与 Excel/PDF 导出。
- **平台管理**：用户/角色/部门/字典/参数/客户、审计日志、通知中心、文件中心、看板。

## 3. 目录结构

```
EOMS/
├── app/                    # 后端应用
│   ├── api/v1/             # REST 端点（按业务域拆分）
│   ├── core/               # 配置、鉴权、错误、日志、缓存、数据域
│   ├── models/             # ORM 模型
│   ├── schemas/            # Pydantic 模型
│   ├── services/           # 业务服务（审批、项目、供应商、成本、报表…）
│   ├── workflow/           # 审批引擎与流程定义
│   ├── tasks/              # Celery 异步任务
│   ├── main.py             # 应用入口、中间件、健康检查、指标
│   └── celery_app.py       # Celery 与 beat 调度
├── migrations/             # Alembic 迁移
├── scripts/
│   ├── seed.py             # 演示数据初始化（--reset 重建）
│   └── backup.sh           # 数据库 + 对象存储备份
├── tests/                  # 接口测试与权限隔离专项
├── docs/                   # 概要设计、用户手册、部署与运维文档
├── web/                    # 前端工程（Vite）
├── docker/                 # Dockerfile、entrypoint、nginx.conf
├── deploy/                 # 一键部署/运维脚本、Prometheus/Grafana/Loki/Promtail 配置
├── docker-compose.yml      # 生产编排
├── release.md              # 版本发布记录
├── .env.example            # 本地开发变量模板
├── .env.docker.example     # Docker 部署变量模板
└── .github/workflows/ci.yml
```

## 4. 本地开发

### 4.1 环境要求

- Python 3.10+（生产镜像使用 3.12）
- Node.js 20+
- 可选：PostgreSQL / Redis / MinIO（不启动时自动降级为 SQLite + 进程内缓存 + 本地文件）

### 4.2 后端

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"

# 准备环境变量：本地无 PostgreSQL/Redis 时保持相应变量为空
cp .env.example .env
# Windows: copy .env.example .env
```

`.env` 中本地开发建议：

```ini
EOMS_ENV=dev
EOMS_DATABASE_URL=            # 留空 → SQLite .data/eoms.db
EOMS_REDIS_URL=               # 留空 → 进程内缓存/锁
EOMS_CELERY_ALWAYS_EAGER=true # 或保持默认，dev 且无 Redis 时自动 eager
EOMS_STORAGE_BACKEND=local
EOMS_RLS_ENABLED=false        # SQLite 不支持 RLS
```

初始化演示数据并启动：

```bash
python scripts/seed.py --reset
uvicorn app.main:app --host 127.0.0.1 --port 8011 --reload
```

- Swagger：<http://127.0.0.1:8011/docs>
- 健康检查：`/healthz`（存活）、`/readyz`（依赖就绪）、`/metrics`（Prometheus）

### 4.3 前端

```bash
cd web
npm install
npm run dev
```

访问 <http://127.0.0.1:5180>。Vite 已将 `/api`、`/healthz`、`/readyz` 代理到 `127.0.0.1:8011`。

生产构建：

```bash
npm run build   # 产物在 web/dist
```

### 4.4 演示账号

统一密码：**`Eoms@2026`**（`admin` 首次登录强制改密）。

| 账号 | 角色 | 数据域 | 说明 |
| --- | --- | --- | --- |
| `admin` | ADMIN | ALL | 超级管理员，首登强制改密 |
| `director` | DIRECTOR | ALL | 董事，全局查看与终审 |
| `manager` | MANAGER | DEPT_TREE | 总经理/经理，审批第二节点 |
| `leader` | DEPT_LEADER | DEPT | 部门负责人，审批第一节点 |
| `pm` | PM | PROJECT | 项目经理，项目全流程 |
| `finance` | FINANCE | COMPANY | 财务专员，付款/成本/报表 |
| `purchase` | PURCHASE | COMPANY | 采购专员，供应商/合同 |
| `auditor` | AUDITOR | COMPANY | 审计，全公司审计与追溯 |
| `employee` | EMPLOYEE | SELF | 普通员工，报销/请假/发文 |

> `seed.py` 使用固定演示数据，可通过 `--no-snapshot` 跳过报表快照生成；`--reset` 在 `EOMS_ENV=prod` 下会被拒绝。

## 5. 数据库迁移

```bash
alembic upgrade head                 # 应用迁移
alembic revision --autogenerate -m "描述"  # 生成迁移
alembic downgrade -1                 # 回退一版
```

容器内由 `docker/entrypoint.sh` 自动执行，并使用 PostgreSQL 咨询锁串行化多副本迁移。

## 6. 测试与质量

```bash
pytest                                   # 全量接口测试
pytest --cov=app --cov-report=term       # 覆盖率（当前 82%）
pytest tests/test_03_scope.py -q         # 数据域/越权专项
ruff check .                             # 静态检查
ruff format --check .                    # 格式检查（如启用）
mypy app                                 # 类型检查
```

测试基座 `tests/conftest.py` 会自动创建独立临时 SQLite、执行 `seed(reset=True)`，不会污染本地数据。

## 7. Docker 部署

### 7.1 一键部署（Ubuntu 22.04，推荐）

```bash
git clone <仓库地址> /opt/eoms
cd /opt/eoms
sudo bash deploy/install.sh
```

脚本会自动完成：

1. 安装 Docker Engine、Buildx 与 Compose v2（`--cn-mirror` 使用国内软件源与镜像加速）；
2. 生成 `.env` 并随机生成数据库、MinIO、Grafana、JWT、AES 全部密钥，权限 `600`；
3. 构建镜像并启动 `db / redis / minio / api / worker / beat / nginx`（默认含监控组件）；
4. 等待 `/healthz` 通过，首次部署自动初始化演示数据；
5. 安装 `eoms` 运维命令，日常启停、升级、备份、日志一条命令完成。

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--port 8080` | 修改对外端口（默认 80） |
| `--domain eoms.example.com` | 使用域名访问 |
| `--origin https://eoms.example.com` | 由外部网关终止 TLS，自动启用安全 Cookie |
| `--seed` / `--no-seed` | 强制 / 禁止初始化演示数据 |
| `--minimal` | 不启动 Prometheus/Grafana/Loki/Promtail，降低资源占用 |
| `--cn-mirror` | 国内网络加速（Docker、pip、npm） |
| `--skip-docker-install` | 已自行安装 Docker 时跳过安装 |

示例：

```bash
# 内网 8080 端口，国内网络
sudo bash deploy/install.sh --port 8080 --cn-mirror

# 已由云负载均衡提供 HTTPS，EOMS 只监听内网
sudo bash deploy/install.sh --origin https://eoms.example.com --port 8080

# 轻量部署，不启用监控
sudo bash deploy/install.sh --minimal
```

> 重复执行安装脚本是安全的：已有 `.env` 的密钥与数据不会被重置，仅重建镜像并滚动启动。

### 7.2 手动部署

详细步骤、TLS、升级回滚与排障见 [`docs/部署文档.md`](docs/部署文档.md)。

```bash
cp .env.docker.example .env
```

必须替换的变量：

| 变量 | 说明 |
| --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 |
| `MINIO_ROOT_PASSWORD` | MinIO 密码 |
| `GRAFANA_ADMIN_PASSWORD` | Grafana 管理员密码 |
| `EOMS_SECRET_KEY` | JWT/会话签名密钥（建议 48 字节随机） |
| `EOMS_AES_KEY` | 敏感字段加密密钥（32 字节 base64） |

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

> 手动部署且暂时使用 HTTP 访问时，需将 `EOMS_COOKIE_SECURE` 改为 `false`，否则浏览器不会保存会话 Cookie，表现为登录后立即掉线；正式环境请配置 HTTPS 并保持 `true`。

### 7.3 构建与启动

```bash
docker compose build
docker compose up -d
docker compose ps
```

首次启动可选初始化演示数据：

```bash
docker compose run --rm api python scripts/seed.py
# 或在 .env 中设置 EOMS_SEED_ON_START=true 后重启 api（仅首次）
```

访问：<http://localhost>（`HTTP_PORT` 可改）。

### 7.4 服务与端口

| 服务 | 说明 | 对外端口 |
| --- | --- | --- |
| `nginx` | SPA 静态资源 + `/api` 反向代理 | `${HTTP_PORT:-80}` |
| `api` | FastAPI（uvicorn，默认 2 worker，可扩容） | 仅容器网络 8000 |
| `worker` | Celery worker（通知/报表/文件） | — |
| `beat` | Celery beat 定时任务 | — |
| `db` | PostgreSQL 16（数据卷持久化） | 不暴露 |
| `redis` | Redis 7（AOF） | 不暴露 |
| `minio` | MinIO 对象存储 | 不暴露 |
| `prometheus` | 指标采集（`monitoring` profile） | `127.0.0.1:${PROMETHEUS_PORT:-9090}` |
| `grafana` | 监控面板（`monitoring` profile） | `127.0.0.1:${GRAFANA_PORT:-3000}` |
| `loki` / `promtail` | 日志聚合/采集（`monitoring` profile） | 不暴露 |

> 监控组件通过 Compose profile `monitoring` 控制，由 `.env` 中的 `COMPOSE_PROFILES` 决定是否启动。

扩容 API：

```bash
docker compose up -d --scale api=3
```

`api` 无状态且不设固定容器名，Nginx 通过 Docker DNS 动态解析副本。

### 7.5 常用运维命令

一键部署会自动安装 `eoms` 命令：

```bash
eoms status          # 容器与健康状态
eoms info            # 访问地址、端口、监控状态
eoms logs api        # 跟踪日志（默认 api nginx）
eoms restart         # 重启 api/worker/beat/nginx
eoms update          # 备份 + 拉取代码 + 重建 + 滚动启动
eoms backup          # 数据库 + 对象存储备份
eoms restore backups/eoms-20260101-020000.tar.gz
eoms monitoring enable|disable|status
eoms seed            # 初始化演示数据
eoms doctor          # 环境诊断
```

未安装 `eoms` 时仍可直接使用 Compose：

```bash
docker compose logs -f api worker
docker compose exec api alembic current
docker compose exec db psql -U eoms -d eoms
docker compose restart api worker beat
docker compose down            # 保留数据卷
docker compose down -v         # 危险：删除数据卷
```

## 8. 监控与日志

- Prometheus 指标：`http_requests_total`、`http_request_duration_seconds_bucket`、`http_requests_inprogress`、`process_*`。
- 预置告警（`deploy/prometheus/alerts.yml`）：实例不可达、5xx 比例 > 2%、P95 > 1.5s、在途请求 > 100、抓取目标缺失。
- Grafana 自动加载 `EOMS 运营概览` 面板（存活、5xx、QPS、延迟分位、热点接口、内存、异常日志、日志级别趋势）。
- 日志为单行 JSON，含 `trace_id / user_id / username / ip / path / status / duration_ms`，Promtail 采集容器 stdout 推送 Loki。
- 前端请求会携带 `X-Trace-Id`，Nginx 透传并可回写响应头，便于端到端排查。

## 9. 备份与恢复

备份（PostgreSQL 自定义格式 + MinIO 镜像 + SHA256，默认保留 30 天）：

```bash
./scripts/backup.sh
# 自定义目录/保留天数
EOMS_BACKUP_DIR=/data/backups EOMS_BACKUP_RETENTION_DAYS=60 ./scripts/backup.sh
```

产物：`backups/eoms-YYYYmmdd-HHMMSS.tar.gz` 与 `.sha256`。

恢复：

```bash
# 1. 解包
tar -xzf backups/eoms-20260101-023000.tar.gz -C /tmp/eoms-restore

# 2. 恢复数据库（会覆盖同名对象）
docker compose exec -T db pg_restore -U eoms -d eoms --clean --if-exists --no-owner \
    < /tmp/eoms-restore/db.dump

# 3. 恢复对象存储
docker run --rm --network eoms-net \
    -e MINIO_ROOT_USER=eoms -e MINIO_ROOT_PASSWORD='***' -e MINIO_BUCKET=eoms \
    -v /tmp/eoms-restore/minio:/backup --entrypoint /bin/sh minio/mc:latest -c '
        mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
        mc mirror --overwrite /backup "local/$MINIO_BUCKET"
    '

# 4. 重启应用
docker compose restart api worker beat
```

建议每季度做一次恢复演练，并校验 `.sha256`。

## 10. 安全要点

- 密钥只通过环境变量/外部 KMS 注入，不写入镜像与仓库；`.env*` 已在 `.gitignore` / `.dockerignore` 中排除。
- 密码使用 Argon2 哈希；手机号、身份证等敏感字段 AES 加密存储，接口按权限脱敏。
- 统一错误响应 `{code,msg,data,trace_id}`；业务规则错误返回 HTTP 422 + `code=3000`，未授权 401/403。
- 写接口支持 `Idempotency-Key`，成本入账使用唯一 `record_key`，付款/报销防重复。
- 生产开启 `EOMS_RLS_ENABLED=true`，在数据库层按公司隔离；应用层数据域仍为第一道防线。
- Nginx 已配置 CSP、`X-Content-Type-Options`、`X-Frame-Options`、Referrer-Policy，上传限制 32MB。

## 11. CI

`.github/workflows/ci.yml` 在 push / PR 时执行：

1. `ruff check` + `mypy`
2. `pytest --cov=app`（覆盖率阈值 80%）
3. 前端 `npm ci && npm run build`
4. 构建后端与前端镜像
5. 在 PostgreSQL 服务上执行 `alembic upgrade head`（并校验模型与迁移一致）
6. 构建后端/前端镜像，以 Docker 容器连接 PostgreSQL + Redis 启动 API，冒烟检查 `/healthz`、`/readyz`、验证码与 OpenAPI

## 12. 常见问题

| 现象 | 处理 |
| --- | --- |
| 启动报数据库连接失败 | 检查 `EOMS_DATABASE_URL`；本地留空使用 SQLite；容器内确认 `db` 健康 |
| 上传文件失败 | 本地确认 `EOMS_STORAGE_BACKEND=local` 且 `.data/storage` 可写；容器确认 MinIO 与 `minio-init` 成功 |
| 异步任务不执行 | 本地可设 `EOMS_CELERY_ALWAYS_EAGER=true`；容器检查 `redis` 与 `worker` 日志 |
| 登录提示锁定 | 等待 `EOMS_LOGIN_LOCK_MINUTES`，或清理 Redis 中登录失败计数 |
| 前端 401 循环 | 清除浏览器 Cookie（`eoms_at` / `eoms_rt` / `eoms_csrf`）后重新登录；确认后端时间与 `EOMS_TIMEZONE` 一致 |
| 写操作返回 403「CSRF 校验失败」 | 前端需带 `X-CSRF-Token`（值取自 `eoms_csrf` Cookie）；跨域部署检查 CORS 是否放行该请求头 |
| HTTPS 下登录后立即掉线 | 确认 `EOMS_COOKIE_SECURE=true` 且反代透传 `X-Forwarded-Proto`，Cookie 未被浏览器丢弃 |
| 演示数据错乱 | 重新执行 `python scripts/seed.py --reset` |

## 13. 许可

Proprietary. 未经授权不得分发。
