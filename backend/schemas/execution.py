"""
ExecutionTrace and ExecutionStep schemas.

WHY: Execution traces capture the complete "thinking process" of an agent
or multi-agent workflow. They're essential for:
- Debugging: What did the agent do? Why did it fail?
- Observability: Which execution paths are slowest/most expensive?
- Reproducibility: Can we replay an execution?
- Learning: Post-hoc analysis for agent improvement
- Compliance: Audit trail of decisions and their rationales
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionStepType(str, Enum):
    """Categorizes what happened in an execution step."""
    PLANNING = "planning"              # Agent decides on a strategy
    REASONING = "reasoning"            # Agent thinks through a problem
    TOOL_CALL = "tool_call"            # Agent invokes a tool
    TOOL_RESULT = "tool_result"        # Tool returns a result
    ERROR_HANDLING = "error_handling"  # Agent handles an exception
    CONTEXT_UPDATE = "context_update"  # Shared context was modified
    DECISION = "decision"              # Agent makes a key decision


class ExecutionStep(BaseModel):
    """
    Atomic unit of execution within an agent's reasoning process.
    
    WHY: Execution steps provide granular visibility into agent behavior.
    Each step documents:
    - What happened (the action)
    - Why it happened (reasoning/decision)
    - Context at that moment (state)
    - Outcome (success/failure)
    
    This enables efficient debugging: instead of reading logs, operators
    can replay the execution step-by-step.
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique step ID")
    execution_trace_id: UUID = Field(default_factory=lambda: UUID(int=0), description="Parent execution trace")
    
    # Step classification
    step_type: ExecutionStepType = Field(description="What type of action occurred")
    step_number: int = Field(default=1, description="Order within the trace (1-indexed)")
    
    # What happened
    description: str = Field(default="", description="Human-readable summary of this step")
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input to this step (e.g., agent state, tool arguments)"
    )
    output_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Output from this step (e.g., agent decision, tool result)"
    )
    
    # Why it happened (reasoning)
    reasoning: Optional[str] = Field(
        default=None,
        description="Agent's explanation of why it took this action (if available)"
    )
    
    # Status
    status: str = Field(default="completed", description="success, failed, pending, etc.")
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if status = 'failed'"
    )
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float = Field(default=0.0, description="Execution time for this step")
    
    # Cost tracking
    cost_incurred: Optional[float] = Field(
        default=None,
        description="Cost for this step (tool invocation, API call, etc.)"
    )


class ExecutionTrace(BaseModel):
    """
    Complete record of an agent's execution or multi-agent workflow.
    
    WHY: Execution traces are the "source of truth" for what happened during
    a conversation. They enable:
    - Post-hoc debugging
    - Performance analysis (which steps are slow?)
    - Cost accounting (which agents/tools are expensive?)
    - Compliance audits
    - Replay/simulation for testing
    - ML training data (learn from agent behavior)
    
    Design considerations:
    - conversation_id: Links trace to a specific conversation.
    - parent_trace_id: Enables hierarchical traces (e.g., one agent delegates
      to another). Supports tree-structured workflows.
    - agent_id: Which agent (or orchestrator) performed this trace.
    - steps: Complete ordered list of actions. Immutable once execution completes.
    - final_output: What the agent/workflow decided/produced.
    - outcome: Did the overall execution succeed?
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique trace ID")
    conversation_id: UUID = Field(description="Which conversation this trace belongs to")
    
    # Hierarchy (for delegated/hierarchical workflows)
    parent_trace_id: Optional[UUID] = Field(
        default=None,
        description="Parent trace if this is a sub-workflow (e.g., delegated task)"
    )
    
    # Who executed
    agent_id: str = Field(description="Agent that produced this trace")
    agent_version: Optional[str] = Field(
        default=None,
        description="Agent version for reproducibility"
    )
    
    # Execution steps
    steps: List[ExecutionStep] = Field(
        default_factory=list,
        description="Ordered list of all actions taken during execution"
    )
    
    # Outcome
    status: str = Field(
        default="completed",
        description="completed, in_progress, failed, timeout, etc."
    )
    final_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Agent's final decision/output"
    )
    
    # Diagnostics
    error_message: Optional[str] = Field(
        default=None,
        description="If status != completed, why?"
    )
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    total_duration_ms: float = Field(description="Total wall-clock time")
    
    # Resource accounting
    total_cost: float = Field(default=0.0, description="Sum of all step costs")
    tokens_used: Optional[Dict[str, int]] = Field(
        default=None,
        description="LLM token usage: prompt_tokens, completion_tokens, etc."
    )
    
    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context: model params, sampling strategy, etc."
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
                    "parent_trace_id": None,
                    "agent_id": "search_agent",
                    "agent_version": "v1.0.0",
                    "steps": [],
                    "status": "completed",
                    "final_output": {"results": []},
                    "error_message": None,
                    "started_at": "2026-05-09T10:00:00Z",
                    "completed_at": "2026-05-09T10:00:05Z",
                    "total_duration_ms": 5000,
                    "total_cost": 0.1,
                    "tokens_used": {"prompt": 150, "completion": 200}
                }
            ]
        }
