#!/bin/bash
# Start All Classification System (A2A)
#
# Usage:
#   ./start_all.sh              # Static discovery (default, uses NATS)
#   ./start_all.sh ads          # ADS discovery (dynamic)
#   ./start_all.sh mcp          # Static + MCP tools enabled
#   ./start_all.sh slim         # Use SLIM transport instead of NATS
#   ./start_all.sh ads mcp      # ADS + MCP tools enabled
#   ./start_all.sh slim mcp     # SLIM + MCP tools enabled

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
DISCOVERY_MODE="static"
MCP_MODE="false"
SLIM_MODE="false"

for arg in "$@"; do
    case $arg in
        ads)
            DISCOVERY_MODE="ads"
            ;;
        mcp)
            MCP_MODE="true"
            ;;
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
echo "Discovery Mode: $([ "$DISCOVERY_MODE" == "ads" ] && echo "ADS (Dynamic)" || echo "Static (Hardcoded)")"
echo "Transport: $([ "$SLIM_MODE" == "true" ] && echo "SLIM (HTTP)" || echo "NATS")"
echo "MCP Tools: $([ "$MCP_MODE" == "true" ] && echo "Enabled" || echo "Disabled")"
echo "=============================================="
echo ""

# Calculate total steps
TOTAL_STEPS=6
[ "$DISCOVERY_MODE" == "ads" ] && TOTAL_STEPS=$((TOTAL_STEPS + 1))
[ "$MCP_MODE" == "true" ] && TOTAL_STEPS=$((TOTAL_STEPS + 1))

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

# If ADS mode, start ADS services and publish agents
if [ "$DISCOVERY_MODE" == "ads" ]; then
    echo ""
    echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting ADS Services..."
    ./scripts/start_ads.sh
    sleep 3
    CURRENT_STEP=$((CURRENT_STEP + 1))

    echo ""
    echo "NOTE: Agent records are NOT auto-published. Run manually when needed:"
    echo "  ./scripts/publish_agent_records.sh"
fi

# If MCP mode, start MCP services
if [ "$MCP_MODE" == "true" ]; then
    echo ""
    echo "[$CURRENT_STEP/$TOTAL_STEPS] Starting MCP Services..."
    ./scripts/start_mcp_medical.sh &
    echo $! >> "$PID_FILE"
    sleep 2
    CURRENT_STEP=$((CURRENT_STEP + 1))

    # Export MCP environment variables for agents
    export USE_MCP=true
    export MCP_TOPIC=medical_tools_service
fi

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
if [ "$DISCOVERY_MODE" == "ads" ]; then
    ./scripts/start_planner.sh ads &
else
    ./scripts/start_planner.sh &
fi
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
echo "  - Planner:    http://localhost:8083"
if [ "$DISCOVERY_MODE" == "ads" ]; then
    echo "  - ADS:        localhost:8888 (gRPC)"
fi
if [ "$MCP_MODE" == "true" ]; then
    if [ "$SLIM_MODE" == "true" ]; then
        echo "  - MCP:        medical_tools_service (via SLIM)"
    else
        echo "  - MCP:        medical_tools_service (via NATS)"
    fi
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
