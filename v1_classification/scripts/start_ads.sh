#!/bin/bash
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

# Start ADS (Agent Directory Service) components
# This script starts the directory services needed for agent discovery

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Starting ADS services..."

# Start ADS core services (zot must start first as dir-api-server depends on it)
docker-compose -f scripts/docker-compose-ads.yaml --profile ads up -d

echo "Waiting for services to be ready..."
sleep 10

# Check service status
echo ""
echo "=== ADS Service Status ==="
docker-compose -f scripts/docker-compose-ads.yaml ps | grep -E "(dir-api-server|dir-mcp-server|zot)" || echo "No ADS services running"

echo ""
echo "=== Port Check ==="
nc -zv localhost 8888 2>&1 && echo "  dir-api-server (gRPC): OK" || echo "  dir-api-server (gRPC): FAILED"
nc -zv localhost 8889 2>&1 && echo "  dir-api-server (HTTP): OK" || echo "  dir-api-server (HTTP): FAILED"
nc -zv localhost 5555 2>&1 && echo "  zot (OCI Registry): OK" || echo "  zot (OCI Registry): FAILED"

echo ""
echo "ADS services started!"
echo ""
echo "To publish agent cards, run:"
echo "  ./scripts/publish_agent_records.sh"
