#!/bin/sh
set -eu

CONFIG_PATH="${MEDIAMTX_CONFIG:-/mediamtx.yml}"
if [ ! -f "$CONFIG_PATH" ]; then
  echo "ingest-entrypoint: config file not found at $CONFIG_PATH" >&2
  exit 1
fi

/usr/local/bin/mediamtx "$CONFIG_PATH" 2>&1 | awk -f /usr/local/bin/ingest_log_normalizer.awk

