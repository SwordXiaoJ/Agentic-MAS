#!/bin/bash
# Start Planner Agent (A2A)
#
# Usage:
#   ./start_planner.sh          # Static discovery (default)
#   ./start_planner.sh ads      # ADS discovery (requires ADS services running)

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)
export PLANNER_PORT=${PLANNER_PORT:-8083}
export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}
export LLM_MODEL=${LLM_MODEL:-openai/gpt-4o-mini}

# Discovery mode: static (default) or ads
if [ "$1" == "ads" ]; then
    export DISCOVERY_MODE=ads
    export ADS_SERVER_ADDRESS=${ADS_SERVER_ADDRESS:-localhost:8888}
    echo "=============================================="
    echo "Planner Agent (Supervisor) - A2A + ADS"
    echo "=============================================="
    echo "Port: $PLANNER_PORT"
    echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
    echo "Discovery: ADS ($ADS_SERVER_ADDRESS)"
    echo "LLM Model: $LLM_MODEL"
else
    export DISCOVERY_MODE=static
    echo "=============================================="
    echo "Planner Agent (Supervisor) - A2A"
    echo "=============================================="
    echo "Port: $PLANNER_PORT"
    echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
    echo "Discovery: Static (hardcoded agents)"
    echo "LLM Model: $LLM_MODEL"
fi
echo ""

python3 -m services.planner.main
