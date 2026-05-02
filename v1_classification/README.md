# AGNTCY Multi-Organization Image Classification System

A multi-organization image classification routing system built on the AGNTCY framework. Routes classification requests across multiple organizations' agent clusters with LLM-based intent classification, verification, and automatic replanning.

## Architecture

```
User → Gateway (8080) → Planner (8083) → [Medical/Satellite/General Agents] → Verifier → Response
                              ↑                    ↕ MCP (optional)                ↓
                              └──────────────── Replan if FAIL ───────────────────┘
```

### Agents

| Agent | Port | Org | Framework | MCP |
|-------|------|-----|-----------|-----|
| **Medical Agent** | 9001 | Org A | LangGraph ReAct | Yes (default on) |
| **Satellite Agent** | 9002 | Org B | CrewAI | No |
| **General Agent** | 9003 | Org C | LlamaIndex Workflow | No |

Each agent belongs to a different organization and independently decides whether to use MCP tools. This is configured in each agent's startup script (`scripts/start_<agent>.sh`), not globally.

### Services

| Service | Port | Description |
|---------|------|-------------|
| **Gateway** | 8080 | API entry point, image upload to MinIO |
| **Planner** | 8083 | LangGraph supervisor, LLM agent selection, ADS discovery |
| **MCP Server** | NATS | Medical tools (literature search, reference, confidence adjustment) |

### Infrastructure (Docker)

| Service | Port | Description |
|---------|------|-------------|
| **NATS** | 4222 | Message transport for A2A protocol |
| **MinIO** | 9010 | Object storage for images |
| **ADS** | 8888 | Agent Directory Service (gRPC) |

### Observability (Optional)

| Service | Port | Description |
|---------|------|-------------|
| **ClickHouse** | 8123 | Trace/metrics storage |
| **OTel Collector** | 4318 | Receives OTLP data from agents |
| **Grafana** | 3001 | Visualization dashboard |

All agents are instrumented with [IOA Observe SDK](https://github.com/agntcy/ioa-observe-sdk) for distributed tracing. When the observability stack is running, traces are automatically exported to ClickHouse via the OTel Collector and viewable in Grafana.

## Prerequisites

- Python 3.12+
- Docker
- OpenAI or Anthropic API key

## Installation

```bash
# Clone the repository
git clone git@github.com:SwordXiaoJ/Agentic-MAS.git
cd Agentic-MAS

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your LLM model and API key:
#   LLM_MODEL=openai/gpt-4o-mini    (or other supported models)
#   OPENAI_API_KEY=your-key-here
```

## Running the System

### 1. Start Observability (optional, run once)

```bash
./scripts/start_observability.sh
```

This starts ClickHouse + OTel Collector + Grafana in Docker containers. These persist across `stop_all.sh` — only stopped explicitly with `./scripts/stop_observability.sh`.

### 2. Start ADS (Agent Directory Service)

```bash
./scripts/start_ads.sh
./scripts/publish_agent_records.sh
```

### 3. Start backend services

```bash
./start_all.sh          # NATS transport (default)
./start_all.sh slim     # SLIM transport (alternative)
```

This starts (in order):
1. Infrastructure (NATS + MinIO, optionally SLIM)
2. MCP Server (always on; agents decide individually whether to use)
3. Medical Agent (Org A, MCP enabled)
4. Satellite Agent (Org B)
5. General Agent (Org C)
6. Planner (ADS discovery)
7. Gateway

### 4. Start frontend

```bash
cd frontend
npm install
npm run dev
```

### Stop services

```bash
./stop_all.sh                       # Stop agents + infrastructure (keeps observability)
./scripts/stop_observability.sh     # Stop observability stack
./scripts/stop_ads.sh               # Stop ADS
```

### Observability UI

After starting the observability stack and running the system:

- Open **Grafana** at `http://localhost:3001` (login: `admin` / `admin`)
- Go to **Explore** → select **ClickHouse** datasource
- Query the `otel_traces` table to see agent call chains, latencies, and cross-service traces

## License

Apache-2.0 License
