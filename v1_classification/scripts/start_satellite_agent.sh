#!/bin/bash
# Start Satellite Classifier Agent (A2A)

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)
export SATELLITE_AGENT_PORT=${SATELLITE_AGENT_PORT:-9002}
export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}
export FARM_BROADCAST_TOPIC=agents.broadcast

echo "=============================================="
echo "Satellite Classifier Agent (Org B) - A2A"
echo "=============================================="
echo "Port: $SATELLITE_AGENT_PORT"
echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
echo ""

python3 -m agents.org_b_satellite.main
