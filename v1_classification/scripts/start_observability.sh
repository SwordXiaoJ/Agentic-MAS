#!/bin/bash
# Start Observability Stack (ClickHouse + OTel Collector + Grafana)
#
# Usage: ./scripts/start_observability.sh

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$PROJECT_ROOT/infrastructure"
NETWORK="infrastructure_classify-network"

CLICKHOUSE_PASSWORD="otel123"

echo "=============================================="
echo "Starting Observability Stack"
echo "=============================================="

# Ensure network exists
if ! docker network ls --format '{{.Name}}' | grep -q "^${NETWORK}$"; then
    echo "Creating network: $NETWORK"
    docker network create "$NETWORK"
fi

# Remove stale containers
docker rm -f classify-clickhouse classify-otel-collector classify-grafana 2>/dev/null

# 1. ClickHouse
echo ""
echo "[1/3] Starting ClickHouse..."
docker run -d \
    --name classify-clickhouse \
    --network "$NETWORK" \
    -p 9009:9000 \
    -p 8123:8123 \
    -e CLICKHOUSE_DB=otel \
    -e CLICKHOUSE_USER=default \
    -e CLICKHOUSE_PASSWORD="$CLICKHOUSE_PASSWORD" \
    -v classify_clickhouse_data:/var/lib/clickhouse \
    clickhouse/clickhouse-server:latest > /dev/null

echo "  Waiting for ClickHouse..."
for i in $(seq 1 15); do
    if docker exec classify-clickhouse clickhouse-client --password "$CLICKHOUSE_PASSWORD" --query "SELECT 1" > /dev/null 2>&1; then
        echo "  ClickHouse ready."
        break
    fi
    sleep 1
done

# 2. OTel Collector
echo ""
echo "[2/3] Starting OTel Collector..."
docker run -d \
    --name classify-otel-collector \
    --network "$NETWORK" \
    -p 4317:4317 \
    -p 4318:4318 \
    -p 8890:8889 \
    -v "$INFRA_DIR/otel-collector-config.yaml:/etc/otel-collector-config.yaml" \
    otel/opentelemetry-collector-contrib:latest \
    --config=/etc/otel-collector-config.yaml > /dev/null

# 3. Grafana
echo ""
echo "[3/3] Starting Grafana..."
docker run -d \
    --name classify-grafana \
    --network "$NETWORK" \
    -p 3001:3000 \
    -e GF_SECURITY_ADMIN_USER=admin \
    -e GF_SECURITY_ADMIN_PASSWORD=admin \
    -e GF_INSTALL_PLUGINS=grafana-clickhouse-datasource \
    -v classify_grafana_data:/var/lib/grafana \
    -v "$INFRA_DIR/grafana-provisioning:/etc/grafana/provisioning" \
    grafana/grafana:latest > /dev/null

sleep 2

echo ""
echo "=============================================="
echo "Observability Stack Started!"
echo "=============================================="
echo ""
echo "  Grafana:        http://localhost:3001  (admin/admin)"
echo "  OTel Collector: http://localhost:4318  (OTLP HTTP)"
echo "  ClickHouse:     http://localhost:8123  (HTTP API)"
echo ""
echo "Stop with: ./scripts/stop_observability.sh"
echo ""
