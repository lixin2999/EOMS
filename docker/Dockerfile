# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# EOMS 后端镜像：多阶段构建（builder 编译依赖 → runtime 精简运行）
# 运行用户为非 root（uid/gid 10001），内置 HEALTHCHECK。
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    TZ=Asia/Shanghai \
    EOMS_ENV=prod \
    EOMS_LOCAL_STORAGE_DIR=/app/.data/storage

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 procps tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 eoms \
    && useradd --system --uid 10001 --gid eoms --create-home --home-dir /app eoms

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=eoms:eoms app ./app
COPY --chown=eoms:eoms migrations ./migrations
COPY --chown=eoms:eoms scripts ./scripts
COPY --chown=eoms:eoms alembic.ini pyproject.toml README.md ./
COPY --chown=eoms:eoms docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/.data/storage /app/logs \
    && chown -R eoms:eoms /app

USER eoms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
