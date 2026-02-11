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
