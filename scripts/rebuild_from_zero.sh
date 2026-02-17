#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

read_env_value() {
    local key="$1"
    local default_value="$2"
    local line value
    if [[ -f .env ]]; then
        line="$(grep -E "^${key}=" .env | tail -n 1 || true)"
        if [[ -n "$line" ]]; then
            value="${line#*=}"
            value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+#.*$//')"
            if [[ -n "$value" ]]; then
                printf '%s' "$value"
                return 0
            fi
        fi
    fi
    printf '%s' "$default_value"
}

POSTGRES_USER="$(read_env_value POSTGRES_USER postgres)"
POSTGRES_DB="$(read_env_value POSTGRES_DB streaming_app)"
APP_HOST="$(read_env_value APP_HOST 127.0.0.1)"
APP_NAME="$(read_env_value APP_NAME surgwaze)"
WEB_PUBLIC_PORT="$(read_env_value WEB_PUBLIC_PORT 3000)"
RESTART_INGEST_AFTER_REBUILD="${RESTART_INGEST_AFTER_REBUILD:-0}"
INGEST_WAS_RUNNING=0

if docker ps --format '{{.Names}}' | grep -qx "streaming_ingest"; then
    INGEST_WAS_RUNNING=1
    echo "[pre] Pausando ingest para limpeza de recordings..."
    docker compose stop ingest >/dev/null 2>&1 || true
fi

echo "[0/5] Limpando historicos/cache/temp locais..."
rm -rf .runtime .pytest_cache web/dist web/.vite
find . \
    -path "./.git" -prune -o \
    -path "./.venv" -prune -o \
    -path "./web/node_modules" -prune -o \
    -type d \( -name "__pycache__" -o -name "cache" -o -name "tmp" -o -name "temp" -o -name "history" -o -name "histories" \) \
    -exec rm -rf {} + 2>/dev/null || true
find . \
    -path "./.git" -prune -o \
    -path "./.venv" -prune -o \
    -path "./web/node_modules" -prune -o \
    -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" \) \
    -delete 2>/dev/null || true
rm -rf recordings 2>/dev/null || true
if [[ -d recordings ]] && find recordings -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
    docker run --rm -v "$ROOT_DIR/recordings:/recordings" alpine:3 sh -c 'rm -rf /recordings/*' >/dev/null 2>&1 || true
fi
if [[ -d recordings ]] && find recordings -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
    echo "WARN: ainda existem arquivos em recordings apos limpeza local."
fi
mkdir -p recordings

echo "[1/5] Subindo servico do PostgreSQL..."
docker compose up -d db >/dev/null

echo "[2/5] Aguardando PostgreSQL ficar pronto..."
for _ in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    echo "ERROR: PostgreSQL nao ficou pronto em 60s." >&2
    exit 1
fi

echo "[2.4/5] Encerrando conexoes ativas no banco alvo para evitar lock em DROP..."
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" >/dev/null || true

echo "[2.5/5] Sem snapshot: drop/recreate destrutivo habilitado."

echo "[3/5] Recriando schema completo (drop + create)..."
docker compose exec -T db psql \
    -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" < scripts/bootstrap_db.sql

echo "[4/5] Aplicando inserts essenciais..."
docker compose exec -T db psql \
    -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" < scripts/seed_minimal.sql

echo "[4.5/5] Ajustando host publico da aplicacao com base no .env..."
APP_PUBLIC_HOST_VALUE="http://${APP_HOST}:${WEB_PUBLIC_PORT}/${APP_NAME}"
docker compose exec -T db psql \
    -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -c "UPDATE app_settings SET host='${APP_PUBLIC_HOST_VALUE}' WHERE id=1;" >/dev/null

echo "[5/5] Rebuild de teste concluido."
echo "Banco recreado e seed minimo aplicado com sucesso."

if [[ "$INGEST_WAS_RUNNING" -eq 1 && "$RESTART_INGEST_AFTER_REBUILD" = "1" ]]; then
    echo "[post] Religando ingest..."
    docker compose up -d ingest >/dev/null
elif [[ "$INGEST_WAS_RUNNING" -eq 1 ]]; then
    echo "[post] Ingest mantido parado para preservar limpeza de recordings."
fi
