# AGNTCY Multi-Organization Image Classification System

A multi-organization image classification routing system built on the AGNTCY framework. Routes classification requests across multiple organizations' agent clusters with LLM-based intent classification, verification, and automatic replanning.

## Quick Start

```bash
# Static mode (hardcoded agents)
./start_all.sh

# ADS mode (dynamic agent discovery)
./start_all.sh ads

# Stop all services
./stop_all.sh
```

## Architecture

```
User → Gateway (8080) → Planner (8083) → [Medical/Satellite/General Agents] → Verifier → Response
                              ↑                                                    ↓
                              └──────────────── Replan if FAIL ───────────────────┘
```

### Components

| Component | Port | Description |
|-----------|------|-------------|
| **Gateway** | 8080 | API entry point, image upload to MinIO |
| **Planner** | 8083 | LangGraph workflow with LLM intent classification |
| **Medical Agent** | 9001 | Medical image classification (X-ray, CT, MRI) |
| **Satellite Agent** | 9002 | Satellite/aerial image classification |
| **General Agent** | 9003 | General object/scene classification |
| **Verifier** | - | Result verification (confidence gate, ensemble voting) |

### Infrastructure (Docker)

| Service | Port | Description |
|---------|------|-------------|
| **NATS** | 4222 | Message transport for A2A protocol |
| **MinIO** | 9010 | Object storage for images |
| **ADS** | 8888 | Agent Directory Service (gRPC) |

## Two Discovery Modes

### Static Mode (Default)
```bash
./start_all.sh
```
- Uses hardcoded agent URLs
- No ADS services needed
- Simpler setup for development

### ADS Mode (Dynamic)
```bash
./start_all.sh ads
```
- Discovers agents from ADS registry
- Agents published via OASF records
- Production-ready dynamic discovery

## API Usage

### Submit Classification

```bash
curl -X POST http://localhost:8080/v1/classify \
  -F "image=@chest_xray.jpg" \
  -F "prompt=Analyze this chest X-ray for abnormalities" \
  -F "min_confidence=0.7"
```

Response:
```json
{
  "task_id": "req-20260206-103045-abc123",
  "status": "PROCESSING",
  "poll_url": "/v1/classify/req-20260206-103045-abc123"
}
```

### Poll for Result

```bash
curl http://localhost:8080/v1/classify/req-20260206-103045-abc123
```

Response:
```json
{
  "status": "COMPLETED",
  "result": {
    "label": "pneumonia",
    "confidence": 0.89,
    "top_k": [...]
  },
  "intent": {
    "domain": "medical",
    "confidence": 0.98
  },
  "iterations": 1
}
```

## Planner Workflow (LangGraph)

```
START → supervisor (LLM intent) → discover_agents → route_decision
                                                         ↓
                              ┌───────────────────────────┴────────────────┐
                              ↓                                            ↓
                         route_simple                              route_ensemble
                              ↓                                            ↓
                              └─────────→ execute_tasks (A2A) ←───────────┘
                                                 ↓
                                     reflection (LLM evaluate)
                                                 ↓
                                           check_status
                                                 ↓
                              ┌──────────────────┼──────────────────┐
                              ↓                  ↓                  ↓
                           success            replan           max_replans
                              ↓                  ↓                  ↓
                      finalize_response   → supervisor      finalize_response
                              ↓                                    ↓
                             END                                  END
```

**LLM Calls per Request:** 2 calls/iteration × max 3 iterations = up to 6 LLM calls

## Project Structure

```
Agentic_Network_Project/
├── start_all.sh               # Main entry: start all services
├── stop_all.sh                # Main entry: stop all services
├── agents/                    # Classifier Agents (A2A)
│   ├── org_a_medical/         # Medical (port 9001)
│   ├── org_b_satellite/       # Satellite (port 9002)
│   └── org_c_general/         # General (port 9003)
├── services/
│   ├── gateway/               # API Gateway (port 8080)
│   ├── planner/               # LangGraph Planner (port 8083)
│   └── verifier/              # Result Verification
├── shared/
│   ├── discovery/             # Agent Discovery (Static/ADS)
│   ├── schemas/               # Pydantic Models
│   └── utils/                 # Utilities
├── scripts/                   # All shell scripts
│   ├── start_*.sh             # Individual service starters
│   ├── start_ads.sh           # ADS services
│   ├── stop_ads.sh
│   └── publish_agent_records* # ADS publishing
├── config/                    # LLM Configuration
├── frontend/                  # Web UI
├── infrastructure/            # Docker (NATS + MinIO)
└── oasf_records/              # Agent Records (OASF)
```

## Configuration

### Environment Variables

```bash
# LLM Model
export LLM_MODEL=openai/gpt-4o-mini

# ADS Server (for ads mode)
export ADS_SERVER_ADDRESS=localhost:8888

# Agent Ports
export MEDICAL_AGENT_PORT=9001
export SATELLITE_AGENT_PORT=9002
export GENERAL_AGENT_PORT=9003
```

### LLM Setup

Create `.env` file:
```
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

## Verification Mechanisms

1. **Confidence Gate**: Reject results below threshold (default: 0.7)
2. **Ensemble Voting**: Multiple agents must agree (2/3 majority)
3. **Replan**: Retry with different strategy on failure (max 3 attempts)

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- OpenAI or Anthropic API key

## Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start services
./start_all.sh
```

## License

Apache-2.0 License
