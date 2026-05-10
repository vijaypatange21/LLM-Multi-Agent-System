# Quick Start Guide for Implementation

This guide helps developers understand the remaining implementation work in the repository.

Current repository state:
- Core abstractions, several agents, orchestration logic, API endpoints, evaluation code, and Docker support are already implemented.
- This guide focuses on the remaining persistence, worker, and production-hardening work.

## Getting Started

### 1. Read the Architecture First
```
1. README.md              - Overview
2. ARCHITECTURE.md        - Complete design
3. DESIGN_DECISIONS.md    - Why we made choices
```

### 2. Understand the Core Interfaces
```python
# backend/core/abstractions.py
from backend.core import BaseAgent, BaseTool, Orchestrator, ContextManager

# All your implementations extend these
```

### 3. Study the Data Models
```python
# backend/schemas/
AgentMessage          # Communication unit
SharedContext         # Conversation state
ToolDefinition        # Tool schema
ToolCall, ToolResult  # Request-response pair
ExecutionTrace        # Complete record
EvalResult            # Quality assessment
PromptVersion         # Versioned prompts
```

## Implementation Order (Recommended)

### Phase 1: Remaining Foundation Work (Weeks 1-2)
1. **Database Models** (`backend/database/`)
   - Conversation ORM model
   - ExecutionTrace model
   - SharedContext model
   - PromptVersion model
   - EvalResult model
   - Database migrations (Alembic)

2. **Configuration** (`config/`)
   - Settings class (Pydantic)
   - Environment variable loading
   - Validation

3. **Logging** (`backend/logging/`)
   - Structured JSON logging
   - OpenTelemetry setup
   - Correlation ID propagation

### Phase 2: Core Logic (Weeks 3-4)
1. **Queue System** (`backend/queue/`)
   - Redis connection pooling
   - Job enqueueing
   - Job dequeueing with retry logic
   - Dead letter queue

2. **Context Manager** (implement `backend/core/ContextManager`)
   - Get/set context
   - Version tracking
   - Concurrency handling

3. **Database Layer**
   - Repository pattern (ConversationRepository, etc.)
   - Query helpers
   - Transaction management

### Phase 3: Agents & Tools (Weeks 5-6)
1. **Example Agent** (`backend/agents/`)
   - SimpleAgent implementing BaseAgent
   - Test with mock tools
   - Trace generation

2. **Example Tool** (`backend/tools/`)
   - EchoTool implementing BaseTool
   - Proper error handling
   - Cost tracking

3. **Orchestrator** (`backend/orchestration/`)
   - SimpleOrchestrator implementing Orchestrator
   - Message routing
   - Tool execution

### Phase 4: API (Weeks 7-8)
1. **FastAPI Setup**
   - Application factory
   - Middleware setup (CORS, auth, logging)
   - Exception handlers

2. **Routes** (`backend/api/`)
   - POST /conversations
   - POST /conversations/{id}/messages
   - GET /conversations/{id}/stream (SSE)
   - GET /traces/{id}

3. **Request/Response Models**
   - Pydantic models for API input/output
   - Error responses

### Phase 5: Workers (Week 9)
1. **Worker Framework**
   - Base worker class
   - Signal handling
   - Database/queue connections

2. **Concrete Workers**
   - AgentWorker
   - ToolWorker
   - EvalWorker

### Phase 6: Streaming & Evaluation (Weeks 10-11)
1. **Streaming** (`backend/streaming/`)
   - SSE endpoint implementation
   - Event publishing to Redis
   - Client subscription management

2. **Evaluation** (`backend/evaluation/`)
   - Simple LLM evaluator
   - Metrics computation
   - Result storage

### Phase 7: Testing & Polish (Week 12)
1. **Unit Tests**
   - Mock implementations
   - Edge cases
   - Error paths

2. **Integration Tests**
   - E2E conversation flow
   - Multi-turn handling
   - Evaluation pipeline

3. **Load Testing**
   - Worker throughput
   - Database query performance
   - API latency

## Code Examples

### Implementing a Custom Agent

```python
# backend/agents/my_agent.py
from backend.core import BaseAgent
from backend.schemas import AgentMessage, ExecutionTrace, ExecutionStep

class MyAgent(BaseAgent):
    @property
    def agent_id(self) -> str:
        return "my_agent"
    
    @property
    def agent_version(self) -> str:
        return "1.0.0"
    
    def get_available_tools(self) -> List[ToolDefinition]:
        # Return tools this agent can use
        return []
    
    async def process_message(
        self,
        message: AgentMessage,
        context: SharedContext,
    ) -> ExecutionTrace:
        # 1. Create trace
        trace = ExecutionTrace(
            conversation_id=message.conversation_id,
            agent_id=self.agent_id,
            steps=[],
        )
        
        # 2. Add reasoning step
        step = ExecutionStep(
            step_type=ExecutionStepType.REASONING,
            description="Analyzing user message",
            reasoning="User asked for: " + message.content,
        )
        trace.steps.append(step)
        
        # 3. Optionally add tool calls
        # tool_call = ToolCall(...)
        # trace.steps.append(tool_call)
        
        # 4. Set final output
        trace.final_output = {"response": "Hello from my agent"}
        
        return trace
    
    async def validate_tool_call(self, tool_call: ToolCall) -> bool:
        return True
```

### Implementing a Custom Tool

```python
# backend/tools/my_tool.py
from backend.core import BaseTool
from backend.schemas import ToolDefinition, ToolCall, ToolResult

class MyTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="my_tool",
            name="My Tool",
            description="Does something useful",
            tool_type=ToolType.COMPUTE,
            input_schema={
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                }
            },
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            },
        )
    
    async def execute(
        self,
        tool_call: ToolCall,
        context: SharedContext,
    ) -> ToolResult:
        # 1. Extract arguments
        input_text = tool_call.arguments.get("input")
        
        # 2. Do work
        result = input_text.upper()  # Example
        
        # 3. Return result
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.SUCCESS,
            output={"result": result},
            execution_time_ms=10,
            actual_cost=0.0,
        )
```

### Creating a Database Migration

```python
# alembic/versions/001_initial.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'conversations',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('user_id', sa.String),
        sa.Column('created_at', sa.DateTime),
        sa.Column('status', sa.String),
    )

def downgrade():
    op.drop_table('conversations')
```

### Setting Up the API

```python
# backend/app.py
from backend.app import app
```

## Testing Pattern

```python
# tests/test_my_agent.py
import pytest
from backend.agents.my_agent import MyAgent
from backend.schemas import AgentMessage, MessageRole, SharedContext

@pytest.fixture
def agent():
    return MyAgent()

@pytest.fixture
def context():
    return SharedContext(
        conversation_id=uuid.uuid4(),
        user_intent="Test",
        facts={},
        constraints=[],
    )

@pytest.mark.asyncio
async def test_agent_processes_message(agent, context):
    message = AgentMessage(
        conversation_id=context.conversation_id,
        role=MessageRole.USER,
        content="Hello",
        agent_id="test",
        sequence_number=1,
    )
    
    trace = await agent.process_message(message, context)
    
    assert trace.status == "completed"
    assert len(trace.steps) > 0
```

## Debugging Tips

1. **Trace Issues**
   - Look at ExecutionTrace in database
   - Check steps in order
   - Verify tool calls and results

2. **Logging Issues**
   - Set LOG_LEVEL=DEBUG
   - Look for trace_id correlation
   - Check structured logs in aggregation system

3. **Queue Issues**
   - Check Redis queue depth: `redis-cli LLEN agent_execution_queue`
   - Check for jobs in DLQ
   - Verify worker connections

4. **Performance Issues**
   - Profile with trace_id
   - Identify slow components
   - Add database indexes if needed

## Common Gotchas

1. **Forgetting await**: All async functions need await
   ```python
   # ❌ Wrong
   trace = agent.process_message(message, context)
   
   # ✅ Right
   trace = await agent.process_message(message, context)
   ```

2. **Mutating Immutable Data**: Don't modify messages/traces
   ```python
   # ❌ Wrong
   message.content = "modified"
   
   # ✅ Right
   new_message = AgentMessage(..., content="new")
   ```

3. **Not Setting Versions**: Always version agents/tools
   ```python
   # ❌ Wrong
   agent_version = None
   
   # ✅ Right
   agent_version = "1.0.0"
   ```

4. **Hardcoding Timeouts**: Use configuration
   ```python
   # ❌ Wrong
   timeout = 30
   
   # ✅ Right
   timeout = settings.TOOL_TIMEOUT
   ```

## Key Files to Know

| File | Purpose |
|------|---------|
| `backend/core/abstractions.py` | Base interfaces |
| `backend/schemas/__init__.py` | All data models |
| `backend/schemas/messages.py` | AgentMessage |
| `backend/schemas/context.py` | SharedContext |
| `backend/schemas/tools.py` | Tools schemas |
| `backend/schemas/execution.py` | ExecutionTrace |
| `config/` | Configuration management |
| `ARCHITECTURE.md` | Complete design |
| `DESIGN_DECISIONS.md` | Why decisions |

## Questions?

1. **What goes in SharedContext?** → Facts, constraints, resources for ALL agents in conversation
2. **When to make a new Tool?** → When you need to interact with external systems
3. **When to make a new Agent?** → When you have different reasoning strategies
4. **How to debug failures?** → Look at ExecutionTrace + logs with trace_id
5. **How to add a feature?** → 1) Add to schema, 2) Implement in component, 3) Add tests

---

Good luck with implementation! Start with the remaining foundation work, follow the order, and refer back to the architecture docs as needed.
