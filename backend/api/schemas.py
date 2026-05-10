"""
Schemas for production API endpoints.

Defines request/response models with validation.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class ErrorResponse(BaseModel):
    """Consistent error response schema."""
    
    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Machine-readable error code")
    trace_id: Optional[UUID] = Field(None, description="Correlation trace ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional error details")


class QueryRequest(BaseModel):
    """Request to submit a query for multi-agent processing."""
    
    query: str = Field(..., min_length=1, max_length=10000, description="User query")
    conversation_id: Optional[UUID] = Field(None, description="Link to existing conversation")
    budget_tokens: int = Field(default=10000, ge=100, le=1000000, description="Token budget")
    timeout_seconds: int = Field(default=60, ge=5, le=600, description="Execution timeout")
    
    @validator('query')
    def query_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
        return v


class QueryResponse(BaseModel):
    """Response to query submission."""
    
    trace_id: UUID = Field(..., description="Unique execution trace ID")
    conversation_id: UUID = Field(..., description="Conversation ID")
    status: str = Field(default="started", description="Initial status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = Field(default="Query submitted for processing")


class TraceMetadata(BaseModel):
    """Metadata about an execution trace."""
    
    step_count: int
    total_duration_ms: float
    status: str
    agent_id: str
    error_message: Optional[str] = None


class ExecutionTraceResponse(BaseModel):
    """Response for execution trace retrieval."""
    
    trace_id: UUID = Field(..., description="Unique trace ID")
    conversation_id: UUID = Field(..., description="Conversation ID")
    metadata: TraceMetadata = Field(..., description="Trace metadata")
    steps_summary: List[Dict[str, Any]] = Field(default_factory=list, description="Summary of steps")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="Latency, cost, etc.")
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class EvaluationMetrics(BaseModel):
    """Evaluation metrics."""
    
    correctness: float = Field(..., ge=0, le=1)
    citation_accuracy: float = Field(..., ge=0, le=1)
    contradiction_resolution: float = Field(..., ge=0, le=1)
    tool_efficiency: float = Field(..., ge=0, le=1)
    context_compliance: float = Field(..., ge=0, le=1)
    critique_agreement: float = Field(..., ge=0, le=1)
    overall_score: Optional[float] = Field(None, ge=0, le=1)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Compute overall_score as average if not provided
        if self.overall_score is None:
            scores = [
                self.correctness,
                self.citation_accuracy,
                self.contradiction_resolution,
                self.tool_efficiency,
                self.context_compliance,
                self.critique_agreement,
            ]
            self.overall_score = sum(scores) / len(scores)


class EvaluationCase(BaseModel):
    """Single evaluation case result."""
    
    case_id: str
    category: str  # baseline, ambiguous, adversarial
    score: EvaluationMetrics
    duration_ms: float


class EvalSummaryResponse(BaseModel):
    """Response for latest evaluation summary."""
    
    eval_run_id: UUID = Field(..., description="Evaluation run ID")
    timestamp: datetime = Field(..., description="When evaluation was run")
    total_cases: int = Field(..., ge=0)
    baseline_cases: int = Field(default=0, ge=0)
    ambiguous_cases: int = Field(default=0, ge=0)
    adversarial_cases: int = Field(default=0, ge=0)
    
    average_metrics: EvaluationMetrics
    
    slowest_cases: List[EvaluationCase] = Field(default_factory=list)
    lowest_scoring_cases: List[EvaluationCase] = Field(default_factory=list)
    
    duration_ms: float = Field(..., description="Total evaluation duration")
    recommendations: List[str] = Field(default_factory=list, description="Improvement suggestions")


class ApprovalDecision(str, Enum):
    """Approval decision."""
    APPROVE = "approve"
    REJECT = "reject"


class PromptApprovalRequest(BaseModel):
    """Request to approve or reject a prompt rewrite."""
    
    decision: ApprovalDecision = Field(..., description="Approve or reject")
    notes: str = Field(default="", max_length=5000, description="Optional review notes")
    approved_by: str = Field(..., description="Email or username of approver")
    
    @validator('approved_by')
    def approver_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Approver must not be empty")
        return v


class PromptApprovalResponse(BaseModel):
    """Response to prompt approval."""
    
    diff_id: UUID = Field(..., description="Prompt diff ID")
    decision: ApprovalDecision
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)
    next_step: str = Field(..., description="What happens next (e.g., 'awaiting_application')")


class TargetedReEvalRequest(BaseModel):
    """Request for targeted re-evaluation of specific prompts."""
    
    prompt_version_ids: List[str] = Field(..., min_items=1, max_items=5, description="Prompt versions to re-eval")
    test_categories: List[str] = Field(
        default=["baseline", "ambiguous", "adversarial"],
        description="Test case categories to run"
    )
    focus_cases: Optional[List[str]] = Field(None, description="Specific case IDs to re-evaluate")
    timeout_seconds: int = Field(default=300, ge=30, le=1800)
    
    @validator('prompt_version_ids')
    def versions_not_empty(cls, v):
        if not v or all(not vid.strip() for vid in v):
            raise ValueError("Must specify at least one prompt version")
        return v


class ReEvalCase(BaseModel):
    """Single case in targeted re-evaluation."""
    
    case_id: str
    old_score: Optional[float] = None
    new_score: float
    improved: bool
    delta: float = Field(..., description="Score delta (new - old)")


class TargetedReEvalResponse(BaseModel):
    """Response for targeted re-evaluation."""
    
    eval_id: UUID = Field(..., description="Evaluation job ID")
    status: str = Field(default="started", description="Job status")
    prompt_versions_tested: int
    total_cases: int
    
    results: List[ReEvalCase] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict, description="Overall summary")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    estimated_completion_seconds: int = Field(default=60)


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(default="healthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(default="1.0.0")
    components: Dict[str, str] = Field(default_factory=dict, description="Status of each component")
