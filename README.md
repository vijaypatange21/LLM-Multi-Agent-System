# LLM Multi-Agent Orchestration System

A production-grade, distributed multi-agent orchestration system for coordinating specialized LLM agents, managing tool invocations, and measuring quality at scale.

**Status**: Core abstractions, API entrypoint, evaluation harness, orchestration logic, and Dockerized development stack are in place. Persistence and worker durability remain the main incomplete areas.

## Documentation

- **[README_SENIOR.md](README_SENIOR.md)** ← Start here for comprehensive technical overview (20 min read)
  - Architecture, components, orchestration flow
  - Evaluation methodology, self-improving loop
  - Adversarial robustness, known limitations
  - Setup, API docs, development workflow
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Detailed component design
- **[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)** — Trade-offs and rationale

Focus is on:
- ✅ System architecture and design patterns
- ✅ Pydantic data schemas and contracts
- ✅ Core abstractions and interfaces
- ✅ Module organization and structure
- ✅ Configuration and deployment patterns
- ✅ Observability framework design

Implemented or available now:
- ✅ Concrete agent implementations for decomposition, retrieval/reasoning, synthesis, and critique
- ✅ API endpoints for query submission, traces, evaluations, prompt approval, and health
- ✅ Evaluation harness and prompt optimization workflow
- ✅ Docker Compose stack for API, worker, PostgreSQL, Redis, Grafana, and Loki
- ✅ Tests

Still design-first or incomplete:
- ⏳ Database models and migrations
- ⏳ Durable queue-backed production worker runtime

See [ARCHITECTURE.md](./ARCHITECTURE.md) for complete design.

## Quick Start (Architecture Overview)

### Core Abstractions

```python
# Base interfaces for extensibility
from backend.core import BaseAgent, BaseTool, Orchestrator, ContextManager

class MyAgent(BaseAgent):
    """Implement your agent logic here"""
    async def process_message(self, message, context):
        # Reasoning, tool calls, decision-making
        pass

class MyTool(BaseTool):
    """Implement your tool here"""
    async def execute(self, tool_call, context):
        # External system interaction
        pass
```

### Data Schemas

```python
# Strongly-typed data contracts
from backend.schemas import (
    AgentMessage,
    SharedContext,
    ToolCall,
    ToolResult,
    ExecutionTrace,
    EvalResult,
    PromptVersion,
)

# All data validated by Pydantic
message = AgentMessage(
    conversation_id=uuid.uuid4(),
    role=MessageRole.AGENT,
    content="I need to search for information",
    agent_id="researcher_agent",
)
```

## Architecture

### System Components

```
┌─────────────────────────────────────────┐
│     FastAPI REST API                    │
│  (Requests, SSE streaming, routing)     │
└────────────┬────────────────────────────┘
             │
             ↓
    ┌────────────────────┐
    │  Redis Queues      │
    │ (Job distribution) │
    └────────┬───────────┘
             │
    ┌────────┼─────────┐
    ↓        ↓         ↓
   Agent   Tool      Eval
  Workers  Workers  Workers
    │        │         │
    └────────┼─────────┘
             ↓
    ┌────────────────────┐
    │  PostgreSQL DB     │
    │ (Persistence)      │
    └────────────────────┘
```

### Key Modules

| Module | Purpose | 
|--------|---------|
| `backend/core/` | Base interfaces (Agent, Tool, Orchestrator) |
| `backend/schemas/` | Pydantic data models |
| `backend/agents/` | Agent implementations |
| `backend/tools/` | Tool implementations |
| `backend/orchestration/` | Orchestration strategies |
| `backend/database/` | ORM and data access |
| `backend/queue/` | Redis queue management |
| `backend/logging/` | Observability and tracing |
| `backend/streaming/` | SSE real-time updates |
| `backend/evaluation/` | Quality framework |
| `backend/prompts/` | Prompt versioning |
| `backend/api/` | FastAPI endpoints |
| `backend/workers/` | Background workers |

## Design Highlights

### 1. **Abstraction-Driven**
Everything inherits from base interfaces, enabling pluggable implementations:
- `BaseAgent`: Write your agent logic
- `BaseTool`: Write your tool integrations
- `Orchestrator`: Define your workflow strategy

### 2. **Message-Passing Architecture**
- Components communicate via immutable `AgentMessage`
- Enables distributed execution and debugging
- Full trace ID propagation for observability

### 3. **Type-Safe Throughout**
- All data modeled with Pydantic
- Automatic validation and serialization
- IDE autocompletion and error detection
- Auto-generated API documentation

### 4. **Versioning First**
- Agents versioned (reproducibility)
- Tools versioned (compatibility)
- Prompts versioned (A/B testing, rollback)
- Traces record versions used

### 5. **Observable by Default**
- Structured logging with correlation IDs
- OpenTelemetry distributed tracing
- Metrics for monitoring
- Execution traces for debugging

### 6. **Cost-Aware**
- Track cost of every tool invocation
- Enforce budget constraints
- Per-agent and per-tool cost breakdown

### 7. **Production-Ready Patterns**
- Async/await throughout
- Error handling and retry logic
- Configuration management
- Health checks
- Graceful shutdown

## Core Schemas

### AgentMessage
Primary communication unit between agents and the system.
- `id`: Unique message ID
- `conversation_id`: Links messages in a session
- `trace_id`: Distributed tracing
- `role`: USER, AGENT, TOOL, SYSTEM
- `tool_calls`: Nested tool invocations

### SharedContext
Immutable ground truth for a conversation.
- `facts`: Observable truths
- `constraints`: Operational rules (budget, rate limits, etc.)
- `resources`: Available tools, APIs, databases
- `user_preferences`: Settings

### ToolCall & ToolResult
Request-response pair for tool invocation.
- Call: `tool_id`, `arguments`, `trace_id`
- Result: `status`, `output`, `execution_time_ms`, `actual_cost`

### ExecutionTrace
Complete record of agent reasoning.
- `steps`: Ordered list of actions
- `final_output`: What agent decided
- `status`: COMPLETED, FAILED, IN_PROGRESS
- `total_cost`: Spending
- `tokens_used`: Token accounting

### EvalResult
Quality assessment of outputs.
- `metrics`: Multi-dimensional scores
- `overall_pass`: Boolean gate
- `feedback`: Diagnostics

### PromptVersion
Immutable prompt snapshot.
- `content`: Template with variables
- `config`: LLM parameters
- `is_active`: Current version
- `version_number`: Semantic versioning

## Folder Structure

```
LLM-Multi-Agent-System/
├── Documentation
│   ├── README.md                    # Main README (points to README_SENIOR.md)
│   ├── README_SENIOR.md             # ← Comprehensive technical guide (start here)
│   ├── ARCHITECTURE.md              # Detailed component design
│   ├── DESIGN_DECISIONS.md          # Trade-offs and rationale
│   ├── IMPLEMENTATION_GUIDE.md      # Implementation roadmap
│   ├── API_IMPLEMENTATION_COMPLETE.md
│   └── requirements.txt
│
├── Deployment & Configuration
│   ├── docker-compose.yml           # Multi-service orchestration (API, worker, DB, Redis, Grafana, Loki)
│   ├── Dockerfile.api               # Production API image
│   ├── Dockerfile.worker            # Production worker image
│   ├── .dockerignore                # Ignore patterns for Docker builds
│   ├── .env.example                 # Environment variables template (NO hardcoded secrets)
│   ├── config/
│   │   └── README.md                # Configuration management guide
│   └── docker/
│       ├── README.md                # Container architecture guide
│       └── loki-config.yaml         # Loki log aggregation config
│
├── Scripts
│   └── scripts/
│       ├── wait-for-it.sh           # Wait for TCP service availability
│       └── wait-and-run.sh          # Wait for Postgres/Redis before starting worker
│
├── Source Code
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── app.py                   # ✅ FastAPI entry point (uvicorn target)
│   │   │
│   │   ├── core/                    # ✅ Base abstractions
│   │   │   ├── __init__.py
│   │   │   └── abstractions.py      # BaseAgent, BaseTool, Orchestrator, ContextManager
│   │   │
│   │   ├── schemas/                 # ✅ Pydantic data models
│   │   │   ├── __init__.py
│   │   │   ├── messages.py          # AgentMessage, MessageRole
│   │   │   ├── context.py           # SharedContext
│   │   │   ├── tools.py             # ToolCall, ToolResult, ToolDefinition
│   │   │   ├── execution.py         # ExecutionTrace, ExecutionStep
│   │   │   ├── evaluation.py        # EvalResult, EvalMetric
│   │   │   └── prompts.py           # PromptVersion
│   │   │
│   │   ├── agents/                  # ✅ Agent implementations
│   │   │   ├── __init__.py
│   │   │   ├── abstractions.py      # BaseAgent interface
│   │   │   ├── decomposition_agent.py
│   │   │   ├── retrieval_reasoning_agent.py
│   │   │   ├── synthesis_agent.py
│   │   │   ├── critique_agent.py
│   │   │   ├── schemas.py
│   │   │   ├── decomposition_utils.py
│   │   │   ├── examples.py
│   │   │   ├── IMPLEMENTATION_COMPLETE.md
│   │   │   └── DECOMPOSITION_GUIDE.md
│   │   │
│   │   ├── tools/                   # ✅ Tool implementations
│   │   │   ├── __init__.py
│   │   │   ├── standard_tools.py
│   │   │   ├── runtime.py
│   │   │   └── (custom tools go here)
│   │   │
│   │   ├── orchestration/           # ✅ Orchestration strategies
│   │   │   ├── __init__.py
│   │   │   ├── dynamic_orchestrator.py
│   │   │   ├── context_window.py
│   │   │   ├── routing.py
│   │   │   ├── state_machine.py
│   │   │   ├── schemas.py
│   │   │   ├── examples.py
│   │   │   ├── IMPLEMENTATION_COMPLETE.md
│   │   │   └── ORCHESTRATOR_GUIDE.md
│   │   │
│   │   ├── evaluation/              # ✅ Quality evaluation framework
│   │   │   ├── __init__.py
│   │   │   ├── harness.py           # EvaluationHarness, test cases
│   │   │   ├── test_cases.py        # Baseline, ambiguous, adversarial cases
│   │   │   ├── runner.py            # EvaluationRunner (main entry point)
│   │   │   ├── prompt_optimization.py  # MetaAgent, prompt diff generation
│   │   │   └── examples.py
│   │   │
│   │   ├── api/                     # ✅ FastAPI REST endpoints
│   │   │   ├── __init__.py
│   │   │   ├── production_endpoints.py  # Query, traces, evaluations, approvals
│   │   │   ├── observability_endpoints.py
│   │   │   └── schemas.py           # Request/response models
│   │   │
│   │   ├── observability/           # ✅ Logging, tracing, metrics
│   │   │   ├── __init__.py
│   │   │   ├── logs.py
│   │   │   ├── metrics.py
│   │   │   ├── sse_events.py
│   │   │   ├── trace_reconstruction.py
│   │   │   ├── trace_replay.py
│   │   │   └── orchestration_visibility.py
│   │   │
│   │   ├── database/                # ⏳ ORM models (planned)
│   │   │   └── __init__.py
│   │   │
│   │   ├── queue/                   # ⏳ Redis queue management
│   │   │   └── __init__.py
│   │   │
│   │   ├── streaming/               # ⏳ SSE real-time updates
│   │   │   └── __init__.py
│   │   │
│   │   ├── prompts/                 # ⏳ Prompt versioning system
│   │   │   └── __init__.py
│   │   │
│   │   ├── optimization/            # ✅ Prompt optimization
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py
│   │   │   └── prompt_optimizer.py
│   │   │
│   │   ├── logging/                 # ⏳ Structured logging
│   │   │   └── __init__.py
│   │   │
│   │   └── workers/                 # ⏳ Background job processors
│   │       └── __init__.py
│   │
│   └── tests/                       # ✅ Comprehensive test suite
│       ├── test_context_window.py
│       ├── test_critique_agent.py
│       ├── test_decomposition_agent.py
│       ├── test_evaluation_harness.py
│       ├── test_observability.py
│       ├── test_production_api.py
│       ├── test_prompt_optimization.py
│       ├── test_retrieval_reasoning_agent.py
│       ├── test_synthesis_agent.py
│       └── test_tool_runtime.py
│
├── Data & Results
│   └── evaluation_runs/
│       └── results_*.json           # Evaluation results (JSON, versioned by UUID)
│
└── CI/CD & Environment
    ├── .env                         # Local environment (git-ignored, create from .env.example)
    └── .env/                        # Python virtual environment (git-ignored)
```

**Legend**:
- ✅ = Implemented and tested
- ⏳ = Designed but not yet fully implemented
- = Architectural design only (kept for legacy sections in older docs)

## Design Principles

1. **Extensibility**: Implement interfaces, add new capabilities
2. **Testability**: Mock implementations for unit tests
3. **Observability**: Trace every decision, log everything
4. **Reliability**: Error handling, retries, circuit breakers
5. **Scalability**: Horizontal scaling via queues and workers
6. **Cost-consciousness**: Track and enforce budgets
7. **Reproducibility**: Version everything, store execution traces


## Configuration

See [config/README.md](./config/README.md) for configuration details.

Key configurations:
- Database connection string
- Redis URL
- LLM API keys
- Cost limits and budgets
- Timeouts (agent, tool, LLM)
- Logging level
- Worker counts

## Deployment

### Development
```bash
cp .env.example .env
docker-compose up --build
```

### Production
```bash
docker build -t agent-system:v1.0.0 -f Dockerfile.api .
docker build -t agent-worker:v1.0.0 -f Dockerfile.worker .
```

See [docker/README.md](./docker/README.md) for containerization details and [README_SENIOR.md](README_SENIOR.md) for the current runtime workflow.

## Contributing

When contributing, follow these principles:
1. Implement interfaces, don't create new ones
2. Use Pydantic schemas, validate all inputs
3. Add comprehensive docstrings explaining "why"
4. Include type hints on all functions
5. Follow async/await patterns
6. Add logging and tracing
7. Write tests for edge cases

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md): Complete system design
- [backend/core/abstractions.py](./backend/core/abstractions.py): Base interfaces
- [backend/schemas/](./backend/schemas/): Data models with examples
- [docker/README.md](./docker/README.md): Containerization
- [config/README.md](./config/README.md): Configuration

## Questions?

This is the foundational architecture. Each module includes detailed docstrings explaining:
- **WHY** this component exists
- **HOW** it fits with others
- **WHAT** to implement next

Start with [ARCHITECTURE.md](./ARCHITECTURE.md) for the big picture, then dive into specific modules.

---

**Status**: Architectural design complete. Ready for implementation.
