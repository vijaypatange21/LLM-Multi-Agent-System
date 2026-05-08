"""
Evaluation framework schemas.

WHY: Production systems must measure quality. Evaluations provide:
- Automated quality gates (prevent low-quality outputs)
- Performance tracking over time (agent improvement validation)
- Failure analysis (which agents/patterns fail most often?)
- Comparison data (agent A vs. agent B)
- Tuning feedback (does changing this parameter help?)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EvalMetricType(str, Enum):
    """Standard evaluation metric categories."""
    ACCURACY = "accuracy"              # Did the agent get the right answer?
    RELEVANCE = "relevance"            # Is the output relevant to the query?
    COMPLETENESS = "completeness"      # Did it cover all requirements?
    LATENCY = "latency"                # Was it fast enough?
    COST = "cost"                      # Did it stay within budget?
    SAFETY = "safety"                  # Did it violate constraints?
    COHERENCE = "coherence"            # Is the reasoning logical?
    CUSTOM = "custom"                  # Custom metric (evaluator-defined)


class EvalMetric(BaseModel):
    """
    Single evaluation metric/dimension.
    
    WHY: Complex tasks require multi-dimensional evaluation. A single score
    isn't enough. By tracking multiple metrics, we can:
    - Identify trade-offs (faster but less accurate?)
    - Correlate metrics with user satisfaction
    - Detect regression on specific dimensions
    """
    
    name: str = Field(description="Metric identifier (e.g., 'answer_correctness')")
    metric_type: EvalMetricType = Field(description="Category of this metric")
    description: str = Field(description="What this metric measures and why it matters")
    
    # Score
    score: float = Field(description="Metric value (0-100 or domain-specific)")
    score_range_min: float = Field(default=0.0, description="Minimum possible score")
    score_range_max: float = Field(default=100.0, description="Maximum possible score")
    
    # Thresholds for pass/fail
    pass_threshold: Optional[float] = Field(
        default=None,
        description="Score must be >= this to pass. None = no hard threshold."
    )
    
    # Details
    evidence: Optional[str] = Field(
        default=None,
        description="Why did we assign this score? (e.g., 'Output contains hallucinations')"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "name": "answer_correctness",
                    "metric_type": "accuracy",
                    "description": "Percentage of questions answered correctly",
                    "score": 85.0,
                    "score_range_min": 0.0,
                    "score_range_max": 100.0,
                    "pass_threshold": 80.0,
                    "evidence": "Got 17/20 questions right. Missed edge cases."
                }
            ]
        }


class EvalResult(BaseModel):
    """
    Complete evaluation of an agent's execution.
    
    WHY: Evaluations are how we ensure quality and track improvement. They:
    - Gate deployments (only promote agents that meet thresholds)
    - Track performance over time (agent learning)
    - Compare variants (A/B testing)
    - Feed into monitoring (alert on quality drops)
    
    Design considerations:
    - execution_trace_id: Links evaluation to what was executed. Enables
      correlation analysis (e.g., "traces with latency > Xms score lower").
    - metrics: Multiple dimensions capture trade-offs and nuances.
    - overall_pass: Boolean gate for automated decision-making (deploy or not?)
    - evaluator_id: Who/what evaluated? (automated script, human, ML model?)
      Enables cross-validator agreement scoring.
    - comparison_baseline: Scores compared to what? (previous version? competitor?)
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique evaluation ID")
    execution_trace_id: UUID = Field(
        description="The ExecutionTrace being evaluated"
    )
    conversation_id: UUID = Field(description="Which conversation this eval belongs to")
    
    # Evaluator
    evaluator_id: str = Field(
        description="Who/what did the evaluation (e.g., 'judge_model_v1', 'human_reviewer_bob')"
    )
    evaluator_version: Optional[str] = Field(
        default=None,
        description="Evaluator version for reproducibility"
    )
    
    # Metrics
    metrics: List[EvalMetric] = Field(
        default_factory=list,
        description="All measured dimensions"
    )
    
    # Overall result
    overall_pass: bool = Field(
        description="Did the execution meet all requirements? (deployment gate)"
    )
    overall_score: Optional[float] = Field(
        default=None,
        description="Single aggregate score if applicable (e.g., average across metrics)"
    )
    
    # Diagnostics
    feedback: Optional[str] = Field(
        default=None,
        description="Detailed evaluator feedback for debugging/improvement"
    )
    
    # Timing
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Baseline comparison
    comparison_baseline: Optional[Dict[str, Any]] = Field(
        default=None,
        description={
            "description": "Comparison data (e.g., previous version scores)",
            "example": {
                "baseline_type": "previous_agent_version",
                "baseline_version": "v0.9.0",
                "previous_overall_score": 72.0,
                "delta": 10.0
            }
        }
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "execution_trace_id": "550e8400-e29b-41d4-a716-446655440001",
                    "conversation_id": "550e8400-e29b-41d4-a716-446655440002",
                    "evaluator_id": "judge_model_v1",
                    "evaluator_version": "v1.2.3",
                    "metrics": [
                        {
                            "name": "answer_correctness",
                            "metric_type": "accuracy",
                            "description": "Answer matches ground truth",
                            "score": 95.0,
                            "score_range_min": 0.0,
                            "score_range_max": 100.0,
                            "pass_threshold": 80.0,
                            "evidence": "Correct"
                        }
                    ],
                    "overall_pass": True,
                    "overall_score": 95.0,
                    "feedback": "Excellent reasoning and comprehensive answer.",
                    "evaluated_at": "2026-05-09T10:00:10Z",
                    "comparison_baseline": {
                        "baseline_type": "previous_agent_version",
                        "baseline_version": "v0.9.0",
                        "previous_overall_score": 82.0,
                        "delta": 13.0
                    }
                }
            ]
        }
