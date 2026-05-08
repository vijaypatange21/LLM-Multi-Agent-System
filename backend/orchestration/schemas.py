"""
Orchestration trace and execution planning schemas.

These schemas extend the core ExecutionTrace to add orchestration-specific
tracking: routing decisions, execution plans, and why decisions were made.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RoutingDecisionReason(str, Enum):
    """Why was an agent selected or skipped?"""
    CAPABILITY_MATCH = "capability_match"          # Agent has required capability
    REQUIRED_BY_CONTEXT = "required_by_context"    # Context constraints require this agent
    DEPENDENCY = "dependency"                      # Required by another agent
    FALLBACK = "fallback"                          # Primary agent unavailable
    OPTIMIZATION = "optimization"                  # Selected for efficiency
    USER_PREFERENCE = "user_preference"            # User requested this agent
    CAPABILITY_PRIORITY = "capability_priority"    # Higher priority for capability
    COST_EFFICIENT = "cost_efficient"              # Lower cost option
    UNKNOWN = "unknown"                            # No reason available


class RoutingDecision(BaseModel):
    """
    Record of a routing decision: which agent was selected and why.
    
    WHY: Transparent routing enables debugging ("why wasn't agent X used?").
    Enables learning (correlate decisions with outcomes).
    """
    
    agent_id: str = Field(description="Agent selected or rejected")
    decision: str = Field(description="SELECTED or REJECTED")
    reason: RoutingDecisionReason = Field(description="Why this decision")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1)"
    )
    explanation: str = Field(
        description="Human-readable explanation of routing decision"
    )
    
    # Scoring details
    score: float = Field(description="Routing score for this agent")
    capability_match: Optional[float] = Field(
        default=None,
        description="How well does agent match query (0-1)"
    )
    budget_available: bool = Field(
        default=True,
        description="Is there sufficient budget for this agent?"
    )
    estimated_cost: Optional[float] = Field(
        default=None,
        description="Estimated cost if selected"
    )
    
    # Alternatives
    alternative_agents: List[str] = Field(
        default_factory=list,
        description="Other agents that could have been selected"
    )


class ExecutionStep(str, Enum):
    """Stages in orchestration execution."""
    PLANNING = "planning"                  # Decide which agents needed
    VALIDATION = "validation"              # Check constraints
    SCHEDULING = "scheduling"              # Determine execution order
    EXECUTING = "executing"                # Running agents
    COLLECTING_RESULTS = "collecting_results"  # Gathering outputs
    AGGREGATING = "aggregating"            # Combining results
    COMPLETED = "completed"                # Finished


class ExecutionPlan(BaseModel):
    """
    Dynamic execution plan for orchestration.
    
    WHY: Explicit plan enables:
    - Transparency: users see what will happen
    - Prediction: can estimate time/cost
    - Debugging: know what went wrong
    - Reproducibility: same plan = same flow
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Plan ID")
    conversation_id: UUID = Field(description="Which conversation")
    
    # Plan structure
    execution_stage: ExecutionStep = Field(description="Current stage")
    planned_agents: List[str] = Field(
        description="Agents that will/did execute, in order"
    )
    planned_order: List[int] = Field(
        description="Execution order (indices into planned_agents)"
    )
    
    # Constraints and budget
    total_budget: float = Field(description="Total token/cost budget")
    budget_allocated: Dict[str, float] = Field(
        default_factory=dict,
        description="Budget per agent (agent_id -> budget)"
    )
    
    # Execution status
    completed_agents: List[str] = Field(
        default_factory=list,
        description="Agents that have completed"
    )
    failed_agents: List[str] = Field(
        default_factory=list,
        description="Agents that failed"
    )
    
    # Plan metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    estimated_total_cost: float = Field(description="Total estimated cost")
    estimated_total_time_ms: float = Field(description="Total estimated time")


class OrchestrationEventType(str, Enum):
    """Types of orchestration events for logging."""
    QUERY_RECEIVED = "query_received"
    ANALYSIS_STARTED = "analysis_started"
    ROUTING_DECISION = "routing_decision"
    PLAN_CREATED = "plan_created"
    AGENT_SELECTED = "agent_selected"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    BUDGET_CONSTRAINT = "budget_constraint"
    RETRY_ATTEMPT = "retry_attempt"
    RESULT_AGGREGATED = "result_aggregated"
    ORCHESTRATION_COMPLETED = "orchestration_completed"
    ORCHESTRATION_FAILED = "orchestration_failed"
    CONTEXT_UPDATED = "context_updated"


class OrchestrationEvent(BaseModel):
    """
    Atomic orchestration event for structured logging.
    
    WHY: Structured events enable:
    - Analytics: query patterns, routing patterns
    - Debugging: step-by-step trace of decisions
    - Monitoring: track orchestration performance
    - Compliance: audit trail of decisions
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0))
    orchestration_trace_id: UUID = Field(description="Parent trace")
    conversation_id: UUID = Field(description="Which conversation")
    
    # Event classification
    event_type: OrchestrationEventType = Field(description="What happened")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Event details
    message: str = Field(description="Human-readable event description")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific details"
    )
    
    # Context
    current_stage: ExecutionStep = Field(description="Orchestration stage")
    elapsed_time_ms: float = Field(description="Time since orchestration started")
    
    # Cost tracking
    cost_incurred_this_event: float = Field(
        default=0.0,
        description="Cost for this event"
    )
    cumulative_cost: float = Field(
        default=0.0,
        description="Total cost so far"
    )
    
    # For decision events
    decision_explanation: Optional[str] = Field(
        default=None,
        description="Why was this decision made?"
    )


class OrchestrationTrace(BaseModel):
    """
    Complete orchestration execution record.
    
    WHY: High-level view of orchestration decisions and flow.
    Distinct from ExecutionTrace (which records agent reasoning).
    This records: what agents ran, in what order, why, and outcomes.
    
    Design:
    - Tracks routing decisions per query
    - Records execution plan
    - Captures all events
    - Links to individual ExecutionTraces
    - Enables orchestration analytics
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique trace ID")
    conversation_id: UUID = Field(description="Which conversation")
    
    # High-level execution
    status: str = Field(
        default="in_progress",
        description="in_progress, completed, failed, timeout"
    )
    
    # Planning
    initial_query: str = Field(description="User's original query")
    execution_plan: ExecutionPlan = Field(description="Dynamic execution plan")
    
    # Routing decisions
    routing_decisions: List[RoutingDecision] = Field(
        default_factory=list,
        description="All routing decisions made"
    )
    
    # Execution
    events: List[OrchestrationEvent] = Field(
        default_factory=list,
        description="All events in order"
    )
    
    # Agent execution tracking
    agent_execution_order: List[str] = Field(
        default_factory=list,
        description="Order agents actually executed"
    )
    agent_results: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Results from each agent (agent_id -> output)"
    )
    agent_execution_traces: Dict[str, UUID] = Field(
        default_factory=dict,
        description="Links to ExecutionTrace for each agent (agent_id -> trace_id)"
    )
    
    # Failure handling
    failed_attempts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Record of failed agent attempts (for retry analysis)"
    )
    
    # Final outcome
    final_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Aggregated/final result"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="If failed, what went wrong"
    )
    
    # Timing and cost
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    total_duration_ms: float = Field(default=0.0)
    total_cost: float = Field(default=0.0)
    total_tokens_used: Dict[str, int] = Field(
        default_factory=dict,
        description="prompt_tokens, completion_tokens, etc."
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
                    "status": "completed",
                    "initial_query": "Find flights and hotels for my trip",
                    "execution_plan": {},
                    "routing_decisions": [],
                    "events": [],
                    "agent_execution_order": ["search_agent", "booking_agent"],
                    "agent_results": {
                        "search_agent": {"flights": [], "hotels": []},
                        "booking_agent": {"booking_confirmation": "..."}
                    },
                    "final_output": {"trip_plan": "..."},
                    "total_duration_ms": 5000,
                    "total_cost": 0.15
                }
            ]
        }
