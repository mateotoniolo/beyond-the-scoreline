# syntax=docker/dockerfile:1
# Stage 1: build the web UI
FROM node:22-alpine AS web
RUN corepack enable && corepack prepare pnpm@9 --activate
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# Stage 2: Python runtime
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./src/bts/static
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "--factory", "bts.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
