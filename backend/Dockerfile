FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Optional build-time proxy, disabled unless explicitly supplied.
#
# These are Docker's reserved proxy build args: when passed they are injected
# into RUN steps automatically and are NOT persisted into the image. They are
# declared here (with no default) purely to document the opt-in, so a normal
# build never uses a proxy.
#
# Do NOT hardcode a proxy in ENV: the previous version baked in
# http://host.docker.internal:7897, which only resolves on Docker Desktop.
# On a plain Linux host `host.docker.internal` does not exist, so apt failed
# with "Could not resolve 'host.docker.internal'" before it could even reach
# the mirror. A stale proxy is worse than no proxy.
#
# To build behind a proxy:
#   docker build --build-arg HTTP_PROXY=http://proxy.example:3128 \
#                --build-arg HTTPS_PROXY=http://proxy.example:3128 .
#   docker compose -f docker-compose.prod.yml build \
#     --build-arg HTTP_PROXY=http://proxy.example:3128
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Debian官方源（不使用国内镜像覆盖，避免镜像同步延迟导致的 404）
WORKDIR /app

# System deps for asyncpg / pgvector
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

EXPOSE 8000

# Auto-run database migrations on startup, then start the server.
# This ensures tables are created before the app accepts requests,
# so users don't need to manually run `alembic upgrade head`.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
