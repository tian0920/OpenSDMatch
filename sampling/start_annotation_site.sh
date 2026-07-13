#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$REPO_DIR/.tools"
CLOUDFLARED="$TOOLS_DIR/cloudflared"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
LOCAL_URL="http://127.0.0.1:$PORT"

APP_PID="$SCRIPT_DIR/annotation_web.pid"
TUNNEL_PID="$SCRIPT_DIR/annotation_tunnel.pid"
APP_LOG="$SCRIPT_DIR/annotation_web.log"
TUNNEL_LOG="$SCRIPT_DIR/annotation_tunnel.log"
URL_FILE="$SCRIPT_DIR/annotation_public_url.txt"

is_running() {
  local pid_file="$1"
  [[ -s "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

stop_pid_file() {
  local pid_file="$1"
  if is_running "$pid_file"; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$pid_file"
}

mkdir -p "$TOOLS_DIR"

if [[ ! -x "$CLOUDFLARED" ]]; then
  echo "Downloading cloudflared..."
  curl -L --fail -o "$CLOUDFLARED" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
  chmod +x "$CLOUDFLARED"
fi

stop_pid_file "$APP_PID"
stop_pid_file "$TUNNEL_PID"
rm -f "$URL_FILE"

cd "$REPO_DIR"
setsid python sampling/annotation_web.py --host "$HOST" --port "$PORT" > "$APP_LOG" 2>&1 < /dev/null &
echo "$!" > "$APP_PID"

for _ in {1..30}; do
  if python - <<PY >/dev/null 2>&1
from urllib.request import urlopen
urlopen("$LOCAL_URL/api/stats", timeout=1).read()
PY
  then
    break
  fi
  sleep 1
done

if ! kill -0 "$(cat "$APP_PID")" 2>/dev/null; then
  echo "Annotation web service failed to start. See: $APP_LOG" >&2
  exit 1
fi

setsid "$CLOUDFLARED" tunnel --url "$LOCAL_URL" > "$TUNNEL_LOG" 2>&1 < /dev/null &
echo "$!" > "$TUNNEL_PID"

for _ in {1..45}; do
  public_url="$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -1 || true)"
  if [[ -n "${public_url:-}" ]]; then
    echo "$public_url" > "$URL_FILE"
    echo "Public URL: $public_url"
    echo "App PID: $(cat "$APP_PID")"
    echo "Tunnel PID: $(cat "$TUNNEL_PID")"
    echo "URL file: $URL_FILE"
    echo "Logs: $APP_LOG $TUNNEL_LOG"
    exit 0
  fi
  sleep 1
done

echo "Tunnel started, but no public URL was found yet. See: $TUNNEL_LOG" >&2
exit 1
