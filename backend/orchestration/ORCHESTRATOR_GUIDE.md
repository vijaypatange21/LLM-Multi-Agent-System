# Dynamic Orchestrator Implementation Guide

## Overview

The **DynamicOrchestrator** is a production-grade multi-agent orchestration engine that:

- **Analyzes queries** to determine which agents are needed
- **Selects agents dynamically** at runtime based on capabilities and constraints  
- **Executes with no hardcoded chains** - adapts to different query types
- **Handles failures gracefully** with retries and fallbacks
- **Tracks all decisions** with structured logging
- **Enforces budgets** and constraints across execution
- **Provides transparency** via comprehensive execution traces

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. QUERY RECEIVED                                               │
│    User query & context arrive                                  │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. QUERY ANALYSIS                                               │
│    Extract intent, required capabilities, complexity            │
│    Decision: What skills are needed?                            │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. AGENT RANKING                                                │
│    Score each agent by suitability                              │
│    Decision: How good is each agent for this query?             │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. AGENT SELECTION                                              │
│    Select agents respecting budget & constraints                │
│    Decision: Which agents will we use?                          │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. EXECUTION PLAN                                               │
│    Create plan with selected agents and order                   │
│    Decision: In what order will agents execute?                 │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. AGENT EXECUTION                                              │
│    Execute each agent with error handling & retries             │
│    Decision: Handle failures gracefully                         │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. RESULT AGGREGATION                                           │
│    Combine results from all agents                              │
│    Decision: How to synthesize final output?                    │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. COMPLETION                                                   │
│    Return orchestration trace with full record                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Routing Policy (`routing.py`)

**Responsibility**: Decide which agents to use for a given query.

**Implementation**: `RuleBasedRoutingPolicy`

```python
# Query analysis: What is the user asking?
query_analysis = await routing_policy.analyze_query(query, context)
# Returns: intent, required_capabilities, complexity, time_sensitivity

# Agent scoring: How suitable is each agent?
score, reasoning = await routing_policy.score_agent(agent, query, analysis, context)
# Returns: 0-1 score and explanation

# Ranking: Order agents by suitability
ranked_agents = await routing_policy.rank_agents(query, agents, analysis, context)
# Returns: [(agent1, 0.9, "reason"), (agent2, 0.7, "reason"), ...]

# Selection: Pick agents respecting constraints
selected_agents, decisions = await routing_policy.select_agents(
    ranked_agents, context, budget
)
# Returns: agents to use and decisions explaining why each was selected/rejected
```

**Capability Mapping**:

| Keyword | Required Capabilities | Agents |
|---------|----------------------|--------|
| search | [search] | [search_agent, researcher_agent] |
| analyze | [analyze] | [analyzer_agent, reasoning_agent] |
| calculate | [compute] | [calculator_agent, analyst_agent] |
| query_data | [database] | [database_agent, analyst_agent] |

**Scoring Factors**:

- **Capability Match** (+0.2 per required capability)
- **Optional Capabilities** (+0.1 per optional capability)
- **User Preferences** (user-specified agent preferences)
- **Baseline** (0.5 starting score)

### 2. State Machine (`state_machine.py`)

**Responsibility**: Track orchestration execution flow through stages.

**States**:

```
PLANNING
   ↓
VALIDATION
   ↓
SCHEDULING
   ↓
EXECUTING
   ↓
COLLECTING_RESULTS
   ↓
AGGREGATING
   ↓
COMPLETED
```

**Prevents Invalid Transitions**: Can't execute before planning, can't complete before aggregating, etc.

**Tracks Timing**: How long in each state for performance analysis.

### 3. Structured Event Logger (`state_machine.py`)

**Responsibility**: Log all orchestration decisions with reasoning.

**Event Types**:

| Event | Meaning | Key Data |
|-------|---------|----------|
| QUERY_RECEIVED | User submitted query | query text |
| ANALYSIS_STARTED | Starting to analyze query | - |
| ROUTING_DECISION | Agent selected or rejected | agent_id, decision, score, reason |
| PLAN_CREATED | Execution plan finalized | agents, budget, time estimate |
| AGENT_STARTED | Beginning agent execution | agent_id |
| AGENT_COMPLETED | Agent finished successfully | agent_id, cost, tokens |
| AGENT_FAILED | Agent failed | agent_id, error, retry_count |
| RETRY_ATTEMPT | Retrying failed agent | agent_id, attempt_number |
| BUDGET_CONSTRAINT | Budget limit reached | current_cost, budget_limit |
| CONTEXT_UPDATED | Shared context modified | updates |
| RESULT_AGGREGATED | Results combined | summary |
| ORCHESTRATION_COMPLETED | Finished successfully | final_output, cost, tokens |
| ORCHESTRATION_FAILED | Fatal error occurred | error_message |

**Structured JSON Output**:

```json
{
  "event_type": "routing_decision",
  "message": "SELECTED agent search_agent",
  "stage": "planning",
  "elapsed_ms": 125.5,
  "trace_id": "550e8400-...",
  "conversation_id": "550e8400-...",
  "details": {
    "agent_id": "search_agent",
    "decision": "SELECTED",
    "score": 0.85
  },
  "decision_explanation": "Agent has required search capability"
}
```

### 4. Dynamic Orchestrator (`dynamic_orchestrator.py`)

**Responsibility**: Main orchestration logic - ties everything together.

**Main Entry Point**:

```python
orchestration_trace = await orchestrator.execute(
    conversation_id=uuid4(),
    initial_message=user_message,
    agents=available_agents,
)
```

**Execution Steps**:

1. **Create orchestration trace** - Container for all execution data
2. **Log query received** - Record what user asked
3. **Transition: PLANNING** - Enter planning stage
4. **Analyze query** - Extract intent and requirements
5. **Transition: VALIDATION** - Enter validation stage
6. **Rank agents** - Score all agents for suitability
7. **Select agents** - Pick subset respecting budget
8. **Create execution plan** - Finalize agent order and budgets
9. **Transition: SCHEDULING** - Enter scheduling stage
10. **Transition: EXECUTING** - Enter execution stage
11. **Execute agents** - Run each selected agent with retries
12. **Transition: COLLECTING_RESULTS** - Gather outputs
13. **Transition: AGGREGATING** - Enter aggregation stage
14. **Aggregate results** - Combine agent outputs
15. **Transition: COMPLETED** - Finish
16. **Log completion** - Record success/failure

## Error Handling & Retry Logic

### Retry Strategy

```python
for attempt in range(max_retries + 1):  # 0, 1, 2 for max_retries=2
    try:
        trace = await agent.process_message(message, context)
        return trace  # Success
    except Exception as e:
        if attempt < max_retries:
            # Log retry
            event_logger.log_agent_failed(..., retry_count=attempt+1)
            # Exponential backoff: 1s, 2s, 4s
            backoff_seconds = 2 ** attempt
            await asyncio.sleep(backoff_seconds)
        else:
            raise  # Give up after max retries
```

### Failure Scenarios

| Scenario | Handling |
|----------|----------|
| Agent timeout | Retry with exponential backoff |
| Agent error | Retry, then skip if exhausted |
| Budget exceeded | Stop execution, mark remaining agents rejected |
| No agents selected | Raise exception, orchestration fails |
| Aggregation error | Continue (attempt best-effort) |

## Orchestration Trace Output

The `OrchestrationTrace` contains:

```python
OrchestrationTrace(
    id: UUID,                              # Unique trace ID
    conversation_id: UUID,                 # Which conversation
    status: str,                           # completed, failed, timeout
    initial_query: str,                    # Original user query
    execution_plan: ExecutionPlan,         # What was planned
    routing_decisions: [RoutingDecision],  # Agents selected/rejected
    events: [OrchestrationEvent],          # All events in order
    agent_execution_order: [str],          # Order agents ran
    agent_results: {str: Dict},            # Results from each agent
    agent_execution_traces: {str: UUID},   # Links to ExecutionTrace
    final_output: Dict,                    # Aggregated output
    error_message: str,                    # If failed
    total_duration_ms: float,              # Total time
    total_cost: float,                     # Total cost
)
```

## Usage Examples

### Basic Usage

```python
from backend.orchestration import DynamicOrchestrator, RuleBasedRoutingPolicy
from backend.schemas import AgentMessage, MessageRole

# Create orchestrator
orchestrator = DynamicOrchestrator(
    routing_policy=RuleBasedRoutingPolicy(),
    max_retries=2,
)

# Create query
message = AgentMessage(
    conversation_id=uuid4(),
    role=MessageRole.USER,
    content="Find and analyze customer sentiment trends",
    agent_id="user",
    sequence_number=1,
)

# Execute
trace = await orchestrator.execute(
    conversation_id=message.conversation_id,
    initial_message=message,
    agents=[search_agent, analyzer_agent],
)

# Use results
print(f"Status: {trace.status}")
print(f"Agents used: {trace.agent_execution_order}")
print(f"Total cost: ${trace.total_cost}")
```

### Custom Routing Policy

```python
from backend.orchestration import RoutingPolicy

class CustomRoutingPolicy(RoutingPolicy):
    async def analyze_query(self, query, context):
        # Your custom analysis logic
        return {...}
    
    async def score_agent(self, agent, query, analysis, context):
        # Your custom scoring
        return (score, reasoning)
    
    async def rank_agents(self, query, agents, analysis, context):
        # Your custom ranking
        return [(agent1, score1, reason1), ...]
    
    async def select_agents(self, ranked_agents, context, budget):
        # Your custom selection
        return (selected_agents, decisions)

# Use custom policy
orchestrator = DynamicOrchestrator(routing_policy=CustomRoutingPolicy())
```

### Analyzing Results

```python
# View routing decisions
for decision in trace.routing_decisions:
    print(f"{decision.agent_id}: {decision.decision}")
    print(f"  Score: {decision.score}")
    print(f"  Reason: {decision.explanation}")

# View execution events
for event in trace.events:
    print(f"[{event.event_type.value}] {event.message}")
    print(f"  Stage: {event.current_stage.value}")
    print(f"  Time: {event.elapsed_time_ms}ms")

# View agent results
for agent_id, result in trace.agent_results.items():
    print(f"{agent_id}: {result['status']}")
    print(f"  Output: {result['output']}")
```

## Production Patterns

### Pattern 1: Budget-Aware Execution

```python
context = SharedContext(
    conversation_id=conv_id,
    user_intent=query,
    constraints=[
        ContextConstraint(
            name="budget",
            constraint_type="budget",
            value=5.0,  # Max $5.00 cost
        )
    ],
)

trace = await orchestrator.execute(..., context=context)
```

The orchestrator will skip agents if budget is exhausted.

### Pattern 2: Required Agents

```python
context = SharedContext(
    ...,
    constraints=[
        ContextConstraint(
            name="required_agents",
            constraint_type="required_agents",
            value=["compliance_agent"],  # Always use this agent
        )
    ],
)
```

### Pattern 3: Excluded Agents

```python
context = SharedContext(
    ...,
    constraints=[
        ContextConstraint(
            name="excluded_agents",
            constraint_type="excluded_agents",
            value=["external_api_agent"],  # Never use this agent
        )
    ],
)
```

### Pattern 4: User Preferences

```python
context = SharedContext(
    ...,
    user_preferences={
        "agent_preferences": {
            "trusted_agent_1": 0.95,    # Strong preference
            "trusted_agent_2": 0.85,    # Moderate preference
        },
        "budget": 10.0,
        "time_sensitivity": "fast",
    },
)
```

## Monitoring & Debugging

### View Orchestration Summary

```python
summary = event_logger.get_summary()
print(f"Events logged: {summary['events_count']}")
print(f"Agents executed: {summary['agents_executed']}")
print(f"Current stage: {summary['current_stage']}")
print(f"Total cost: ${summary['total_cost']}")
print(f"Elapsed: {summary['elapsed_ms']}ms")
```

### Find Bottlenecks

```python
for agent_id in trace.agent_execution_order:
    # Get ExecutionTrace for this agent
    agent_trace_id = trace.agent_execution_traces[agent_id]
    # Fetch from database and analyze
```

### Analyze Routing Decisions

```python
rejected = [d for d in trace.routing_decisions if d.decision == "REJECTED"]
print(f"Rejected {len(rejected)} agents:")
for d in rejected:
    print(f"  {d.agent_id}: {d.reason.value}")
    print(f"    Score: {d.score}")
```

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_routing_selection():
    policy = RuleBasedRoutingPolicy()
    
    # Test analysis
    analysis = await policy.analyze_query("Find papers on ML", context)
    assert "search" in analysis["required_capabilities"]
    
    # Test ranking
    ranked = await policy.rank_agents(query, agents, analysis, context)
    assert len(ranked) == len(agents)
    assert ranked[0][1] >= ranked[1][1]  # Descending by score
    
    # Test selection
    selected, decisions = await policy.select_agents(ranked, context, 100)
    assert len(selected) > 0
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_orchestration():
    orchestrator = DynamicOrchestrator(
        routing_policy=RuleBasedRoutingPolicy(),
        max_retries=2,
    )
    
    trace = await orchestrator.execute(
        conversation_id=uuid4(),
        initial_message=test_message,
        agents=[agent1, agent2],
    )
    
    assert trace.status == "completed"
    assert len(trace.events) > 0
    assert len(trace.agent_execution_order) > 0
```

## Performance Considerations

| Aspect | Optimization |
|--------|--------------|
| Query Analysis | Cache common patterns |
| Agent Ranking | Parallelize scoring |
| Agent Execution | Execute in parallel if no deps |
| Event Logging | Batch event writes |
| Result Aggregation | Stream results if possible |

## Future Enhancements

1. **Parallel Execution**: Run independent agents simultaneously
2. **Hierarchical Agents**: Agents can delegate to sub-agents
3. **ML-Based Routing**: Learn routing patterns from execution data
4. **Dynamic Ordering**: Optimize agent order based on dependencies
5. **Caching**: Cache query analysis and agent rankings
6. **Fallback Chains**: Specify fallback agents per capability
7. **Cost Prediction**: Learn cost patterns per agent
8. **Human-in-the-Loop**: Approve routing decisions before execution

---

## See Also

- [ARCHITECTURE.md](../../ARCHITECTURE.md) - System-wide design
- [DESIGN_DECISIONS.md](../../DESIGN_DECISIONS.md) - Why we made key choices
- [examples.py](./examples.py) - Runnable examples
