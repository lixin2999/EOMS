#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# EOMS 运维命令（由 deploy/install.sh 安装为 /usr/local/bin/eoms）
#
# 用法：eoms <命令> [参数]
#   eoms status                 查看容器与健康状态
#   eoms info                   查看访问地址与配置摘要
#   eoms up|down|start|stop     启动 / 停止
#   eoms restart [服务...]      重启（默认 api worker beat nginx）
#   eoms ps                     等价于 status
#   eoms logs [服务...]         跟踪日志（默认 api nginx）
#   eoms health                 检查 /healthz 与 /readyz
#   eoms shell [服务]           进入容器（默认 api）
#   eoms dbshell                进入 PostgreSQL
#   eoms seed [--yes] [参数]    初始化演示数据
#   eoms backup                 备份数据库与对象存储
#   eoms restore <归档> [--yes] 从备份归档恢复
#   eoms update [--no-pull] [--no-backup]  升级
#   eoms monitoring [enable|disable|status] 监控组件开关
#   eoms config                 校验 Compose 配置
#   eoms doctor                 环境诊断
#   eoms destroy [--yes]        删除容器与全部数据卷（危险）
# ---------------------------------------------------------------------------
set -Eeuo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
DEPLOY_DIR="$(dirname "$SCRIPT_PATH")"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
NETWORK_NAME="eoms-net"

if [[ -t 1 ]]; then
    C_INFO=$'\033[36m'
    C_OK=$'\033[32m'
    C_WARN=$'\033[33m'
    C_ERR=$'\033[31m'
    C_RESET=$'\033[0m'
else
    C_INFO=""
    C_OK=""
    C_WARN=""
    C_ERR=""
    C_RESET=""
fi

log() { printf '%s[eoms]%s %s\n' "$C_INFO" "$C_RESET" "$*"; }
ok() { printf '%s[eoms]%s %s\n' "$C_OK" "$C_RESET" "$*"; }
warn() { printf '%s[eoms] 警告:%s %s\n' "$C_WARN" "$C_RESET" "$*" >&2; }
die() {
    printf '%s[eoms] 错误:%s %s\n' "$C_ERR" "$C_RESET" "$*" >&2
    exit 1
}

usage() {
    sed -n '3,23p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
}

# 帮助信息无需 Docker 与 .env
if [[ $# -eq 0 || ${1:-} == "help" || ${1:-} == "-h" || ${1:-} == "--help" ]]; then
    usage
    exit 0
fi

command -v docker >/dev/null 2>&1 || die "未安装 Docker，请先执行：sudo bash deploy/install.sh"
docker compose version >/dev/null 2>&1 || die "缺少 Docker Compose v2 插件"

if ! docker info >/dev/null 2>&1; then
    if [[ ${EUID:-$(id -u)} -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
        exec sudo -E bash "$SCRIPT_PATH" "$@"
    fi
    die "无法连接 Docker，请确认 docker 服务已启动，且当前用户已加入 docker 组"
fi

[[ -f $ENV_FILE ]] || die "缺少 $ENV_FILE，请先执行：sudo bash deploy/install.sh"
[[ -f $ROOT_DIR/docker-compose.yml ]] || die "缺少 docker-compose.yml，项目目录可能不完整"

if [[ ! -r $ENV_FILE ]]; then
    if [[ ${EUID:-$(id -u)} -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
        exec sudo -E bash "$SCRIPT_PATH" "$@"
    fi
    die "无权读取 $ENV_FILE，请使用 root 或执行：sudo eoms <命令>"
fi

cd "$ROOT_DIR"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

HTTP_PORT="${HTTP_PORT:-80}"
PUBLIC_ORIGIN="${EOMS_PUBLIC_ORIGIN:-http://127.0.0.1:$HTTP_PORT}"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN%/}"
LOCAL_URL="http://127.0.0.1:$HTTP_PORT"
PROFILES="${COMPOSE_PROFILES:-}"

on_error() {
    local code=$?
    printf '\n%s[eoms] 命令执行失败（退出码 %s，行 %s）%s\n' "$C_ERR" "$code" "${BASH_LINENO[0]:-?}" "$C_RESET" >&2
    exit "$code"
}
trap on_error ERR

wait_health() {
    local timeout=${1:-240}
    local start=$SECONDS
    printf '[eoms] 等待服务就绪：%s ...\n' "$LOCAL_URL/healthz"
    while (( SECONDS - start < timeout )); do
        if curl -fsS --max-time 3 "$LOCAL_URL/healthz" >/dev/null 2>&1; then
            ok "服务已就绪（${PUBLIC_ORIGIN}）"
            return 0
        fi
        sleep 3
    done
    warn "健康检查超时（${timeout}s）"
    docker compose ps || true
    return 1
}

env_set() {
    python3 - "$ENV_FILE" "$@" <<'PY'
import re
import sys

path = sys.argv[1]
pairs = sys.argv[2:]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
for pair in pairs:
    key, value = pair.split("=", 1)
    pattern = rf"(?m)^{re.escape(key)}=.*$"
    if re.search(pattern, text):
        text = re.sub(pattern, lambda _m, k=key, v=value: f"{k}={v}", text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"{key}={value}\n"
with open(path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
PY
}

confirm() {
    local prompt=$1 answer=""
    if [[ ! -t 0 ]]; then
        die "非交互环境请追加 --yes 确认"
    fi
    read -r -p "$prompt [y/N] " answer
    [[ $answer =~ ^[Yy]$ ]] || {
        echo "已取消"
        exit 0
    }
}

cmd_status() {
    docker compose ps
    echo
    if curl -fsS --max-time 4 "$LOCAL_URL/healthz" >/dev/null 2>&1; then
        ok "健康检查：正常（$LOCAL_URL/healthz）"
    else
        warn "健康检查：未就绪（$LOCAL_URL/healthz）"
    fi
    if curl -fsS --max-time 4 "$LOCAL_URL/readyz" >/dev/null 2>&1; then
        ok "就绪检查：数据库 / 缓存正常（$LOCAL_URL/readyz）"
    else
        warn "就绪检查：未通过（$LOCAL_URL/readyz）"
    fi
}

cmd_info() {
    local monitoring="未启用"
    [[ $PROFILES == *monitoring* ]] && monitoring="已启用（127.0.0.1:${GRAFANA_PORT:-3000}）"
    cat <<EOF
EOMS 部署信息
  访问地址   : $PUBLIC_ORIGIN
  本机健康   : $LOCAL_URL/healthz
  本机就绪   : $LOCAL_URL/readyz
  配置文件   : $ENV_FILE
  运行环境   : ${EOMS_ENV:-prod}
  对外端口   : $HTTP_PORT
  监控组件   : $monitoring
  数据卷     : eoms_pgdata / eoms_redisdata / eoms_miniodata / eoms_eoms_storage
EOF
    if [[ $monitoring == 已启用* ]]; then
        echo "  Grafana    : ssh -L ${GRAFANA_PORT:-3000}:127.0.0.1:${GRAFANA_PORT:-3000} <user>@<server>"
    fi
}

cmd_up() {
    docker compose up -d --remove-orphans
    wait_health 300
    docker compose ps
}

cmd_down() {
    log "停止并删除容器（保留数据卷）..."
    docker compose down --remove-orphans
}

cmd_start() {
    docker compose start "$@"
    wait_health 180
}

cmd_stop() {
    if [[ $# -gt 0 ]]; then
        docker compose stop "$@"
    else
        docker compose stop
    fi
}

cmd_restart() {
    local services=("$@")
    if [[ ${#services[@]} -eq 0 ]]; then
        services=(api worker beat nginx)
    fi
    docker compose restart "${services[@]}"
    if [[ " ${services[*]} " == *" api "* || " ${services[*]} " == *" nginx "* ]]; then
        wait_health 180
    fi
}

cmd_logs() {
    local follow=1
    local services=()
    local arg
    for arg in "$@"; do
        case "$arg" in
            --no-follow) follow=0 ;;
            -f|--follow) follow=1 ;;
            *) services+=("$arg") ;;
        esac
    done
    [[ ${#services[@]} -gt 0 ]] || services=(api nginx)
    if (( follow )); then
        docker compose logs --tail=200 -f "${services[@]}"
    else
        docker compose logs --tail=300 "${services[@]}"
    fi
}

cmd_health() {
    log "GET $LOCAL_URL/healthz"
    curl -fsS "$LOCAL_URL/healthz"
    echo
    log "GET $LOCAL_URL/readyz"
    curl -fsS "$LOCAL_URL/readyz"
    echo
}

cmd_shell() {
    local service=${1:-api}
    docker compose exec "$service" sh
}

cmd_dbshell() {
    docker compose exec db psql -U "${POSTGRES_USER:-eoms}" -d "${POSTGRES_DB:-eoms}"
}

cmd_seed() {
    local assume_yes=0
    local args=()
    local arg
    for arg in "$@"; do
        case "$arg" in
            -y|--yes) assume_yes=1 ;;
            *) args+=("$arg") ;;
        esac
    done
    if (( ! assume_yes )); then
        confirm "将写入演示业务数据（幂等，已有数据会跳过），是否继续？"
    fi
    docker compose exec -T api python scripts/seed.py "${args[@]}"
}

cmd_backup() {
    log "执行备份..."
    bash "$ROOT_DIR/scripts/backup.sh" "$@"
}

cmd_restore() {
    local assume_yes=0
    local archive=""
    local arg
    for arg in "$@"; do
        case "$arg" in
            -y|--yes) assume_yes=1 ;;
            -*) die "未知参数：$arg" ;;
            *) archive="$arg" ;;
        esac
    done
    [[ -n $archive ]] || die "用法：eoms restore <备份归档.tar.gz> [--yes]"
    [[ -f $archive ]] || die "备份文件不存在：$archive"
    archive="$(readlink -f "$archive")"

    if [[ -f "$archive.sha256" ]] && command -v sha256sum >/dev/null 2>&1; then
        local expected actual
        expected="$(awk '{print $1}' "$archive.sha256")"
        actual="$(sha256sum "$archive" | awk '{print $1}')"
        [[ $expected == "$actual" ]] || die "备份文件校验失败：sha256 不匹配"
        ok "备份文件校验通过"
    else
        warn "未找到 .sha256 校验文件，跳过完整性校验"
    fi

    if (( ! assume_yes )); then
        confirm "恢复会覆盖当前数据库与对象存储，且不可撤销！是否继续？"
    fi

    local tmp
    tmp="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" RETURN
    tar -xzf "$archive" -C "$tmp"
    [[ -f "$tmp/db.dump" ]] || die "归档中缺少 db.dump"

    log "停止写入（api / worker / beat）..."
    docker compose stop api worker beat || true

    log "恢复 PostgreSQL..."
    if ! docker compose exec -T db pg_restore -U eoms -d eoms \
        --clean --if-exists --no-owner --no-privileges < "$tmp/db.dump"; then
        warn "数据库恢复失败，正在重新启动服务..."
        docker compose start api worker beat || true
        die "恢复中止，请检查上方的 pg_restore 输出"
    fi

    if [[ -d "$tmp/minio" ]]; then
        log "恢复 MinIO 对象存储..."
        if ! docker compose run --rm --no-deps \
            -e MINIO_ENDPOINT=minio:9000 \
            -e MINIO_ROOT_USER="${MINIO_ROOT_USER:-eoms}" \
            -e MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?缺少 MINIO_ROOT_PASSWORD}" \
            -e MINIO_BUCKET="${MINIO_BUCKET:-eoms}" \
            -v "$tmp/minio:/backup:ro" \
            --entrypoint /opt/venv/bin/python \
            minio-init /app/scripts/minio_storage.py restore /backup; then
            warn "对象存储恢复失败，正在重新启动服务..."
            docker compose start api worker beat || true
            die "恢复中止"
        fi
    fi

    log "启动服务..."
    docker compose start api worker beat
    wait_health 300
    ok "恢复完成"
}

cmd_update() {
    local pull=1
    local backup=1
    local arg
    for arg in "$@"; do
        case "$arg" in
            --no-pull) pull=0 ;;
            --no-backup) backup=0 ;;
            *) die "未知参数：$arg" ;;
        esac
    done

    if (( backup )); then
        if docker compose ps --status running -q db 2>/dev/null | grep -q .; then
            cmd_backup
        else
            warn "数据库未运行，跳过升级前备份"
        fi
    fi

    if (( pull )); then
        if [[ -d "$ROOT_DIR/.git" ]]; then
            log "拉取最新代码..."
            git -C "$ROOT_DIR" pull --ff-only
        else
            warn "当前目录不是 Git 仓库，跳过代码拉取"
        fi
    fi

    log "构建镜像..."
    docker compose build
    log "滚动启动（数据库迁移由 api 入口自动执行）..."
    docker compose up -d --remove-orphans
    wait_health 360
    docker compose ps
}

cmd_monitoring() {
    local action=${1:-status}
    case "$action" in
        enable)
            env_set "COMPOSE_PROFILES=monitoring"
            log "启动监控组件..."
            COMPOSE_PROFILES=monitoring docker compose up -d
            ;;
        disable)
            log "停止监控组件（保留监控数据卷）..."
            COMPOSE_PROFILES=monitoring docker compose stop prometheus grafana loki promtail 2>/dev/null || true
            env_set "COMPOSE_PROFILES="
            ok "监控组件已停止，后续 eoms up 不会再启动"
            ;;
        status)
            if [[ $PROFILES == *monitoring* ]]; then
                echo "监控组件：已启用（Grafana 127.0.0.1:${GRAFANA_PORT:-3000}）"
            else
                echo "监控组件：未启用"
            fi
            ;;
        *)
            die "用法：eoms monitoring [enable|disable|status]"
            ;;
    esac
}

cmd_config() {
    docker compose config -q
    ok "Compose 配置校验通过"
}

cmd_doctor() {
    echo "== Docker =="
    docker version --format 'Server: {{.Server.Version}}' 2>/dev/null || true
    docker compose version --short 2>/dev/null || true
    echo
    echo "== 系统资源 =="
    df -h "$ROOT_DIR" | tail -n 1
    free -h | sed -n '1,2p'
    echo
    echo "== 监听端口 =="
    if command -v ss >/dev/null 2>&1; then
        ss -ltn "sport = :$HTTP_PORT" 2>/dev/null || true
    fi
    echo
    echo "== 容器状态 =="
    docker compose ps
    echo
    echo "== Docker 磁盘占用 =="
    docker system df
}

cmd_destroy() {
    local assume_yes=0
    local arg
    for arg in "$@"; do
        case "$arg" in
            -y|--yes) assume_yes=1 ;;
            *) die "未知参数：$arg" ;;
        esac
    done
    if (( ! assume_yes )); then
        [[ -t 0 ]] || die "非交互环境请追加 --yes 确认"
        warn "此操作将删除全部容器、网络与数据卷（数据库、文件、监控数据），不可恢复！"
        local answer=""
        read -r -p "请输入 DELETE 确认：" answer
        [[ $answer == "DELETE" ]] || {
            echo "已取消"
            exit 0
        }
    fi
    docker compose down -v --remove-orphans
    ok "已删除容器与数据卷（.env 保留，如需彻底清理请手动删除）"
}

CMD=${1:-help}
[[ $# -gt 0 ]] && shift

case "$CMD" in
    status|ps) cmd_status ;;
    info) cmd_info ;;
    up) cmd_up ;;
    down) cmd_down ;;
    start) cmd_start "$@" ;;
    stop) cmd_stop "$@" ;;
    restart) cmd_restart "$@" ;;
    logs) cmd_logs "$@" ;;
    health) cmd_health ;;
    shell) cmd_shell "$@" ;;
    dbshell) cmd_dbshell ;;
    seed) cmd_seed "$@" ;;
    backup) cmd_backup "$@" ;;
    restore) cmd_restore "$@" ;;
    update) cmd_update "$@" ;;
    monitoring) cmd_monitoring "$@" ;;
    config) cmd_config ;;
    doctor) cmd_doctor ;;
    destroy) cmd_destroy "$@" ;;
    help|-h|--help) usage ;;
    *)
        usage
        echo
        die "未知命令：$CMD"
        ;;
esac
