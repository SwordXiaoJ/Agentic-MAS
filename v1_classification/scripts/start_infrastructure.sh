#!/bin/bash
# Start Infrastructure Services (like Lungo)
# Uses docker-compose with profiles

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=============================================="
echo "Classification System Infrastructure"
echo "=============================================="

show_help() {
    echo ""
    echo "Usage: ./start_infrastructure.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)      Start NATS + MinIO"
    echo "  --with-slim    Start NATS + MinIO + SLIM"
    echo "  --full         Start NATS + MinIO + SLIM + Observability"
    echo "  --help         Show this help"
    echo ""
    echo "Profiles:"
    echo "  default        NATS (always started)"
    echo "  slim           SLIM transport (port 46357)"
    echo "  observability  ClickHouse + OTEL + Grafana"
    echo ""
}

COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"

case "$1" in
    --help)
        show_help
        exit 0
        ;;
    --with-slim)
        echo "Starting: NATS + MinIO + SLIM"
        docker-compose -f "$COMPOSE_FILE" up -d nats minio
        docker-compose -f "$COMPOSE_FILE" --profile slim up -d
        ;;
    --full)
        echo "Starting: NATS + MinIO + SLIM + Observability"
        docker-compose -f "$COMPOSE_FILE" --profile slim --profile observability up -d
        ;;
    *)
        echo "Starting: NATS + MinIO"
        docker-compose -f "$COMPOSE_FILE" up -d nats minio
        ;;
esac

echo ""
echo "✓ Infrastructure started!"
echo ""
echo "Services:"
docker-compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker ps --filter "name=classify" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
