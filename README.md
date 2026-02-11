# AGNTCY Multi-Organization Image Classification System

A multi-organization image classification routing system built on the AGNTCY framework. Routes classification requests across multiple organizations' agent clusters with LLM-based intent classification, verification, and automatic replanning.

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

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
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

## Running the System (ADS Mode Recommended)

You will need **3 terminals**:

### Terminal 1 — Start backend services
```bash
source .venv/bin/activate
./start_all.sh
```

### Terminal 2 — Start ADS and publish agent records
```bash
./scripts/start_ads.sh
./scripts/publish_agent_records.sh
```

### Terminal 3 — Start frontend
```bash
cd frontend
npm install
npm run dev
```

### Static Mode (Alternative)
```bash
./start_all.sh
```
- Uses hardcoded agent URLs, no ADS needed
- Simpler but not recommended for full functionality

### Stop all services
```bash
./stop_all.sh
```

## License

Apache-2.0 License
