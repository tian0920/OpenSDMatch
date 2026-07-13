#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/ecs-user/miniconda3/envs/OpenSDMatch/bin/python}"
APP_PATH="${APP_PATH:-$ROOT_DIR/sampling/annotation_web.py}"
CSV_PATH="${CSV_PATH:-$ROOT_DIR/sampling/annotation_pairs_blind.csv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
REPLICATES="${REPLICATES:-2}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/sampling/run}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/sampling/logs}"
PID_FILE="$RUN_DIR/annotation_web.pid"
LOG_FILE="$LOG_DIR/annotation_web.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start() {
  if is_running; then
    echo "Annotation web is already running: pid $(cat "$PID_FILE")"
    echo "URL: http://$HOST:$PORT"
    return 0
  fi

  if [[ -f "$PID_FILE" ]]; then
    rm -f "$PID_FILE"
  fi

  echo "Starting annotation web..."
  echo "CSV: $CSV_PATH"
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"

  cd "$ROOT_DIR"
  setsid env PYTHONUNBUFFERED=1 "$PYTHON_BIN" "$APP_PATH" \
    --csv "$CSV_PATH" \
    --host "$HOST" \
    --port "$PORT" \
    --replicates "$REPLICATES" \
    </dev/null >> "$LOG_FILE" 2>&1 &

  echo "$!" > "$PID_FILE"
  sleep 1

  if is_running; then
    echo "Started: pid $(cat "$PID_FILE")"
  else
    echo "Failed to start. Recent log:"
    tail -50 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    exit 1
  fi
}

stop() {
  if ! is_running; then
    echo "Annotation web is not running."
    rm -f "$PID_FILE"
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  echo "Stopping annotation web: pid $pid"
  kill "$pid"

  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Stopped."
      return 0
    fi
    sleep 0.5
  done

  echo "Process did not stop gracefully; killing."
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Stopped."
}

status() {
  if is_running; then
    echo "Annotation web is running: pid $(cat "$PID_FILE")"
    echo "URL: http://$HOST:$PORT"
    echo "CSV: $CSV_PATH"
    echo "Log: $LOG_FILE"
  else
    echo "Annotation web is not running."
  fi
}

logs() {
  touch "$LOG_FILE"
  tail -f "$LOG_FILE"
}

case "${1:-status}" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    start
    ;;
  status)
    status
    ;;
  logs)
    logs
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 2
    ;;
esac
