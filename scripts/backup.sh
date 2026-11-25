#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# EOMS 备份：PostgreSQL 逻辑备份 + MinIO 对象镜像，保留 30 天
#
# 用法（在仓库根目录执行）：
#   ./scripts/backup.sh
#   EOMS_BACKUP_DIR=/data/backups ./scripts/backup.sh
#
# 依赖：docker / docker compose、tar、sha256sum（Windows 可用 Git Bash + WSL）
# 建议通过 cron 每日 02:30 执行：
#   30 2 * * * cd /opt/eoms && ./scripts/backup.sh >> /var/log/eoms-backup.log 2>&1
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
    echo "[backup] 缺少 .env（请参考 .env.docker.example 创建）" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

BACKUP_DIR="${EOMS_BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${EOMS_BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK_DIR="$BACKUP_DIR/work-$STAMP"
ARCHIVE="$BACKUP_DIR/eoms-$STAMP.tar.gz"

mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[backup] 1/4 导出 PostgreSQL..."
docker compose exec -T db \
    pg_dump -U eoms -d eoms --format=custom --no-owner --no-privileges \
    > "$WORK_DIR/db.dump"

echo "[backup] 2/4 镜像 MinIO 对象存储..."
docker compose run --rm --no-deps \
    -e MINIO_ROOT_USER="${MINIO_ROOT_USER:-eoms}" \
    -e MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?缺少 MINIO_ROOT_PASSWORD}" \
    -e MINIO_BUCKET="${MINIO_BUCKET:-eoms}" \
    -v "$WORK_DIR:/backup" \
    --entrypoint /bin/sh \
    minio-init -c '
        set -eu
        mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
        if mc ls "local/$MINIO_BUCKET" >/dev/null 2>&1; then
            mc mirror --overwrite --quiet "local/$MINIO_BUCKET" /backup/minio
        else
            mkdir -p /backup/minio
        fi
    '

echo "[backup] 3/4 打包并校验..."
tar -czf "$ARCHIVE" -C "$WORK_DIR" db.dump minio
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
fi
echo "[backup] 完成：$ARCHIVE"

echo "[backup] 4/4 清理超过 ${RETENTION_DAYS} 天的备份..."
find "$BACKUP_DIR" -maxdepth 1 -name 'eoms-*.tar.gz*' -mtime "+${RETENTION_DAYS}" -print -delete

echo "[backup] 全部完成。建议定期执行以下演练："
echo "  docker compose exec -T db pg_restore --list < <(tar -xzOf '$ARCHIVE' db.dump) | head"
