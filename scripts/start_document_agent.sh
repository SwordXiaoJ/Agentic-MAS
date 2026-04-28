#!/bin/bash

# Ensure we're in the right directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=============================================="
echo "Starting Document Agent (Org D) - CrewAI"
echo "=============================================="

# Export PYTHONPATH to ensure modules can be found
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT

# Run the agent
python -m agents.org_d_document.main
