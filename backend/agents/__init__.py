"""
Agent implementations module.

Architecture Overview:
This module contains concrete implementations of BaseAgent. Agents are the
"thinking" components of the system. They:
- Receive messages and context
- Reason about the problem
- Make decisions (including tool calls)
- Return execution traces

Implemented Agents:
1. ✅ DecompositionAgent: Breaks complex queries into subtasks
   - Parses queries into typed tasks
   - Generates dependency DAG
   - Detects ambiguities and missing info
   - Produces structured task graphs
   - Confidence scoring

Planned Agents:
2. LLMAgent: Uses an LLM (GPT-4, Claude, etc.) as the reasoning engine.
   - Reads context and message
   - Constructs a prompt
   - Calls the LLM
   - Parses LLM output for tool calls
   - Returns execution trace

3. HierarchicalAgent: Delegates to sub-agents
   - Breaks down complex tasks
   - Delegates to specialist agents
   - Aggregates results
   - Reports back to parent

4. ReasoningAgent: Multi-step reasoning with explicit planning
   - Thinks through steps before acting
   - Produces interpretable traces
   - Can be traced/debugged

5. RoutingAgent: Dispatches to other agents based on message type
   - Content-based routing
   - Maintains agent registry
   - Transparent passthrough for debugging

Extension points:
- Custom reasoning strategies (chain-of-thought, tree-of-thought, etc.)
- Different LLM backends (OpenAI, Anthropic, local models, etc.)
- Agent-specific tool filtering
- Custom message interpretation
"""

from .decomposition_agent import DecompositionAgent
from .schemas import (
    AmbiguityIndicator,
    AmbiguityType,
    DecompositionResult,
    Task,
    TaskDependency,
    TaskGraph,
    TaskStatus,
    TaskType,
)

__all__ = [
    # Agents
    "DecompositionAgent",
    # Schemas - Task types and status
    "Task",
    "TaskType",
    "TaskStatus",
    "TaskDependency",
    # Schemas - Task Graph
    "TaskGraph",
    # Schemas - Decomposition
    "AmbiguityType",
    "AmbiguityIndicator",
    "DecompositionResult",
]
