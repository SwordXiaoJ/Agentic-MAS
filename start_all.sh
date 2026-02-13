#!/bin/bash
# Start All Classification System (A2A)
#
# Infrastructure (always started):
#   - NATS/SLIM transport
#   - MinIO (object storage)
#   - MCP server (agents decide individually whether to use)
#
# ADS (Agent Directory Service) is managed separately:
#   ./scripts/start_ads.sh              # Start ADS
#   ./scripts/publish_agent_records.sh  # Publish agent cards
#
# Usage:
#   ./start_all.sh              # Default (NATS transport)
#   ./start_all.sh slim         # Use SLIM transport instead of NATS

cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Load environment variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Parse arguments
SLIM_MODE="false"

for arg in "$@"; do
    case $arg in
        slim)
            SLIM_MODE="true"
            ;;
    esac
done

# Set transport based on SLIM mode
if [ "$SLIM_MODE" == "true" ]; then
    export DEFAULT_MESSAGE_TRANSPORT=SLIM
    export TRANSPORT_SERVER_ENDPOINT=http://localhost:46357
else
    export DEFAULT_MESSAGE_TRANSPORT=NATS
    export TRANSPORT_SERVER_ENDPOINT=nats://localhost:4222
fi

# Clean up any stale processes/containers first
echo "Cleaning up stale processes..."
./stop_all.sh 2>/dev/null
echo ""

# Record PIDs for cleanup
PID_FILE=".service_pids"
> "$PID_FILE"

echo "=============================================="
echo "Classification System - A2A Architecture"
echo "Discovery: ADS (start ADS separately)"
echo "Transport: $([ "$SLIM_MODE" == "true" ] && echo "SLIM (HTTP)" || echo "NATS")"
echo "MCP Server: Always On (agents decide individually)"
echo "=============================================="
echo ""

# Calculate total steps (MCP always included; ADS managed separately)
TOTAL_STEPS=7

CURRENT_STEP=1

# Start infrastructure (NATS + MinIO, optionally SLIM)
echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting Infrastructure..."
if [ "$SLIM_MODE" == "true" ]; then
    ./scripts/start_infrastructure.sh --with-slim
else
    ./scripts/start_infrastructure.sh
fi
sleep 5
CURRENT_STEP=$((CURRENT_STEP + 1))

# Start MCP services (always-on infrastructure; agents decide individually whether to use)
echo ""
echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting MCP Services..."
export MCP_TOPIC=medical_tools_service
./scripts/start_mcp_medical.sh &
echo $! >> "$PID_FILE"
sleep 2
CURRENT_STEP=$((CURRENT_STEP + 1))

# Start agents in background
echo ""
echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting Medical Agent (port 9001)..."
./scripts/start_medical_agent.sh &
echo $! >> "$PID_FILE"
sleep 1
CURRENT_STEP=$((CURRENT_STEP + 1))

echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting Satellite Agent (port 9002)..."
./scripts/start_satellite_agent.sh &
echo $! >> "$PID_FILE"
sleep 1
CURRENT_STEP=$((CURRENT_STEP + 1))

echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting General Agent (port 9003)..."
./scripts/start_general_agent.sh &
echo $! >> "$PID_FILE"
sleep 1
CURRENT_STEP=$((CURRENT_STEP + 1))

echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting Planner (port 8083)..."
./scripts/start_planner.sh ads &
echo $! >> "$PID_FILE"
sleep 1
CURRENT_STEP=$((CURRENT_STEP + 1))

echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting Gateway (port 8080)..."
./scripts/start_gateway.sh &
echo $! >> "$PID_FILE"

echo ""
echo "=============================================="
echo "All Services Started!"
echo "=============================================="
echo ""
echo "Gateway (entry point):"
echo "  - Gateway:    http://localhost:8080"
echo ""
echo "Agents:"
echo "  - Medical:    http://localhost:9001"
echo "  - Satellite:  http://localhost:9002"
echo "  - General:    http://localhost:9003"
echo ""
echo "Services:"
echo "  - Planner:    http://localhost:8083 (ADS discovery)"
echo "  - ADS:        (start separately: ./scripts/start_ads.sh)"
if [ "$SLIM_MODE" == "true" ]; then
    echo "  - MCP:        medical_tools_service (via SLIM)"
else
    echo "  - MCP:        medical_tools_service (via NATS)"
fi
if [ "$SLIM_MODE" == "true" ]; then
    echo "  - SLIM:       http://localhost:46357"
fi
echo ""
echo "Usage:"
echo "  curl -X POST http://localhost:8080/v1/classify -F 'image=@test.jpg' -F 'prompt=Classify this image'"
echo ""
echo "Press Ctrl+C to stop all services"

wait
