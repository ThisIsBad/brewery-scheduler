# Produktions-Image (MVP, 2026-08-05). Zwei Ziele aus einem Build:
#   --target backend  -> FastAPI/uvicorn inkl. Migrationen+Seed beim Start
#   --target web      -> Caddy mit dem gebauten Frontend + Reverse-Proxy
# deploy/docker-compose.prod.yml verdrahtet beide mit Postgres und Backups.

FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app
COPY backend/ ./
RUN pip install --no-cache-dir .
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]

FROM caddy:2 AS web
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/caddy-entrypoint.sh /caddy-entrypoint.sh
RUN chmod +x /caddy-entrypoint.sh
COPY --from=frontend-build /build/dist /srv
ENTRYPOINT ["/caddy-entrypoint.sh"]
