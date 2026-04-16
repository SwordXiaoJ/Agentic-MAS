#!/bin/bash
# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

# Stop ADS (Agent Directory Service) components
# This script stops all directory services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Stopping ADS services..."

# Stop ADS services
docker-compose -f scripts/docker-compose-ads.yaml --profile ads down
docker-compose -f scripts/docker-compose-ads.yaml --profile ads-publish down 2>/dev/null || true

echo ""
echo "=== Remaining Services ==="
docker-compose -f scripts/docker-compose-ads.yaml ps

echo ""
echo "ADS services stopped!"
