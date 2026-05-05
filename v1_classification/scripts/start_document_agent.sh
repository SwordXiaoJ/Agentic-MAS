#!/bin/bash
# Start Document Analysis Agent (Org D) — A2A + PydanticAI

set -euo pipefail

cd "$(dirname "$0")/.."

DOC_VENV_DIR=".venv-document"
DOC_REQS="agents/org_d_document/requirements.txt"

if [ ! -d "$DOC_VENV_DIR" ]; then
    echo "Creating isolated document-agent venv at $DOC_VENV_DIR..."
    python3 -m venv "$DOC_VENV_DIR"
fi

# shellcheck source=/dev/null
source "$DOC_VENV_DIR/bin/activate"

if [ ! -f "$DOC_REQS" ]; then
    echo "Error: missing requirements file at $DOC_REQS"
    exit 1
fi

echo "Installing/updating isolated dependencies from $DOC_REQS..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$DOC_REQS"

export PYTHONPATH=$(pwd)
export DOCUMENT_AGENT_PORT=${DOCUMENT_AGENT_PORT:-9004}
export DEFAULT_MESSAGE_TRANSPORT=${DEFAULT_MESSAGE_TRANSPORT:-NATS}
export TRANSPORT_SERVER_ENDPOINT=${TRANSPORT_SERVER_ENDPOINT:-nats://localhost:4222}
export FARM_BROADCAST_TOPIC=${FARM_BROADCAST_TOPIC:-agents.broadcast}

echo "=============================================="
echo "Document Analysis Agent (Org D) — PydanticAI"
echo "=============================================="
echo "Port: $DOCUMENT_AGENT_PORT"
echo "Venv: $DOC_VENV_DIR"
echo "Transport: $DEFAULT_MESSAGE_TRANSPORT"
echo ""

python3 -m agents.org_d_document.main
