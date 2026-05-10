"""
Self-improving prompt optimization loop with mandatory human approval.

Architecture:
- MetaAgent analyzes failed evaluations
- Identifies weakest performing prompts
- Generates improved prompt recommendations
- Creates structured diffs for review
- Approval/rejection workflow (human mandatory)
- Prompt versioning with performance tracking
- Performance delta computation

Key principle: NO AUTO-APPLY. All prompt changes require explicit human approval.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
import json
from collections import defaultdict

from backend.evaluation import (
    CaseCategory,
    DimensionScore,
    EvaluationResult,
    ScoringDimension,
)


class ApprovalStatus(str, Enum):
    """Status of prompt approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # Newer version approved


class PromptOrigin(str, Enum):
    """Origin/source of a prompt."""
    ORIGINAL = "original"
    GENERATED = "generated"
    APPROVED = "approved"  # Was approved in a previous iteration


@dataclass
class FailedEval:
    """Single failed evaluation for analysis."""
    
    result_id: str
    case_id: str
    case_category: CaseCategory
    prompt: str
    expected: str
    actual: str
    dimension_scores: Dict[str, float]  # dimension_name -> score
    overall_score: float
    weakest_dimensions: List[str]  # Ordered by weakness


@dataclass
class PromptWeakness:
    """Identified weakness in a prompt."""
    
    prompt_id: str
    weakness_type: str  # "low_correctness", "citations_missing", "tool_inefficiency", etc.
    affected_cases: List[str]  # Case IDs affected
    avg_impact: float  # Average score impact
    evidence: Dict[str, Any]  # Specific examples


@dataclass
class PromptRecommendation:
    """Recommendation for prompt improvement."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    original_prompt_id: str = ""
    weakness_addressed: str = ""  # Which weakness this targets
    
    original_text: str = ""
    recommended_text: str = ""
    
    reasoning: str = ""  # Why this change should help
    predicted_improvements: Dict[str, float] = field(default_factory=dict)  # dimension -> predicted delta
    
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "original_prompt_id": self.original_prompt_id,
            "weakness_addressed": self.weakness_addressed,
            "original_text": self.original_text,
            "recommended_text": self.recommended_text,
            "reasoning": self.reasoning,
            "predicted_improvements": self.predicted_improvements,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class PromptDiff:
    """Structured diff between two prompts."""
    
    original_id: str = ""
    original_text: str = ""
    updated_id: str = ""
    updated_text: str = ""
    
    # Diff components
    added_sections: List[str] = field(default_factory=list)  # New instructions
    removed_sections: List[str] = field(default_factory=list)  # Removed instructions
    modified_sections: List[Tuple[str, str]] = field(default_factory=list)  # (original, updated)
    
    # Justification
    rationale: str = ""
    expected_impact: Dict[str, float] = field(default_factory=dict)  # dimension -> expected change
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "original_id": self.original_id,
            "original_text": self.original_text,
            "updated_id": self.updated_id,
            "updated_text": self.updated_text,
            "added_sections": self.added_sections,
            "removed_sections": self.removed_sections,
            "modified_sections": self.modified_sections,
            "rationale": self.rationale,
            "expected_impact": self.expected_impact,
        }


@dataclass
class ApprovalRequest:
    """Request for human approval of a prompt change."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    prompt_diff: PromptDiff = field(default_factory=PromptDiff)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None  # Human reviewer
    approved_at: Optional[datetime] = None
    
    rejection_reason: str = ""  # If rejected, why?
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "prompt_diff": self.prompt_diff.to_dict(),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class PromptVersion:
    """Single version of a prompt with performance metrics."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    prompt_id: str = ""  # Group ID (all variants of same prompt)
    version: int = 0  # Version number within group
    
    text: str = ""
    origin: PromptOrigin = PromptOrigin.ORIGINAL
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    approval_request_id: Optional[str] = None  # If from approval
    
    # Performance metrics
    total_evals: int = 0
    avg_overall_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)  # dimension -> avg score
    failed_cases: List[str] = field(default_factory=list)  # Case IDs that failed
    
    is_active: bool = False  # Currently in use
    superseded_by: Optional[str] = None  # If replaced by newer version
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "version": self.version,
            "text": self.text,
            "origin": self.origin.value,
            "created_at": self.created_at.isoformat(),
            "approval_request_id": self.approval_request_id,
            "total_evals": self.total_evals,
            "avg_overall_score": self.avg_overall_score,
            "dimension_scores": self.dimension_scores,
            "failed_cases": self.failed_cases,
            "is_active": self.is_active,
            "superseded_by": self.superseded_by,
        }


@dataclass
class PerformanceDelta:
    """Track performance change between prompt versions."""
    
    baseline_version_id: str = ""
    new_version_id: str = ""
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Metrics
    overall_score_delta: float = 0.0  # New - baseline
    dimension_deltas: Dict[str, float] = field(default_factory=dict)  # dimension -> delta
    
    cases_improved: List[str] = field(default_factory=list)
    cases_regressed: List[str] = field(default_factory=list)
    
    is_improvement: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "baseline_version_id": self.baseline_version_id,
            "new_version_id": self.new_version_id,
            "timestamp": self.timestamp.isoformat(),
            "overall_score_delta": self.overall_score_delta,
            "dimension_deltas": self.dimension_deltas,
            "cases_improved": self.cases_improved,
            "cases_regressed": self.cases_regressed,
            "is_improvement": self.is_improvement,
        }


class MetaAgent:
    """Analyzes evaluations and generates prompt improvements."""
    
    def analyze_failed_evals(
        self,
        results: List[EvaluationResult],
        threshold: float = 0.7,
    ) -> List[FailedEval]:
        """Identify and analyze failed evaluations."""
        failed = []
        
        for result in results:
            if result.overall_score < threshold:
                # Find weakest dimensions
                weakest = sorted(
                    result.dimension_scores.items(),
                    key=lambda x: x[1].numeric_score,
                )
                weakest_dims = [dim for dim, score in weakest[:3]]
                
                failed.append(FailedEval(
                    result_id=str(result.id),
                    case_id=result.case_id,
                    case_category=result.case_category,
                    prompt=result.prompt,
                    expected=result.case_category.value,  # Simplified
                    actual=result.agent_outputs.get("final_answer", ""),
                    dimension_scores={dim: score.numeric_score for dim, score in result.dimension_scores.items()},
                    overall_score=result.overall_score,
                    weakest_dimensions=weakest_dims,
                ))
        
        return failed
    
    def identify_prompt_weaknesses(
        self,
        failed_evals: List[FailedEval],
    ) -> List[PromptWeakness]:
        """Identify common weaknesses across failed evaluations."""
        weakness_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "cases": set(),
            "scores": [],
        })
        
        # Group by weakness type
        for eval_result in failed_evals:
            for weak_dim in eval_result.weakest_dimensions:
                key = f"{weak_dim}_low"
                weakness_map[key]["cases"].add(eval_result.case_id)
                weakness_map[key]["scores"].append(eval_result.dimension_scores.get(weak_dim, 0.0))
        
        # Convert to PromptWeakness objects
        weaknesses = []
        for weakness_type, data in weakness_map.items():
            if data["cases"]:
                avg_score = sum(data["scores"]) / len(data["scores"])
                impact = 1.0 - avg_score  # How much it drags down score
                
                weaknesses.append(PromptWeakness(
                    prompt_id="",  # Set by caller
                    weakness_type=weakness_type,
                    affected_cases=list(data["cases"]),
                    avg_impact=impact,
                    evidence={
                        "count": len(data["cases"]),
                        "avg_score": avg_score,
                    },
                ))
        
        return sorted(weaknesses, key=lambda w: w.avg_impact, reverse=True)
    
    def generate_prompt_recommendation(
        self,
        original_prompt: str,
        weakness: PromptWeakness,
    ) -> PromptRecommendation:
        """Generate an improved version of the prompt."""
        # Map weakness to improvement strategy
        improvement_map = {
            "correctness_low": {
                "addition": "Prioritize answer accuracy above all else. If uncertain, explain the uncertainty rather than guessing.",
                "impact": {"correctness": 0.15},
            },
            "citation_accuracy_low": {
                "addition": "Always cite your sources. For each claim, specify exactly which source it comes from.",
                "impact": {"citation_accuracy": 0.20},
            },
            "contradiction_resolution_low": {
                "addition": "When you encounter conflicting information, explicitly acknowledge the contradiction and explain how you're resolving it.",
                "impact": {"contradiction_resolution": 0.25},
            },
            "tool_efficiency_low": {
                "addition": "Use only the minimum necessary tools. Prefer direct answers when possible.",
                "impact": {"tool_efficiency": 0.15},
            },
            "context_compliance_low": {
                "addition": "Respect all context constraints. Before providing an answer, verify you've satisfied every constraint.",
                "impact": {"context_compliance": 0.20},
            },
            "critique_agreement_low": {
                "addition": "Take critical feedback seriously. If a critique flags a claim, be willing to reject it.",
                "impact": {"critique_agreement": 0.18},
            },
        }
        
        improvement = improvement_map.get(weakness.weakness_type, {
            "addition": "Improve clarity and accuracy in your responses.",
            "impact": {"overall": 0.10},
        })
        
        # Generate recommendation
        recommended_text = f"{original_prompt}\n\n[IMPROVEMENT: {improvement['addition']}]"
        
        return PromptRecommendation(
            original_prompt_id="",
            weakness_addressed=weakness.weakness_type,
            original_text=original_prompt,
            recommended_text=recommended_text,
            reasoning=f"Addresses {weakness.weakness_type} which affected {len(weakness.affected_cases)} cases",
            predicted_improvements=improvement["impact"],
        )
    
    def create_prompt_diff(
        self,
        recommendation: PromptRecommendation,
    ) -> PromptDiff:
        """Create structured diff of prompt changes."""
        original_lines = set(recommendation.original_text.split("\n"))
        recommended_lines = set(recommendation.recommended_text.split("\n"))
        
        added = list(recommended_lines - original_lines)
        removed = list(original_lines - recommended_lines)
        
        return PromptDiff(
            original_id="",
            original_text=recommendation.original_text,
            updated_id="",
            updated_text=recommendation.recommended_text,
            added_sections=added,
            removed_sections=removed,
            modified_sections=[],
            rationale=recommendation.reasoning,
            expected_impact=recommendation.predicted_improvements,
        )


class PromptOptimizer:
    """Manages prompt versions, approvals, and performance tracking."""
    
    def __init__(self, storage_dir: Path = Path("prompt_versions")):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.versions: Dict[str, PromptVersion] = {}
        self.approval_requests: Dict[str, ApprovalRequest] = {}
        self.performance_deltas: List[PerformanceDelta] = []
        
        self._load_history()
    
    def create_approval_request(
        self,
        diff: PromptDiff,
        expires_in_hours: int = 24,
    ) -> ApprovalRequest:
        """Create approval request. MANDATORY human review."""
        request = ApprovalRequest(
            prompt_diff=diff,
            expires_at=datetime.utcnow() if expires_in_hours > 0 else None,
        )
        
        self.approval_requests[request.id] = request
        self._save_approval_request(request)
        
        return request
    
    def get_pending_approvals(self) -> List[ApprovalRequest]:
        """Get all pending approval requests."""
        return [
            r for r in self.approval_requests.values()
            if r.status == ApprovalStatus.PENDING
        ]
    
    def approve_prompt(
        self,
        approval_request_id: str,
        approved_by: str,
        new_version_text: str,
    ) -> PromptVersion:
        """
        Approve a prompt change.
        
        Returns new PromptVersion that is now active.
        HUMAN APPROVAL MANDATORY.
        """
        if approval_request_id not in self.approval_requests:
            raise ValueError(f"Approval request {approval_request_id} not found")
        
        request = self.approval_requests[approval_request_id]
        
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Request already {request.status.value}")
        
        # Mark as approved
        request.status = ApprovalStatus.APPROVED
        request.approved_by = approved_by
        request.approved_at = datetime.utcnow()
        
        # Create new version
        version = PromptVersion(
            prompt_id="approved_prompt",
            text=new_version_text,
            origin=PromptOrigin.APPROVED,
            approval_request_id=approval_request_id,
            is_active=True,
        )
        
        # Deactivate previous version
        for v in self.versions.values():
            if v.is_active:
                v.is_active = False
                v.superseded_by = version.id
        
        self.versions[version.id] = version
        self._save_approval_request(request)
        self._save_version(version)
        
        return version
    
    def reject_prompt(
        self,
        approval_request_id: str,
        rejected_by: str,
        reason: str,
    ) -> None:
        """Reject a prompt change with reason."""
        if approval_request_id not in self.approval_requests:
            raise ValueError(f"Approval request {approval_request_id} not found")
        
        request = self.approval_requests[approval_request_id]
        
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Request already {request.status.value}")
        
        request.status = ApprovalStatus.REJECTED
        request.approved_by = rejected_by  # Who rejected it
        request.approved_at = datetime.utcnow()
        request.rejection_reason = reason
        
        self._save_approval_request(request)
    
    def record_version_performance(
        self,
        version_id: str,
        results: List[EvaluationResult],
    ) -> PromptVersion:
        """Record performance metrics for a prompt version."""
        if version_id not in self.versions:
            raise ValueError(f"Version {version_id} not found")
        
        version = self.versions[version_id]
        version.total_evals = len(results)
        version.avg_overall_score = sum(r.overall_score for r in results) / len(results) if results else 0.0
        
        # Aggregate dimension scores
        dim_scores: Dict[str, List[float]] = defaultdict(list)
        failed_cases = []
        
        for result in results:
            for dim, score in result.dimension_scores.items():
                dim_scores[dim].append(score.numeric_score)
            
            if result.overall_score < 0.7:
                failed_cases.append(result.case_id)
        
        version.dimension_scores = {
            dim: sum(scores) / len(scores)
            for dim, scores in dim_scores.items()
        }
        version.failed_cases = failed_cases
        
        self._save_version(version)
        return version
    
    def compare_versions(
        self,
        baseline_version_id: str,
        new_version_id: str,
        baseline_results: List[EvaluationResult],
        new_results: List[EvaluationResult],
    ) -> PerformanceDelta:
        """Compare two prompt versions and compute delta."""
        baseline_avg = sum(r.overall_score for r in baseline_results) / len(baseline_results) if baseline_results else 0.0
        new_avg = sum(r.overall_score for r in new_results) / len(new_results) if new_results else 0.0
        
        delta = PerformanceDelta(
            baseline_version_id=baseline_version_id,
            new_version_id=new_version_id,
            overall_score_delta=new_avg - baseline_avg,
            is_improvement=new_avg > baseline_avg,
        )
        
        # Compute dimension deltas
        baseline_by_case = {r.case_id: r for r in baseline_results}
        improved_cases = []
        regressed_cases = []
        
        for new_result in new_results:
            if new_result.case_id in baseline_by_case:
                baseline_result = baseline_by_case[new_result.case_id]
                
                if new_result.overall_score > baseline_result.overall_score:
                    improved_cases.append(new_result.case_id)
                elif new_result.overall_score < baseline_result.overall_score:
                    regressed_cases.append(new_result.case_id)
        
        delta.cases_improved = improved_cases
        delta.cases_regressed = regressed_cases
        
        self.performance_deltas.append(delta)
        self._save_performance_delta(delta)
        
        return delta
    
    def get_active_version(self) -> Optional[PromptVersion]:
        """Get currently active prompt version."""
        for version in self.versions.values():
            if version.is_active:
                return version
        return None
    
    def get_version_history(self, prompt_id: str) -> List[PromptVersion]:
        """Get all versions of a prompt."""
        return sorted(
            [v for v in self.versions.values() if v.prompt_id == prompt_id],
            key=lambda v: v.created_at,
            reverse=True,
        )
    
    def _save_version(self, version: PromptVersion) -> None:
        """Save version to disk."""
        versions_file = self.storage_dir / "versions.jsonl"
        with open(versions_file, "a") as f:
            f.write(json.dumps(version.to_dict(), default=str) + "\n")
    
    def _save_approval_request(self, request: ApprovalRequest) -> None:
        """Save approval request to disk."""
        requests_file = self.storage_dir / "approval_requests.jsonl"
        with open(requests_file, "a") as f:
            f.write(json.dumps(request.to_dict(), default=str) + "\n")
    
    def _save_performance_delta(self, delta: PerformanceDelta) -> None:
        """Save performance delta to disk."""
        deltas_file = self.storage_dir / "performance_deltas.jsonl"
        with open(deltas_file, "a") as f:
            f.write(json.dumps(delta.to_dict(), default=str) + "\n")
    
    def _load_history(self) -> None:
        """Load versions and approval history from disk."""
        # Load versions
        versions_file = self.storage_dir / "versions.jsonl"
        if versions_file.exists():
            with open(versions_file) as f:
                for line in f:
                    data = json.loads(line)
                    # Reconstruct PromptVersion (simplified)
                    self.versions[data.get("id", "")] = data
        
        # Load approval requests
        requests_file = self.storage_dir / "approval_requests.jsonl"
        if requests_file.exists():
            with open(requests_file) as f:
                for line in f:
                    data = json.loads(line)
                    self.approval_requests[data.get("id", "")] = data
