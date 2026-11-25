#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# EOMS 一键部署脚本（Ubuntu 22.04 / Debian 12）
#
# 功能：
#   1. 安装 Docker Engine + Compose v2（可选国内镜像源）；
#   2. 自动生成 .env，随机生成全部密钥（不会覆盖已有 .env）；
#   3. 构建镜像、启动全部服务并等待健康检查通过；
#   4. 首次部署可按需初始化演示数据；
#   5. 安装 eoms 运维命令（/usr/local/bin/eoms）。
#
# 用法（在仓库根目录执行）：
#   sudo bash deploy/install.sh
#   sudo bash deploy/install.sh --port 8080 --seed --cn-mirror
#   sudo bash deploy/install.sh --origin https://eoms.example.com
#
# 常用参数：
#   --port N          Nginx 对外端口，默认 80
#   --domain FQDN     对外域名（未启用 TLS 时生成 http://域名[:端口]）
#   --origin URL      对外访问地址，如 https://eoms.example.com
#   --seed            强制初始化演示数据（已有 .env 时默认不初始化）
#   --no-seed         不初始化演示数据
#   --minimal         不启动 Prometheus/Grafana/Loki/Promtail
#   --monitoring      启动监控组件（默认）
#   --cn-mirror       使用阿里云 Docker 源并配置镜像加速与 pip/npm 国内源
#   --skip-docker-install  跳过 Docker 安装（已自行安装时使用；不影响 --cn-mirror 配置）
#   -h, --help        显示帮助
# ---------------------------------------------------------------------------
set -Eeuo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
DEPLOY_DIR="$(dirname "$SCRIPT_PATH")"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_TEMPLATE="$ROOT_DIR/.env.docker.example"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

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
    sed -n '2,28p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
}

# 帮助信息无需 root 权限
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
            ;;
    esac
done

# 以 root 运行时无需重复 sudo
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        log "需要 root 权限，正在通过 sudo 重新执行..."
        exec sudo -E bash "$SCRIPT_PATH" "$@"
    fi
    die "请以 root 身份运行：sudo bash $SCRIPT_PATH"
fi

HTTP_PORT=80
DOMAIN=""
ORIGIN=""
DO_SEED="auto"
MONITORING=1
MONITORING_SET=0
CN_MIRROR=0
SKIP_DOCKER=0
PORT_SET=0
ORIGIN_SET=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            [[ $# -ge 2 ]] || die "--port 缺少参数"
            HTTP_PORT="$2"
            PORT_SET=1
            shift 2
            ;;
        --port=*)
            HTTP_PORT="${1#*=}"
            PORT_SET=1
            shift
            ;;
        --domain)
            [[ $# -ge 2 ]] || die "--domain 缺少参数"
            DOMAIN="$2"
            ORIGIN_SET=1
            shift 2
            ;;
        --domain=*)
            DOMAIN="${1#*=}"
            ORIGIN_SET=1
            shift
            ;;
        --origin)
            [[ $# -ge 2 ]] || die "--origin 缺少参数"
            ORIGIN="$2"
            ORIGIN_SET=1
            shift 2
            ;;
        --origin=*)
            ORIGIN="${1#*=}"
            ORIGIN_SET=1
            shift
            ;;
        --seed)
            DO_SEED=1
            shift
            ;;
        --no-seed)
            DO_SEED=0
            shift
            ;;
        --minimal)
            MONITORING=0
            MONITORING_SET=1
            shift
            ;;
        --monitoring)
            MONITORING=1
            MONITORING_SET=1
            shift
            ;;
        --cn-mirror)
            CN_MIRROR=1
            shift
            ;;
        --skip-docker-install)
            SKIP_DOCKER=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "未知参数：$1（使用 --help 查看用法）"
            ;;
    esac
done

[[ $HTTP_PORT =~ ^[0-9]+$ ]] || die "--port 必须是数字"
HTTP_PORT=$((10#$HTTP_PORT))
(( HTTP_PORT >= 1 && HTTP_PORT <= 65535 )) || die "--port 必须在 1-65535 之间"

cd "$ROOT_DIR"

on_error() {
    local code=$?
    printf '\n%s[eoms] 部署中断（退出码 %s，行 %s）%s\n' "$C_ERR" "$code" "${BASH_LINENO[0]:-?}" "$C_RESET" >&2
    echo "  排查命令：" >&2
    echo "    docker compose ps" >&2
    echo "    docker compose logs --tail=100 api nginx" >&2
    exit "$code"
}
trap on_error ERR

# ---------------------------------------------------------------------------
# 1. 系统检测与依赖
# ---------------------------------------------------------------------------
[[ -r /etc/os-release ]] || die "无法读取 /etc/os-release，请确认系统为 Ubuntu/Debian"
# shellcheck disable=SC1091
. /etc/os-release

OS_ID="${ID:-unknown}"
OS_CODENAME="${VERSION_CODENAME:-}"
if [[ -z $OS_CODENAME ]] && command -v lsb_release >/dev/null 2>&1; then
    OS_CODENAME="$(lsb_release -cs)"
fi
[[ -n $OS_CODENAME ]] || die "无法确定系统版本代号（VERSION_CODENAME），请手动安装 Docker 后使用 --skip-docker-install"

if [[ $OS_ID != "ubuntu" && $OS_ID != "debian" ]]; then
    warn "当前系统为 ${PRETTY_NAME:-$OS_ID}，脚本仅在 Ubuntu 22.04 / Debian 12 验证过，将继续尝试"
elif [[ $OS_ID == "ubuntu" && ${VERSION_ID:-} != "22.04" ]]; then
    warn "推荐 Ubuntu 22.04，当前为 ${VERSION_ID:-未知}，将继续尝试"
fi

log "项目目录：$ROOT_DIR"
[[ -f $COMPOSE_FILE ]] || die "未找到 docker-compose.yml，请在 EOMS 仓库根目录执行本脚本"
[[ -f $ENV_TEMPLATE ]] || die "未找到 .env.docker.example"

apt_install() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends "$@"
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        systemctl enable --now docker >/dev/null 2>&1 || true
        if docker info >/dev/null 2>&1; then
            ok "Docker 已安装：$(docker --version | cut -d, -f1)，$(docker compose version --short 2>/dev/null || true)"
            return 0
        fi
    fi

    log "安装 Docker Engine、Buildx 与 Compose v2 ..."
    apt_install ca-certificates curl gnupg

    local repo_os="$OS_ID"
    local repo_base="https://download.docker.com/linux/$repo_os"
    local gpg_url="https://download.docker.com/linux/$repo_os/gpg"

    if (( CN_MIRROR )); then
        repo_base="https://mirrors.aliyun.com/docker-ce/linux/$repo_os"
        gpg_url="https://mirrors.aliyun.com/docker-ce/linux/$repo_os/gpg"
        log "使用阿里云 Docker 软件源"
    fi

    install -m 0755 -d /etc/apt/keyrings
    rm -f /etc/apt/keyrings/docker.asc
    if ! curl -fsSL --retry 3 --connect-timeout 10 "$gpg_url" -o /etc/apt/keyrings/docker.asc; then
        die "下载 Docker GPG 密钥失败，请检查网络；国内服务器可加 --cn-mirror"
    fi
    chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] $repo_base $OS_CODENAME stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -y
    apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable --now docker
    docker info >/dev/null 2>&1 || die "Docker 服务启动失败，请执行 systemctl status docker 查看原因"
    ok "Docker 安装完成：$(docker --version | cut -d, -f1)"
}

configure_docker_mirror() {
    (( CN_MIRROR )) || return 0

    local daemon_config="/etc/docker/daemon.json"
    local mirrors=(
        "https://docker.m.daocloud.io"
        "https://docker.1ms.run"
        "https://dockerproxy.net"
    )
    local merge_result

    log "配置 Docker 镜像加速..."
    mkdir -p /etc/docker
    if ! merge_result="$(python3 - "$daemon_config" "${mirrors[@]}" <<'PY'
import json
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime

path = sys.argv[1]
desired = sys.argv[2:]
existed = os.path.exists(path)
if existed:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
else:
    data = {}

if not isinstance(data, dict):
    raise SystemExit("daemon.json 顶层必须是 JSON 对象")

current = data.get("registry-mirrors", [])
if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
    raise SystemExit("daemon.json 中的 registry-mirrors 必须是字符串数组")

merged = list(current)
for mirror in desired:
    if mirror not in merged:
        merged.append(mirror)

if merged == current:
    print("unchanged")
    raise SystemExit(0)

backup = ""
if existed:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup = f"{path}.eoms-backup-{stamp}"
    shutil.copy2(path, backup)

data["registry-mirrors"] = merged
mode = stat.S_IMODE(os.stat(path).st_mode) if existed else 0o644
fd, tmp_path = tempfile.mkstemp(prefix=".daemon.json.", dir=os.path.dirname(path), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)
except Exception:
    try:
        os.unlink(tmp_path)
    except FileNotFoundError:
        pass
    raise

print(backup or "created")
PY
)"; then
        die "合并 Docker 镜像加速配置失败，请检查 $daemon_config 是否为合法 JSON"
    fi

    if [[ "$merge_result" == "unchanged" ]]; then
        ok "Docker 镜像加速已配置，无需重启"
        return 0
    fi

    if [[ "$merge_result" != "created" ]]; then
        log "原配置已备份：$merge_result"
    fi
    systemctl restart docker
    sleep 2
    docker info >/dev/null 2>&1 || die "Docker 重启失败，请检查 $daemon_config 与 systemctl status docker"
    ok "Docker 镜像加速配置完成"
}

if (( SKIP_DOCKER )); then
    command -v docker >/dev/null 2>&1 || die "未安装 Docker，且指定了 --skip-docker-install"
    docker compose version >/dev/null 2>&1 || die "缺少 Docker Compose v2 插件"
    docker info >/dev/null 2>&1 || die "无法连接 Docker 服务"
else
    install_docker
fi

command -v curl >/dev/null 2>&1 || apt_install curl ca-certificates
command -v python3 >/dev/null 2>&1 || apt_install python3

# Docker 已安装时同样需要应用 --cn-mirror 的镜像加速配置
configure_docker_mirror

if [[ -n ${SUDO_USER:-} && ${SUDO_USER} != "root" ]]; then
    if ! id -nG "$SUDO_USER" | grep -qw docker; then
        usermod -aG docker "$SUDO_USER" || true
        log "已将用户 $SUDO_USER 加入 docker 组（重新登录后无需 sudo）"
    fi
fi

# ---------------------------------------------------------------------------
# 2. 生成 / 校验 .env
# ---------------------------------------------------------------------------
rand_b64() {
    python3 -c 'import base64,os,sys; print(base64.b64encode(os.urandom(int(sys.argv[1]))).decode())' "$1"
}

rand_hex() {
    python3 -c 'import secrets,sys; print(secrets.token_hex(int(sys.argv[1])))' "$1"
}

env_get() {
    local key=$1
    [[ -f $ENV_FILE ]] || return 0
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

env_has() {
    local key=$1
    [[ -f $ENV_FILE ]] && grep -q "^${key}=" "$ENV_FILE"
}

# 使用 Python 原地更新 KEY=VALUE，自动转义且支持追加缺失键
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

detect_public_ip() {
    local url ip=""
    for url in https://api.ipify.org https://ifconfig.me/ip https://ipinfo.io/ip; do
        ip="$(curl -fsS --max-time 4 "$url" 2>/dev/null | tr -d '[:space:]' || true)"
        if [[ $ip =~ ^[0-9a-fA-F:.]+$ ]]; then
            printf '%s' "$ip"
            return 0
        fi
    done
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    printf '%s' "${ip:-127.0.0.1}"
}

ENV_CREATED=0
if [[ ! -f $ENV_FILE ]]; then
    log "生成 .env（随机密钥，权限 600）..."
    umask 077
    install -m 0600 "$ENV_TEMPLATE" "$ENV_FILE"
    ENV_CREATED=1
fi

# 复用已有配置时，端口/监控开关以显式参数为准
CURRENT_PORT="$(env_get HTTP_PORT)"
CURRENT_ORIGIN="$(env_get EOMS_PUBLIC_ORIGIN)"
CURRENT_PROFILES="$(env_get COMPOSE_PROFILES)"

if (( ! PORT_SET )) && [[ -n $CURRENT_PORT ]]; then
    HTTP_PORT="$CURRENT_PORT"
fi

[[ $HTTP_PORT =~ ^[0-9]+$ ]] || die ".env 中的 HTTP_PORT 必须是数字"
HTTP_PORT=$((10#$HTTP_PORT))
(( HTTP_PORT >= 1 && HTTP_PORT <= 65535 )) || die ".env 中的 HTTP_PORT 必须在 1-65535 之间"

if (( ! MONITORING_SET )); then
    if [[ $ENV_CREATED -eq 1 ]]; then
        MONITORING=1
    elif env_has COMPOSE_PROFILES; then
        [[ $CURRENT_PROFILES == *monitoring* ]] && MONITORING=1 || MONITORING=0
    else
        # 兼容旧版 .env（尚未包含 COMPOSE_PROFILES 时默认启动监控）
        MONITORING=1
    fi
fi

if (( ORIGIN_SET )); then
    if [[ -z $ORIGIN ]]; then
        [[ -n $DOMAIN ]] || die "--origin 不能为空"
        [[ $DOMAIN != *"://"* ]] || die "--domain 只填写域名，不要包含 http:// 或 https://"
        [[ $DOMAIN != *:* ]] || die "--domain 不要包含端口，请使用 --port 指定"
        ORIGIN="http://$DOMAIN"
        [[ $HTTP_PORT == "80" ]] || ORIGIN="$ORIGIN:$HTTP_PORT"
    fi
elif (( ! ENV_CREATED )) && [[ -n $CURRENT_ORIGIN && $CURRENT_ORIGIN != "http://localhost"* && $CURRENT_ORIGIN != "http://127.0.0.1"* ]]; then
    ORIGIN="$CURRENT_ORIGIN"
    # 端口变化时同步更新 HTTP 直连地址，避免 CORS 仍指向旧端口
    if (( PORT_SET )) && [[ $ORIGIN == http://* ]]; then
        ORIGIN="$(python3 -c '
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1])
host = p.hostname or ""
host = f"[{host}]" if ":" in host else host
port = "" if sys.argv[2] == "80" else ":" + sys.argv[2]
print(f"{p.scheme}://{host}{port}")
' "$ORIGIN" "$HTTP_PORT")"
    fi
else
    PUBLIC_IP="$(detect_public_ip)"
    if [[ $PUBLIC_IP == *:* ]]; then
        ORIGIN="http://[$PUBLIC_IP]"
    else
        ORIGIN="http://$PUBLIC_IP"
    fi
    [[ $HTTP_PORT == "80" ]] || ORIGIN="$ORIGIN:$HTTP_PORT"
fi

ORIGIN="${ORIGIN%/}"
[[ $ORIGIN =~ ^https?://[^/]+$ ]] || die "--origin 必须是 http(s):// 开头的完整地址，且不能包含路径"

ORIGIN_SCHEME="${ORIGIN%%://*}"
ORIGIN_HOST="$(python3 -c 'import sys, urllib.parse as u; print(u.urlparse(sys.argv[1]).hostname or "")' "$ORIGIN")"
[[ -n $ORIGIN_HOST ]] || die "无法从 $ORIGIN 解析主机名"
COOKIE_SECURE="false"
[[ $ORIGIN_SCHEME == "https" ]] && COOKIE_SECURE="true"

if [[ $ORIGIN_HOST =~ ^[0-9.]+$ || $ORIGIN_HOST == *:* || $ORIGIN_HOST == "localhost" ]]; then
    TRUSTED_HOSTS="*"
else
    # 保留容器内健康检查、Prometheus 抓取所需的主机名
    TRUSTED_HOSTS="$ORIGIN_HOST,localhost,127.0.0.1,api"
fi

PROFILES=""
(( MONITORING )) && PROFILES="monitoring"

# 仅匹配「KEY=...CHANGE_ME...」的值行，避免误判模板中的说明注释
env_needs_init() {
    grep -Eq '^[A-Za-z_][A-Za-z0-9_]*=.*CHANGE_ME' "$ENV_FILE"
}

# 首次建库时补齐占位密钥；已有数据库卷时禁止改密钥，避免连接失败
if env_needs_init; then
    if docker volume inspect eoms_pgdata >/dev/null 2>&1; then
        die ".env 仍含 CHANGE_ME 且数据库卷 eoms_pgdata 已存在。请先备份并手动修正 .env，或删除数据卷后重装"
    fi
    log "检测到 CHANGE_ME 占位密钥，自动替换为随机值..."
fi

if (( ENV_CREATED )) || env_needs_init; then
    env_set \
        "EOMS_SECRET_KEY=$(rand_b64 48)" \
        "EOMS_AES_KEY=$(rand_b64 32)" \
        "POSTGRES_PASSWORD=$(rand_hex 24)" \
        "MINIO_ROOT_PASSWORD=$(rand_hex 24)" \
        "GRAFANA_ADMIN_PASSWORD=$(rand_hex 18)"
fi

# 国内网络：为后续构建注入公共镜像源（也可在 .env 中手动修改）
if (( CN_MIRROR )); then
    env_set \
        "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple" \
        "NPM_REGISTRY=https://registry.npmmirror.com"
elif (( ENV_CREATED )); then
    env_set \
        "PIP_INDEX_URL=https://pypi.org/simple" \
        "NPM_REGISTRY=https://registry.npmjs.org"
fi

env_set \
    "HTTP_PORT=$HTTP_PORT" \
    "EOMS_PUBLIC_ORIGIN=$ORIGIN" \
    "EOMS_TRUSTED_HOSTS=$TRUSTED_HOSTS" \
    "EOMS_COOKIE_SECURE=$COOKIE_SECURE" \
    "COMPOSE_PROFILES=$PROFILES"

chmod 600 "$ENV_FILE"

# 显式导出，确保当前进程内的 Compose 调用立即使用最新 profile
export COMPOSE_PROFILES="$PROFILES"

for key in EOMS_SECRET_KEY EOMS_AES_KEY POSTGRES_PASSWORD MINIO_ROOT_PASSWORD GRAFANA_ADMIN_PASSWORD; do
    [[ -n "$(env_get "$key")" ]] || die ".env 中 $key 为空，请参考 $ENV_TEMPLATE 修正"
done

if [[ "$COOKIE_SECURE" == "false" ]]; then
    warn "当前使用 HTTP 访问，已自动设置 EOMS_COOKIE_SECURE=false，仅建议内网使用"
    warn "公网部署请配置 HTTPS，并使用 --origin https://你的域名 重新执行（会保留现有 .env 密钥）"
fi

log "校验 Compose 配置..."
docker compose config -q

# ---------------------------------------------------------------------------
# 3. 端口检查、构建与启动
# ---------------------------------------------------------------------------
if command -v ss >/dev/null 2>&1; then
    if ss -ltnH "sport = :$HTTP_PORT" 2>/dev/null | grep -q .; then
        if ! docker ps --format '{{.Ports}}' 2>/dev/null | grep -Eq "[:.]$HTTP_PORT->"; then
            die "端口 $HTTP_PORT 已被其他进程占用，请使用 --port 指定其他端口"
        fi
    fi
fi

log "构建镜像（首次构建需要数分钟，请耐心等待）..."
docker compose build

log "启动服务..."
docker compose up -d --remove-orphans

wait_health() {
    local timeout=${1:-300}
    local start=$SECONDS
    local url="http://127.0.0.1:$HTTP_PORT/healthz"
    log "等待服务就绪：$url"
    while (( SECONDS - start < timeout )); do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            ok "服务已就绪（耗时 $((SECONDS - start)) 秒）"
            return 0
        fi
        sleep 3
    done
    return 1
}

if ! wait_health 360; then
    echo >&2
    docker compose ps >&2 || true
    echo "--- api 最近日志 ---" >&2
    docker compose logs --tail=120 api >&2 || true
    die "服务未在预期时间内就绪，请根据上方日志排查"
fi

# 首次部署默认初始化演示数据；已有 .env 时需显式 --seed
if [[ $DO_SEED == "auto" ]]; then
    [[ $ENV_CREATED -eq 1 ]] && DO_SEED=1 || DO_SEED=0
fi

SEEDED=0
if (( DO_SEED )); then
    log "初始化演示数据（幂等，已有数据会跳过）..."
    if docker compose exec -T api python scripts/seed.py; then
        SEEDED=1
    else
        warn "演示数据初始化失败，可稍后执行：eoms seed"
    fi
fi

# ---------------------------------------------------------------------------
# 4. 安装运维命令
# ---------------------------------------------------------------------------
chmod +x "$ROOT_DIR/deploy/eoms.sh" "$ROOT_DIR/scripts/backup.sh" 2>/dev/null || true
if [[ -e /usr/local/bin/eoms && ! -L /usr/local/bin/eoms ]]; then
    warn "/usr/local/bin/eoms 已存在且不是符号链接，跳过安装运维命令"
else
    ln -sfn "$ROOT_DIR/deploy/eoms.sh" /usr/local/bin/eoms
    chmod +x /usr/local/bin/eoms
    ok "已安装运维命令：eoms（可用 eoms help 查看）"
fi

# ---------------------------------------------------------------------------
# 5. 输出部署结果
# ---------------------------------------------------------------------------
echo
printf '%s============================================================%s\n' "$C_OK" "$C_RESET"
printf '%s  EOMS 部署完成%s\n' "$C_OK" "$C_RESET"
printf '%s============================================================%s\n' "$C_OK" "$C_RESET"
cat <<EOF
  访问地址 : $ORIGIN
  健康检查 : http://127.0.0.1:$HTTP_PORT/healthz
  配置文件 : $ENV_FILE （权限 600，请妥善保管）
  监控组件 : $([[ -n $PROFILES ]] && echo "已启用（推荐 SSH 隧道访问 Grafana 127.0.0.1:${GRAFANA_PORT:-3000}）" || echo "未启用")
EOF

if (( SEEDED )); then
    cat <<'EOF'

  演示账号 : admin / Eoms@2026（首次登录需修改密码）
  其他账号 : director / manager / leader / pm / finance / purchase / employee / auditor
  上线前请务必修改 admin 密码，并禁用不需要的演示账号。
EOF
else
    cat <<'EOF'

  当前未初始化演示数据。空库无法登录，可执行：
    eoms seed
EOF
fi

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    warn "检测到 ufw 已启用，如无法访问请执行：ufw allow $HTTP_PORT/tcp"
fi

cat <<'EOF'

  常用命令：
    eoms status       查看服务与健康状态
    eoms logs         跟踪 api/nginx 日志
    eoms update       备份 + 拉取代码 + 重建 + 滚动启动
    eoms backup       备份数据库与对象存储
    eoms monitoring   开启/关闭监控组件（enable|disable）
    eoms help         查看全部命令

  非 root 用户首次使用请重新登录（docker 组生效），或直接执行 sudo eoms。

  详细说明见 docs/部署文档.md。
EOF
