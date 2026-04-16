# Project Guide — AGNTCY Image Classification Network

## What This System Does

A multi-organization image classification network. Users submit images, the system automatically routes them to the best specialized agent (medical, satellite, or general), verifies the result, and returns the classification with evidence(MCP enabled).

```
User → Gateway → Planner → [Medical Agent / Satellite Agent / General Agent] → Verifier → Response
                    ↑                                                              │
                    └──────────────── Replan if FAIL (up to 3×) ──────────────────┘
```

---

## Directory Structure

```
Agentic_Network_Project/
├── services/                        # Platform services
│   ├── gateway/                     # HTTP API entry point (port 8080)
│   │   ├── main.py                 # FastAPI server
│   │   ├── api/classify.py         # /v1/classify endpoint
│   │   └── storage/minio_client.py # Image upload to MinIO
│   ├── planner/                     # Orchestrator (port 8083)
│   │   ├── main.py                 # FastAPI server
│   │   ├── agent_langgraph.py      # 7-node LangGraph workflow (core logic)
│   │   ├── tools.py                # A2A communication to agents
│   │   └── shared.py               # Factory initialization
│   └── verifier/                    # Result verification
│       ├── main.py                 # Verification orchestrator
│       ├── confidence_gate.py      # Confidence threshold check
│       ├── ensemble_vote.py        # Multi-agent voting
│
├── agents/                          # Classification agents (one per organization)
│   ├── org_a_medical/              # Medical image classifier (port 9001)
│   │   ├── main.py                 # A2A server entry point
│   │   ├── card.py                 # Agent identity (A2A card + OASF skills/domains)
│   │   ├── agent.py                # LangGraph ReAct workflow
│   │   └── agent_executor_a2a.py   # A2A request → classify → A2A response
│   ├── org_b_satellite/            # Satellite classifier (port 9002, CrewAI)
│   └── org_c_general/              # General classifier (port 9003, LlamaIndex)
│
├── shared/                          # Shared code
│   ├── discovery/                   # How the planner finds agents
│   │   ├── base.py                 # Abstract interface
│   │   ├── static_discovery.py     # Hardcoded 3 agents (default)
│   │   └── ads_discovery.py        # Dynamic discovery via ADS/Directory
│   ├── schemas/                     # Pydantic data models
│   │   ├── request.py              # ClassificationRequest
│   │   ├── result.py               # ClassificationResult
│   │   ├── route_decision.py       # RouteDecision, SelectedAgent
│   │   ├── verification.py         # VerificationReport
│   │   └── agent_record.py         # AgentRecord, AgentSkill
│   └── utils/
│       ├── logging.py              # Structured logging
│
├── config/
│   ├── llm_config.py               # LLM initialization (OpenAI/Anthropic/Azure/Ollama)
│   └── security_config.py          # SLIM security settings (TLS/JWT/MLS/SPIRE)
│
├── infrastructure/
│   ├── docker-compose.yml          # NATS, MinIO, SLIM, observability stack
│   └── slim/config.yaml            # SLIM gateway configuration
│
├── scripts/
│   ├── start_infrastructure.sh     # Start Docker containers
│   ├── start_medical_agent.sh      # Start individual services
│   ├── start_planner.sh
│   ├── start_gateway.sh
│   ├── start_ads.sh                # Start Agent Directory Service
│   ├── publish_agent_records.sh    # Publish agent cards to ADS
│   ├── start_observability.sh      # Start ClickHouse + OTel + Grafana
│   └── docker-compose-ads.yaml     # ADS Docker services
│
├── oasf_records/                    # Generated OASF records (from publish_agent_records.sh)
├── frontend/                        # Web UI
├── .env.example                     # Environment template
├── requirements.txt                 # Python dependencies
├── start_all.sh                     # Start everything
└── stop_all.sh                      # Stop everything
```

---

## Ports

| Service | Port | Description |
|---------|------|-------------|
| Gateway | 8080 | User-facing API |
| Planner | 8083 | Orchestrator |
| Medical Agent | 9001 | Org A |
| Satellite Agent | 9002 | Org B |
| General Agent | 9003 | Org C |
| NATS | 4222 | Message transport |
| MinIO | 9010 | Image storage |
| SLIM | 46357 | Alternative transport (optional) |
| ADS | 8888 | Agent Directory Service (optional) |
| ClickHouse | 9000 | Trace storage (optional) |
| Grafana | 3001 | Dashboards (optional) |

---


## Request Flow — Step by Step

### 1. Gateway receives request

`services/gateway/api/classify.py`:
- Accepts image + prompt via `POST /v1/classify`
- Uploads image to MinIO, generates presigned URL
- Creates `ClassificationRequest` and sends to Planner

### 2. Planner orchestrates the workflow

`services/planner/agent_langgraph.py` — a 7-node LangGraph:

```
supervisor_node ──→ discover_agents ──→ route_decision ──→ execute_tasks
      │                                                         │
      │  LLM: Intent Guard                                      │  A2A call to
      │  LLM: Agent Router                                      │  selected agent(s)
      │                                                         │
      │                                                         ▼
      │                    check_status ◄──── reflection_node
      │                        │                    │
      │                   ┌────┴────┐          LLM: evaluate
      │                   │         │          results quality
      │                  PASS     FAIL
      │                   │         │
      │                   ▼         └──→ replan (loop back to supervisor)
      │            finalize_response
      │                   │
      │                   ▼
      └──────────── return result
```

**supervisor_node** makes 2 LLM calls:
1. **Intent Guard** — is this a classification request? (accept/reject)
2. **Agent Router** — which agent(s) should handle this? (medical/satellite/general)

**execute_tasks** sends the request to the selected agent via A2A protocol:
- `tools.py → send_message_to_agent()` — creates A2A client, sends JSON-RPC message

**reflection_node** makes 1 LLM call:
- Evaluates whether the result is good enough or should replan

### 3. Agent executes classification

Each agent has a different framework but the same interface:

| Agent | Framework | Workflow |
|-------|-----------|----------|
| Medical (Org A) | LangGraph | ReAct loop: reason → tool/classify → observe → repeat |
| Satellite (Org B) | Pure Python
| General (Org C) | LlamaIndex | Workflow with step-based execution |

**Medical Agent ReAct loop** (`agents/org_a_medical/agent.py`):

```
preprocess → reason → [act_tool | act_classify] → observe → reason → ... → finalize
               │                                                │
               │  LLM decides next action:                      │
               │  - classify_image                              │
               │  - search_medical_literature (MCP)             │
               │  - get_medical_reference (MCP)                 │
               │  - done                                        │
               └────────────────────────────────────────────────┘
```

### 4. Verifier checks result

`services/verifier/main.py` runs up to 2 tests:
- **Confidence Gate**: is confidence > threshold (default 0.75)?
- **Ensemble Vote**: if multiple agents, do they agree?

Returns `PASS` / `FAIL` / `INCONCLUSIVE`. If `FAIL`, planner replans (up to 3 times).

---

## Key Code Files to Read

| Priority | File | What It Does |
|----------|------|-------------|
| 1 | `services/planner/agent_langgraph.py` | The core orchestration logic — 7 LangGraph nodes |
| 2 | `agents/org_a_medical/agent.py` | Medical ReAct workflow — shows how agents work |
| 3 | `agents/org_a_medical/card.py` | Agent identity definition (A2A card + OASF metadata) |
| 4 | `services/planner/tools.py` | How planner talks to agents (A2A protocol) |
| 5 | `shared/schemas/request.py` | Data model for classification requests |
| 6 | `shared/schemas/result.py` | Data model for classification results |
| 7 | `shared/discovery/static_discovery.py` | How planner discovers available agents |
| 8 | `services/verifier/main.py` | Verification logic |
| 9 | `config/llm_config.py` | LLM initialization |
| 10 | `start_all.sh` | Startup sequence |

---

## How Each Agent Is Built

Every agent has 4 files:

### `card.py` — Identity

```python
AGENT_CARD = AgentCard(
    name="Medical Image Classifier - Organization A",
    url="http://localhost:9001",
    skills=[AgentSkill(
        id="medical_image_classification",
        name="Medical Image Classification",
        tags=["medical", "xray", "ct_scan", "mri", "pneumonia"],
    )],
    defaultInputModes=["image/jpeg", "image/png", "text"],
    defaultOutputModes=["text", "application/json"],
)

# OASF standard classification for ADS publishing
OASF_SKILLS = [{"name": "images_computer_vision/image_classification", "id": 203}]
OASF_DOMAINS = [{"name": "healthcare/medical_technology", "id": 901}]
```

### `agent.py` — Workflow

Implements the classification logic. Can use any framework:
- LangGraph (medical)
- LlamaIndex (general)

Must expose a `classify(request) → ClassificationResult` method.

### `agent_executor_a2a.py` — A2A Bridge

Translates between A2A protocol and the agent's internal interface:
- Receives A2A `SendMessageRequest`
- Extracts image URL and prompt
- Calls `agent.classify()`
- Returns A2A `Message` with result

### `main.py` — Server

Starts the A2A farm server:

```python
agent = MedicalClassifierAgent()
executor = MedicalAgentExecutor(agent)
app = A2AStarletteApplication(agent_card=AGENT_CARD, http_handler=executor)

# Run HTTP server + transport bridge in parallel
await asyncio.gather(
    run_http_server(app, port=9001),
    run_transport_bridge(app, transport_type="NATS")
)
```

---

## How to Add a New Agent

1. **Create directory**: `agents/org_d_newtype/`

2. **Create `card.py`**: Define agent identity
   - Copy from `org_a_medical/card.py`
   - Change: name, URL (port 9004), skills, tags, OASF_SKILLS, OASF_DOMAINS

3. **Create `agent.py`**: Implement classification
   - Must have `async def classify(request) -> ClassificationResult`
   - Use any framework (LangGraph, CrewAI, LlamaIndex, or plain Python)

4. **Create `agent_executor_a2a.py`**: A2A bridge
   - Copy from `org_a_medical/agent_executor_a2a.py`
   - Change: import your agent class

5. **Create `main.py`**: Server entry point
   - Copy from `org_a_medical/main.py`
   - Change: port, agent class imports

6. **Create startup script**: `scripts/start_newtype_agent.sh`
   - Copy from `scripts/start_medical_agent.sh`
   - Change: port, module path

7. **Register the agent**:
   - **Static mode**: Add to `shared/discovery/static_discovery.py` `_initialize_agents()`
   - **ADS mode**: Run `./scripts/publish_agent_records.sh` (auto-discovers from card.py)

8. **Add to `start_all.sh`**: Add the new agent startup line



## Environment Variables

### Required

```bash
OPENAI_API_KEY=sk-...              # LLM API key
LLM_MODEL=openai/gpt-4o-mini      # Model (format: provider/model)
```

### Optional

```bash
# Discovery
DISCOVERY_MODE=static              # "static" (default) or "ads"
ADS_SERVER_ADDRESS=localhost:8888   # ADS gRPC address

# Transport
DEFAULT_MESSAGE_TRANSPORT=NATS     # "NATS" (default) or "SLIM"

# Observability
OBSERVE_TRACE_CONTENT=true         # Capture LLM prompts/completions

# LLM tuning
OPENAI_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096
```

