#!/bin/bash
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

# Publish agent records to ADS
# This script starts the OASF translation service and publishes agent cards

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Agent Record Publishing Script ==="
echo ""

# Check if ADS services are running
if ! nc -z localhost 8888 2>/dev/null; then
    echo "ERROR: ADS services not running. Please start them first:"
    echo "  ./scripts/start_ads.sh"
    exit 1
fi

# Start OASF translation service if not running
if ! nc -z localhost 31234 2>/dev/null; then
    echo "Starting OASF translation service..."
    docker-compose -f scripts/docker-compose-ads.yaml --profile ads-publish up -d oasf-translation-service

    echo "Waiting for OASF service to be ready..."
    sleep 5

    # Verify service is up
    if ! nc -z localhost 31234 2>/dev/null; then
        echo "ERROR: OASF translation service failed to start"
        exit 1
    fi
    echo "OASF translation service started."
fi

echo ""
echo "Publishing agent records..."
echo ""

# Activate virtual environment (consistent with other project scripts)
source "$PROJECT_DIR/.venv/bin/activate"
export PYTHONPATH="$PROJECT_DIR"

# Run the Python publish script
python -m scripts.publish_agent_records

echo ""
echo "=== Publishing Complete ==="
echo ""
echo "Published CIDs are saved to: published_cids.json"
echo ""
echo "To stop OASF translation service (optional):"
echo "  docker-compose -f scripts/docker-compose-ads.yaml --profile ads-publish down"
