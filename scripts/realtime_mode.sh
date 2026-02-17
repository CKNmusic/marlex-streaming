#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-}"
ENV_FILE="${2:-.env}"

usage() {
    cat <<'USAGE'
Uso:
  bash scripts/realtime_mode.sh memory
  bash scripts/realtime_mode.sh redis

Opcional:
  bash scripts/realtime_mode.sh <memory|redis> <arquivo-env>
USAGE
}

if [[ "$MODE" != "memory" && "$MODE" != "redis" ]]; then
    usage
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: arquivo de ambiente nao encontrado: $ENV_FILE" >&2
    exit 1
fi

TEMPLATE_FILE=".env.realtime.${MODE}"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "ERROR: template nao encontrado: $TEMPLATE_FILE" >&2
    exit 1
fi

upsert_env_key() {
    local key="$1"
    local value="$2"
    local file="$3"
    local tmp_file
    tmp_file="$(mktemp)"

    awk -v key="$key" -v value="$value" '
        BEGIN { replaced = 0 }
        {
            if ($0 ~ ("^" key "=")) {
                if (replaced == 0) {
                    print key "=" value
                    replaced = 1
                }
                next
            }
            print
        }
        END {
            if (replaced == 0) {
                print key "=" value
            }
        }
    ' "$file" > "$tmp_file"
    mv "$tmp_file" "$file"
}

while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(printf '%s' "$line" | tr -d '\r')"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    upsert_env_key "$key" "$value" "$ENV_FILE"
done < "$TEMPLATE_FILE"

if [[ "$MODE" == "redis" ]]; then
    docker compose -f docker-compose.realtime.yml up -d redis
    echo "Modo realtime: redis"
else
    docker compose -f docker-compose.realtime.yml stop redis >/dev/null 2>&1 || true
    docker compose -f docker-compose.realtime.yml rm -f redis >/dev/null 2>&1 || true
    echo "Modo realtime: memory"
fi

echo "Arquivo atualizado: $ENV_FILE"
echo "Reinicie a API para aplicar as novas variaveis."
