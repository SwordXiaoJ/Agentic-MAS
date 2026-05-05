#!/bin/bash
# Robust local dev launcher:
# - Loads v1_classification/.env explicitly
# - Activates .venv
# - Cleans stale processes on known ports
# - Starts Docker infrastructure (NATS + MinIO), then Gateway, Planner, all agents (incl. Org D document) in background (logs/)
# - Starts frontend (Vite) in foreground
# - Cleans up everything on Ctrl+C

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
VENV_ACTIVATE="$ROOT_DIR/.venv/bin/activate"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/.start_all.pids"

mkdir -p "$LOG_DIR"
: > "$PID_FILE"

cleanup_done=0

kill_port() {
    local port="$1"
    local pids=""

    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    elif command -v fuser >/dev/null 2>&1; then
        pids="$(fuser "$port"/tcp 2>/dev/null || true)"
    fi

    if [ -n "${pids// }" ]; then
        echo "Clearing port $port (PIDs: $pids)"
        # shellcheck disable=SC2086
        kill -TERM $pids 2>/dev/null || true
        sleep 1
        # shellcheck disable=SC2086
        kill -KILL $pids 2>/dev/null || true
    fi
}

cleanup() {
    if [ "$cleanup_done" -eq 1 ]; then
        return
    fi
    cleanup_done=1

    echo ""
    echo "Stopping background services..."

    if [ -f "$PID_FILE" ]; then
        while read -r pid; do
            [ -z "$pid" ] && continue
            kill -TERM "$pid" 2>/dev/null || true
        done < "$PID_FILE"
        sleep 1
        while read -r pid; do
            [ -z "$pid" ] && continue
            kill -KILL "$pid" 2>/dev/null || true
        done < "$PID_FILE"
    fi

    # Extra safety in case child shells exited but python/node stayed alive
    kill_port "${GATEWAY_PORT:-8080}"
    kill_port "${PLANNER_PORT:-8083}"
    kill_port "${GENERAL_AGENT_PORT:-9003}"
    kill_port "${MEDICAL_AGENT_PORT:-9001}"
    kill_port "${SATELLITE_AGENT_PORT:-9002}"
    kill_port "${DOCUMENT_AGENT_PORT:-9004}"

    echo "Cleanup complete."
}

trap cleanup INT TERM EXIT

echo "Loading environment from $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env not found at $ENV_FILE"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "Error: virtualenv activate script not found at $VENV_ACTIVATE"
    exit 1
fi
source "$VENV_ACTIVATE"

export PYTHONPATH="$ROOT_DIR"
export GATEWAY_PORT="${GATEWAY_PORT:-8080}"
export PLANNER_PORT="${PLANNER_PORT:-8083}"
export GENERAL_AGENT_PORT="${GENERAL_AGENT_PORT:-9003}"
export MEDICAL_AGENT_PORT="${MEDICAL_AGENT_PORT:-9001}"
export SATELLITE_AGENT_PORT="${SATELLITE_AGENT_PORT:-9002}"
export DOCUMENT_AGENT_PORT="${DOCUMENT_AGENT_PORT:-9004}"
export DEFAULT_MESSAGE_TRANSPORT="${DEFAULT_MESSAGE_TRANSPORT:-NATS}"
export TRANSPORT_SERVER_ENDPOINT="${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}"
export OBSERVE_ENABLED="${OBSERVE_ENABLED:-false}"

echo "Pre-cleaning stale processes/ports..."
kill_port "$GATEWAY_PORT"
kill_port "$PLANNER_PORT"
kill_port "$GENERAL_AGENT_PORT"
kill_port "$MEDICAL_AGENT_PORT"
kill_port "$SATELLITE_AGENT_PORT"
kill_port "$DOCUMENT_AGENT_PORT"

if [ "$OBSERVE_ENABLED" = "true" ]; then
    echo "Starting infrastructure (NATS + MinIO + Observability)..."
    ./scripts/start_infrastructure.sh --full >>"$LOG_DIR/infrastructure.log" 2>&1
else
    echo "Starting infrastructure (NATS + MinIO)..."
    ./scripts/start_infrastructure.sh >>"$LOG_DIR/infrastructure.log" 2>&1
fi
echo "  Infrastructure -> $LOG_DIR/infrastructure.log"
echo "Waiting 5s for infrastructure containers to become ready..."
sleep 5

echo "Starting backend services in background (logs/)..."
bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_gateway.sh" >"$LOG_DIR/gateway.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  Gateway  -> $LOG_DIR/gateway.log"

bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_planner.sh" >"$LOG_DIR/planner.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  Planner  -> $LOG_DIR/planner.log"

bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_general_agent.sh" >"$LOG_DIR/general_agent.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  General  -> $LOG_DIR/general_agent.log"

bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_medical_agent.sh" >"$LOG_DIR/medical_agent.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  Medical  -> $LOG_DIR/medical_agent.log"

bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_satellite_agent.sh" >"$LOG_DIR/satellite_agent.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  Satellite -> $LOG_DIR/satellite_agent.log"

bash -lc "cd \"$ROOT_DIR\" && ./scripts/start_document_agent.sh" >"$LOG_DIR/document_agent.log" 2>&1 &
echo "$!" >> "$PID_FILE"
echo "  Document  -> $LOG_DIR/document_agent.log"

echo ""
echo "Waiting for Gateway to come online on port $GATEWAY_PORT..."
while true; do
    if command -v nc >/dev/null 2>&1; then
        if nc -z 127.0.0.1 "$GATEWAY_PORT" >/dev/null 2>&1; then
            break
        fi
    elif command -v curl >/dev/null 2>&1; then
        if curl -sSf "http://127.0.0.1:$GATEWAY_PORT/health" >/dev/null 2>&1; then
            break
        fi
    else
        # Fallback to bash /dev/tcp if nc/curl unavailable
        if (echo >/dev/tcp/127.0.0.1/"$GATEWAY_PORT") >/dev/null 2>&1; then
            break
        fi
    fi
    sleep 1
done
echo "Gateway is online."
echo ""
echo "Launching frontend in foreground (Ctrl+C stops all services)..."
cd "$ROOT_DIR/frontend"
npm run dev
