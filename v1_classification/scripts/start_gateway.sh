#!/bin/bash

cd "$(dirname "$0")/.."

# Activate virtual environment
source .venv/bin/activate

export PYTHONPATH=$(pwd)
export GATEWAY_PORT=${GATEWAY_PORT:-8080}
export MINIO_ENDPOINT=${MINIO_ENDPOINT:-localhost:9010}
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export PLANNER_URL=${PLANNER_URL:-http://localhost:8083}

echo "Starting Classification Gateway..."
echo "Port: $GATEWAY_PORT"
echo "MinIO: $MINIO_ENDPOINT"
echo "Planner: $PLANNER_URL"
echo ""

python3 -m services.gateway.main
