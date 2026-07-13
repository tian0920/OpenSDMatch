#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_pid_file() {
  local pid_file="$1"
  if [[ -s "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    echo "Stopped $(basename "$pid_file"): $(cat "$pid_file")"
  fi
  rm -f "$pid_file"
}

stop_pid_file "$SCRIPT_DIR/annotation_tunnel.pid"
stop_pid_file "$SCRIPT_DIR/annotation_web.pid"
