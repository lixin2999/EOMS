# ---------------------------------------------------------------------------
# EOMS 前端镜像：Node 构建 → Nginx 运行（静态资源 + /api 反向代理）
# 构建上下文必须为仓库根目录：docker build -f web/Dockerfile .
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

ENV TZ=Asia/Shanghai

RUN rm -f /etc/nginx/conf.d/default.conf \
    && apk add --no-cache tzdata \
    && mkdir -p /var/cache/nginx /var/run

COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
