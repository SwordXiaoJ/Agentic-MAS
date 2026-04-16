#!/bin/bash
# Start General Classifier Agent (A2A)

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)
export GENERAL_AGENT_PORT=${GENERAL_AGENT_PORT:-9003}
export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}
export FARM_BROADCAST_TOPIC=agents.broadcast

echo "=============================================="
echo "General Classifier Agent (Org C) - A2A"
echo "=============================================="
echo "Port: $GENERAL_AGENT_PORT"
echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
echo ""

python3 -m agents.org_c_general.main
