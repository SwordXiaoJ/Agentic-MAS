#!/bin/bash
# Stop all AGNTCY services

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "========================================"
echo "Stopping AGNTCY System"
echo "========================================"
echo ""

# Stop processes recorded by start_all.sh
PID_FILE="$PROJECT_ROOT/.service_pids"
if [ -f "$PID_FILE" ]; then
    echo "Stopping recorded service processes..."
    while read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  Stopped PID $pid"
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
fi

# Kill any remaining Python service processes by port
echo ""
echo "Stopping Python services by port..."
for port in 8080 8082 8083 9001 9002 9003 9004; do
    pid=$(lsof -t -i :"$port" 2>/dev/null)
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null
        echo "  Stopped process on port $port (PID $pid)"
    fi
done

# Stop tmux sessions
if command -v tmux &> /dev/null; then
    if tmux has-session -t agntcy-simple 2>/dev/null; then
        echo "Stopping tmux session: agntcy-simple..."
        tmux kill-session -t agntcy-simple
    fi

    if tmux has-session -t agntcy 2>/dev/null; then
        echo "Stopping tmux session: agntcy..."
        tmux kill-session -t agntcy
    fi
fi

# Stop Docker infrastructure
echo ""
echo "Stopping Docker infrastructure..."

if [ -d "$PROJECT_ROOT/infrastructure" ]; then
    docker-compose -f "$PROJECT_ROOT/infrastructure/docker-compose.yml" down 2>/dev/null
fi

# Stop ADS services if running
echo ""
echo "Stopping ADS services..."
if [ -f "$PROJECT_ROOT/scripts/stop_ads.sh" ]; then
    "$PROJECT_ROOT/scripts/stop_ads.sh" 2>/dev/null
fi

# Also stop any stale containers by name pattern (including legacy names)
for container in classify-nats classify-minio classify-slim classify-clickhouse classify-otel-collector classify-grafana nats classification-nats lungo-nats classification-zot classification-dir-api-server classification-dir-mcp-server classification-oasf-translation; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$" 2>/dev/null; then
        docker stop "$container" 2>/dev/null
        docker rm "$container" 2>/dev/null
        echo "  Removed stale container: $container"
    fi
done

echo ""
echo "All services stopped"
echo ""
echo "To remove all data (MinIO, ClickHouse):"
echo "  cd infrastructure && docker-compose down -v"
echo ""
