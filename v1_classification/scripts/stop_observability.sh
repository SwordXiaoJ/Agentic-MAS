#!/bin/bash
# Stop Observability Stack (ClickHouse + OTel Collector + Grafana)
#
# Usage: ./scripts/stop_observability.sh

echo "Stopping Observability Stack..."

docker stop classify-otel-collector classify-grafana classify-clickhouse 2>/dev/null
docker rm -f classify-otel-collector classify-grafana classify-clickhouse 2>/dev/null

echo "Observability Stack stopped."
