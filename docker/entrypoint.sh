#!/bin/sh
# ---------------------------------------------------------------------------
# EOMS 容器入口：等待数据库 → 执行迁移（PG 咨询锁串行化）→ 可选演示数据 → 启动进程
# 所有业务进程均通过 exec 接管 PID 1，保证信号（SIGTERM）可正常优雅退出。
# ---------------------------------------------------------------------------
set -eu

echo "[entrypoint] EOMS_ENV=${EOMS_ENV:-dev} 等待数据库就绪..."

python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
url = settings.resolved_database_url
if url.startswith("sqlite"):
    print("[entrypoint] SQLite 模式，跳过数据库等待")
    sys.exit(0)

engine = create_engine(url, pool_pre_ping=True, future=True)
last_error = None
for attempt in range(1, 61):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[entrypoint] 数据库已就绪（第 {attempt} 次探测）")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        print(f"[entrypoint] 数据库未就绪（{attempt}/60）：{exc}")
        time.sleep(2)
print(f"[entrypoint] 数据库连接失败：{last_error}", file=sys.stderr)
sys.exit(1)
PY

if [ "${EOMS_RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] 执行数据库迁移：alembic upgrade head"
    python - <<'PY'
import subprocess
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

url = settings.resolved_database_url
if url.startswith("sqlite"):
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))

# 多副本同时启动时用 PostgreSQL 会话级咨询锁串行化迁移。
MIGRATION_LOCK_ID = 728417
engine = create_engine(url, pool_pre_ping=True, future=True)
with engine.connect() as conn:
    conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
    try:
        code = subprocess.call(["alembic", "upgrade", "head"])
    finally:
        conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
sys.exit(code)
PY
fi

if [ "${EOMS_SEED_ON_START:-false}" = "true" ]; then
    echo "[entrypoint] 初始化演示数据（默认检测到已有数据会跳过）"
    python scripts/seed.py
fi

echo "[entrypoint] 启动：$*"
exec "$@"
