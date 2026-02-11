#!/bin/bash
# Start Medical Tools MCP Server
#
# This MCP server provides medical literature search tools
# and runs via NATS/SLIM transport (Lungo style).
#
# Usage:
#   ./scripts/start_mcp_medical.sh

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}

echo "=============================================="
echo "Medical Tools MCP Server"
echo "=============================================="
echo "Transport: ${DEFAULT_MESSAGE_TRANSPORT:-NATS}"
echo "Endpoint: ${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}"
echo "Topic: medical_tools_service"
echo ""

python -m agents.mcp_servers.medical_tools_service
