"""
Tool-related schemas: ToolDefinition, ToolCall, ToolResult.

WHY: Tools are how agents interact with external systems and perform actions.
Strong typing ensures proper invocation, reduces errors, and enables:
- Tool registry discovery
- Request validation
- Response type checking
- Usage tracking and monitoring
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ToolType(str, Enum):
    """Tool categories for runtime dispatch and capability discovery."""
    SEARCH = "search"           # External data retrieval
    COMPUTE = "compute"         # Heavy computation
    DATABASE = "database"       # Data persistence
    EXTERNAL_API = "external_api"  # Third-party services
    CODE_EXECUTION = "code_execution"  # Interpreter/REPL
    SYSTEM_ACTION = "system_action"    # Infrastructure changes


class ToolDefinition(BaseModel):
    """
    Static tool schema and metadata.
    
    WHY: Tool definitions act as an "API contract". Agents download these
    at runtime to understand what tools are available, their signatures,
    and constraints. This enables:
    - Dynamic tool discovery (agents don't need hard-coded tool lists)
    - Automatic validation of tool calls
    - Rate limiting and cost tracking per tool
    - Capability-based access control
    
    Design considerations:
    - Tool definitions are versioned separately from agents. A new agent
      version doesn't force all tools to be redeployed.
    - required_permissions: Some tools need explicit authorization. Stored
      in context constraints for audit purposes.
    """
    
    id: str = Field(description="Unique tool identifier (e.g., 'web_search_v1')")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="What this tool does and when to use it")
    version: str = Field(default="1.0.0", description="Semantic version for compatibility")
    
    # Tool classification
    tool_type: ToolType = Field(description="Category for routing and discovery")
    
    # Input contract
    input_schema: Dict[str, Any] = Field(
        description="JSON schema for tool arguments. Enables strict validation."
    )
    
    # Output contract
    output_schema: Dict[str, Any] = Field(
        description="JSON schema for tool results. Ensures predictable return values."
    )
    
    # Operational constraints
    timeout_seconds: int = Field(default=30, description="Max execution time")
    fallback_tool_ids: List[str] = Field(
        default_factory=list,
        description="Ordered fallback tools to try if the primary tool fails",
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="Permissions needed to invoke (e.g., ['write_database', 'external_api'])"
    )
    
    # Cost and limits
    cost_per_call: float = Field(
        default=0.0,
        description="Monetary cost if applicable (for budget enforcement)"
    )
    rate_limit_per_hour: Optional[int] = Field(
        default=None,
        description="Max invocations per hour. None = unlimited."
    )
    
    # Availability and rollout
    is_deprecated: bool = Field(
        default=False,
        description="If true, agents should use newer versions"
    )
    available_regions: List[str] = Field(
        default_factory=list,
        description="Geographic availability constraints"
    )


class ToolCall(BaseModel):
    """
    Agent's invocation of a tool.
    
    WHY: ToolCall represents the agent's *decision* to invoke a tool. The system
    validates this decision (does it match input_schema? are permissions granted?)
    before execution. This enables:
    - Dry-run validation
    - Early error detection
    - Tool invocation logging for audit trails
    - Cost estimation before execution
    
    Design considerations:
    - tool_id: References the tool definition. Enables version lookup.
    - arguments: Arbitrary tool-specific parameters. Must conform to input_schema
      or validation fails.
    - execution_trace_id: Connects the tool call to the broader execution trace
      for debugging/observability.
    """
    
    id: UUID = Field(default_factory=uuid4, description="Unique call ID")
    tool_id: str = Field(description="Identifier of the tool being invoked")
    tool_version: str = Field(
        default="1.0.0",
        description="Tool version. Used for reproducibility if tool changes."
    )
    
    # Invocation details
    arguments: Dict[str, Any] = Field(
        description="Tool arguments. Must conform to tool's input_schema."
    )
    
    # Tracing
    execution_trace_id: UUID = Field(
        description="Links this tool call to the parent execution trace"
    )
    agent_id: str = Field(description="Which agent made this call")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional cost tracking (populated after validation)
    estimated_cost: Optional[float] = Field(
        default=None,
        description="Estimated cost if applicable. Used for budget enforcement."
    )


class ToolResultStatus(str, Enum):
    """Tool execution outcome."""
    SUCCESS = "success"
    PARTIAL = "partial"  # Got results but with warnings
    FAILED = "failed"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"


class ToolCallDecision(str, Enum):
    """Acceptance state for a tool call before execution."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ToolRetryOutcome(str, Enum):
    """Outcome of a single retry attempt."""
    RETRIED = "retried"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class ToolExecutionAttempt(BaseModel):
    """One independently logged attempt to execute a tool call."""

    id: UUID = Field(default_factory=uuid4, description="Unique attempt ID")
    tool_call_id: UUID = Field(description="Parent tool call")
    attempt_number: int = Field(ge=1, description="1-indexed attempt number")
    decision: ToolCallDecision = Field(description="Whether the attempt was accepted for execution")
    outcome: ToolRetryOutcome = Field(description="Outcome of the attempt")
    status: ToolResultStatus = Field(description="Tool result status for this attempt")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = Field(default=0.0, description="Observed latency for the attempt")
    error_message: Optional[str] = Field(default=None, description="Why the attempt failed, if applicable")
    structured_log: Dict[str, Any] = Field(default_factory=dict, description="Structured log payload for the attempt")
    input_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Validated input arguments for the attempt")
    output_snapshot: Optional[Dict[str, Any]] = Field(default=None, description="Output captured for the attempt")


class ToolExecutionTrace(BaseModel):
    """Full execution record for a tool call, including all retry attempts."""

    id: UUID = Field(default_factory=uuid4, description="Unique trace ID")
    tool_call_id: UUID = Field(description="Tool call being executed")
    tool_id: str = Field(description="Tool identifier")
    agent_id: str = Field(description="Agent requesting the tool")
    accepted: bool = Field(default=True, description="Whether the tool call was accepted")
    rejected_reason: Optional[str] = Field(default=None, description="Reason for rejection if not accepted")
    attempts: List[ToolExecutionAttempt] = Field(default_factory=list, description="All logged attempts")
    final_result_status: ToolResultStatus = Field(description="Final execution status")
    total_latency_ms: float = Field(default=0.0, description="Total latency across attempts")
    total_attempts: int = Field(default=0, description="Number of attempts performed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata")


class ToolResult(BaseModel):
    """
    Outcome of a tool invocation.
    
    WHY: Tool results carry both the output data and execution metadata.
    This enables:
    - Error diagnostics (why did it fail?)
    - Cost tracking (what did it cost?)
    - Debugging (how long did it take?)
    - Monitoring (which tools fail most often?)
    
    Design considerations:
    - status: Distinguishes between "got a result" vs. "call failed". Agents
      handle these differently (exception handling, retry logic, etc.).
    - output: The actual tool result. Can be None if it failed.
    - error_message: If status != SUCCESS, explains why (for agent debugging).
    - execution_metadata: Hidden operational details (latency, retries, etc.)
      that agents don't need but operators do.
    """
    
    id: UUID = Field(default_factory=uuid4, description="Unique result ID")
    tool_call_id: UUID = Field(description="References the ToolCall that produced this")
    
    # Execution outcome
    status: ToolResultStatus = Field(description="Did the tool succeed?")
    output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Tool output. Conforms to tool's output_schema if status=SUCCESS."
    )
    
    # Diagnostics
    error_message: Optional[str] = Field(
        default=None,
        description="Why did it fail (if status != SUCCESS)"
    )
    
    # Execution details
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    execution_time_ms: float = Field(
        description="Wall-clock time tool took to execute"
    )
    
    # Cost tracking
    actual_cost: Optional[float] = Field(
        default=None,
        description="Actual cost incurred (may differ from estimate)"
    )
    
    # Operational metadata
    execution_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Latency, retries, caching info, etc. (internal use)"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440002",
                    "tool_call_id": "550e8400-e29b-41d4-a716-446655440003",
                    "status": "success",
                    "output": {
                        "search_results": [
                            {"title": "...", "url": "...", "snippet": "..."}
                        ]
                    },
                    "error_message": None,
                    "started_at": "2026-05-09T10:00:01Z",
                    "completed_at": "2026-05-09T10:00:03Z",
                    "execution_time_ms": 2000,
                    "actual_cost": 0.05,
                    "execution_metadata": {"retries": 0, "cached": False}
                }
            ]
        }


class ToolValidationIssue(BaseModel):
    """Structured validation issue returned by the tool validator."""

    field: str = Field(description="Field or path that failed validation")
    issue: str = Field(description="Human-readable issue")
    expected: Optional[str] = Field(default=None, description="Expected format or type")
    actual: Optional[str] = Field(default=None, description="Actual value or type")


class ToolValidationResult(BaseModel):
    """Detailed output from validating a tool call."""

    is_valid: bool = Field(description="Whether the call is valid")
    issues: List[ToolValidationIssue] = Field(default_factory=list, description="Validation issues")
    normalized_arguments: Dict[str, Any] = Field(default_factory=dict, description="Normalized arguments")
    rejected_reason: Optional[str] = Field(default=None, description="Summary reason for rejection")
