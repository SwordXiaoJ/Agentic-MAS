#!/bin/bash
# Start Medical Classifier Agent (A2A)

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)
export MEDICAL_AGENT_PORT=${MEDICAL_AGENT_PORT:-9001}
export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}
export FARM_BROADCAST_TOPIC=${FARM_BROADCAST_TOPIC:-agents.broadcast}

# MCP settings (inherited from start_all.sh if mcp mode)
export USE_MCP=${USE_MCP:-false}
export MCP_TOPIC=${MCP_TOPIC:-medical_tools_service}

echo "=============================================="
echo "Medical Classifier Agent (Org A) - A2A"
echo "=============================================="
echo "Port: $MEDICAL_AGENT_PORT"
echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
echo "Endpoint: $TRANSPORT_SERVER_ENDPOINT"
echo "MCP Enabled: $USE_MCP"
if [ "$USE_MCP" == "true" ]; then
    echo "MCP Topic: $MCP_TOPIC"
fi
echo ""

python3 -m agents.org_a_medical.main
