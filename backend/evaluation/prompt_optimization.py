"""
Self-improving prompt optimization loop.

Analyzes failed evaluations, generates improved prompts, and requires mandatory
human approval before any changes are applied.

Design principles:
- No auto-apply: human approval mandatory for ALL prompt changes
- Explainability: show exactly what changed and why
- Traceability: full audit trail of all versions and approvals
- Reversibility: can always rollback to previous working versions
- Gradual improvement: one prompt at a time, targeted re-evaluation
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import json
import difflib

from backend.evaluation import EvaluationResult, ScoringDimension, CaseCategory


class ApprovalStatus(str, Enum):
    """Status of a prompt optimization."""
    PENDING = "pending"           # Awaiting human review
    APPROVED = "approved"         # Human approved
    REJECTED = "rejected"         # Human rejected
    APPLIED = "applied"           # Approved and applied to system
    REVERTED = "reverted"         # Previously applied but rolled back


class PromptRole(str, Enum):
    """Different prompt roles in the system."""
    DECOMPOSITION = "decomposition"           # Decompose queries
    RETRIEVAL_REASONING = "retrieval_reasoning"  # Retrieve and reason
    SYNTHESIS = "synthesis"                   # Synthesize answers
    CRITIQUE = "critique"                     # Critique outputs


@dataclass
class PromptVersion:
    """A single version of a prompt."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    role: PromptRole = PromptRole.DECOMPOSITION
    version_number: int = 1
    content: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""  # Human-readable description of this version
    
    # Performance metrics
    avg_correctness: float = 0.0
    avg_overall_score: float = 0.0
    test_count: int = 0
    
    # Metadata
    created_by: str = "system"
    is_active: bool = False  # Currently deployed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "role": self.role.value,
            "version_number": self.version_number,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "avg_correctness": self.avg_correctness,
            "avg_overall_score": self.avg_overall_score,
            "test_count": self.test_count,
            "created_by": self.created_by,
            "is_active": self.is_active,
        }


@dataclass
class PromptDiff:
    """Structured representation of prompt changes."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    role: PromptRole = PromptRole.DECOMPOSITION
    from_version_id: str = ""
    to_version_id: str = ""
    from_version_num: int = 0
    to_version_num: int = 0
    
    # Original and new content
    original_content: str = ""
    new_content: str = ""
    
    # Human-readable diff
    diff_lines: List[str] = field(default_factory=list)
    
    # Analysis
    change_summary: str = ""  # Why was this changed?
    changes_by_type: Dict[str, int] = field(default_factory=dict)  # added, removed, modified
    
    # Performance prediction
    expected_correctness_delta: float = 0.0  # Expected improvement
    expected_overall_delta: float = 0.0
    reasoning: str = ""  # Why we expect this to help
    
    # Approval
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approval_notes: str = ""
    approval_timestamp: Optional[datetime] = None
    
    # Metrics after application
    actual_correctness_delta: Optional[float] = None
    actual_overall_delta: Optional[float] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "role": self.role.value,
            "from_version": self.from_version_num,
            "to_version": self.to_version_num,
            "change_summary": self.change_summary,
            "changes_by_type": self.changes_by_type,
            "expected_deltas": {
                "correctness": self.expected_correctness_delta,
                "overall": self.expected_overall_delta,
            },
            "reasoning": self.reasoning,
            "approval_status": self.approval_status.value,
            "approved_by": self.approved_by,
            "approval_notes": self.approval_notes,
            "actual_deltas": {
                "correctness": self.actual_correctness_delta,
                "overall": self.actual_overall_delta,
            },
            "created_at": self.created_at.isoformat(),
            "diff_preview": "\n".join(self.diff_lines[:20]),  # First 20 lines for preview
        }


class PromptDiffGenerator:
    """Generates structured diffs between prompt versions."""
    
    @staticmethod
    def generate_diff(
        from_version: PromptVersion,
        to_version: PromptVersion,
        expected_correctness_delta: float = 0.0,
        expected_overall_delta: float = 0.0,
        reasoning: str = "",
    ) -> PromptDiff:
        """Generate a diff between two prompt versions."""
        
        # Create unified diff
        from_lines = from_version.content.splitlines(keepends=True)
        to_lines = to_version.content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"v{from_version.version_number}",
            tofile=f"v{to_version.version_number}",
            lineterm="",
        ))
        
        # Count changes
        added = len([l for l in diff_lines if l.startswith("+")])
        removed = len([l for l in diff_lines if l.startswith("-")])
        modified = min(added, removed)
        
        changes_by_type = {
            "added": added,
            "removed": removed,
            "modified": modified,
        }
        
        # Generate summary
        if not reasoning:
            if modified > 0:
                reasoning = f"Modified {modified} sections to improve prompt clarity"
            elif added > 0:
                reasoning = f"Added {added} lines to enhance instructions"
            else:
                reasoning = f"Removed {removed} lines to simplify prompt"
        
        diff = PromptDiff(
            role=from_version.role,
            from_version_id=from_version.id,
            to_version_id=to_version.id,
            from_version_num=from_version.version_number,
            to_version_num=to_version.version_number,
            original_content=from_version.content,
            new_content=to_version.content,
            diff_lines=diff_lines,
            change_summary=f"Update from v{from_version.version_number} to v{to_version.version_number}",
            changes_by_type=changes_by_type,
            expected_correctness_delta=expected_correctness_delta,
            expected_overall_delta=expected_overall_delta,
            reasoning=reasoning,
        )
        
        return diff


class PromptAnalyzer:
    """Analyzes evaluation results to identify weakest prompts."""
    
    @staticmethod
    def identify_weakest_role(
        results: List[EvaluationResult],
    ) -> Tuple[Optional[PromptRole], float]:
        """
        Identify which agent role is performing worst.
        
        Returns: (role, average_score)
        """
        # Simple heuristic: check prompt role based on case category
        # In real system, would parse agent_outputs to identify which role produced them
        
        scores_by_role = {}
        
        for result in results:
            # Heuristic: categorize by case difficulty
            if result.case_category == CaseCategory.BASELINE:
                role = PromptRole.DECOMPOSITION
            elif result.case_category == CaseCategory.AMBIGUOUS:
                role = PromptRole.RETRIEVAL_REASONING
            else:  # ADVERSARIAL
                role = PromptRole.CRITIQUE
            
            if role not in scores_by_role:
                scores_by_role[role] = []
            scores_by_role[role].append(result.overall_score)
        
        # Find role with lowest average score
        if not scores_by_role:
            return None, 0.0
        
        weakest_role = min(
            scores_by_role.keys(),
            key=lambda r: sum(scores_by_role[r]) / len(scores_by_role[r])
        )
        
        avg_score = sum(scores_by_role[weakest_role]) / len(scores_by_role[weakest_role])
        
        return weakest_role, avg_score
    
    @staticmethod
    def identify_failing_cases(
        results: List[EvaluationResult],
        threshold: float = 0.5,
    ) -> List[EvaluationResult]:
        """Identify cases scoring below threshold."""
        return [r for r in results if r.overall_score < threshold]
    
    @staticmethod
    def analyze_dimension_weaknesses(
        results: List[EvaluationResult],
    ) -> Dict[str, float]:
        """Analyze which dimensions are weakest across all results."""
        dimension_scores = {}
        
        for result in results:
            for dim_val, score in result.dimension_scores.items():
                if dim_val not in dimension_scores:
                    dimension_scores[dim_val] = []
                dimension_scores[dim_val].append(score.numeric_score)
        
        # Compute averages
        return {
            dim: sum(scores) / len(scores)
            for dim, scores in dimension_scores.items()
        }


class MetaAgent:
    """
    Meta-agent that proposes prompt improvements based on failed evaluations.
    
    Never auto-applies changes - always requires human approval.
    """
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
    
    def analyze_and_propose(
        self,
        failed_results: List[EvaluationResult],
        current_version: PromptVersion,
        dimension_weaknesses: Dict[str, float],
    ) -> Tuple[str, str]:
        """
        Analyze failed evaluations and propose improved prompt.
        
        Returns: (proposed_prompt_content, reasoning)
        """
        # Identify failure patterns
        correctness_issues = [r for r in failed_results if r.dimension_scores.get("correctness", None) and 
                             r.dimension_scores["correctness"].numeric_score < 0.3]
        
        tool_efficiency_issues = [r for r in failed_results if r.dimension_scores.get("tool_efficiency", None) and
                                 r.dimension_scores["tool_efficiency"].numeric_score < 0.3]
        
        # Generate reasoning about improvements
        reasoning = f"""
Analysis of {len(failed_results)} failed cases:

1. Correctness Issues: {len(correctness_issues)} cases
   - Current prompt may not be specific enough
   - Recommendation: Add examples and clarify expected output format

2. Tool Efficiency Issues: {len(tool_efficiency_issues)} cases  
   - Suggest using fewer tool calls or different retrieval strategy
   - Recommendation: Simplify retrieval instructions

3. Weakest Dimensions: {', '.join(sorted(dimension_weaknesses.keys(), 
                                         key=lambda d: dimension_weaknesses[d])[:3])}

Proposed improvements:
- Add more concrete examples to the prompt
- Clarify the decision-making process
- Simplify instructions to reduce ambiguity
"""
        
        # Generate improved prompt (simplified version - in real system would use LLM)
        improved_prompt = self._generate_improved_prompt(
            current_version.content,
            correctness_issues,
            tool_efficiency_issues,
        )
        
        return improved_prompt, reasoning
    
    def _generate_improved_prompt(
        self,
        current_prompt: str,
        correctness_issues: List[EvaluationResult],
        tool_efficiency_issues: List[EvaluationResult],
    ) -> str:
        """Generate an improved prompt (simplified - would use LLM in production)."""
        
        # In production, this would call Claude/GPT-4 with structured prompt
        # For now, we return an enhanced version
        
        improvements = []
        
        if correctness_issues:
            improvements.append(
                "\n# Correctness Improvements:\n"
                "- Provide 2-3 worked examples\n"
                "- Clarify expected output structure\n"
                "- Define edge cases explicitly"
            )
        
        if tool_efficiency_issues:
            improvements.append(
                "\n# Tool Efficiency Improvements:\n"
                "- Prioritize high-signal information retrieval\n"
                "- Limit to 2-3 most relevant sources\n"
                "- Cache repeated queries"
            )
        
        improved = current_prompt + "\n".join(improvements)
        return improved


class PromptOptimizationOrchestrator:
    """
    Orchestrates the prompt optimization loop with mandatory human approval.
    
    Workflow:
    1. Analyze evaluation results
    2. Identify weakest prompts
    3. Generate improved prompts
    4. Create diffs for human review
    5. Await human approval
    6. Apply approved changes
    7. Re-evaluate and track deltas
    """
    
    def __init__(self, output_dir: Path = Path("prompt_optimizations")):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.meta_agent = MetaAgent()
        self.analyzer = PromptAnalyzer()
        self.diff_gen = PromptDiffGenerator()
        
        self.prompt_versions: Dict[PromptRole, List[PromptVersion]] = {
            role: [] for role in PromptRole
        }
        self.diffs: List[PromptDiff] = []
    
    def register_prompt_version(self, version: PromptVersion) -> None:
        """Register a new prompt version."""
        self.prompt_versions[version.role].append(version)
    
    def analyze_results_and_propose(
        self,
        eval_results: List[EvaluationResult],
    ) -> List[PromptDiff]:
        """
        Analyze evaluation results and propose prompt improvements.
        
        Returns: List of proposed diffs awaiting approval.
        """
        proposed_diffs = []
        
        # Identify weakest role
        weakest_role, avg_score = self.analyzer.identify_weakest_role(eval_results)
        if not weakest_role:
            return []
        
        # Identify failing cases
        failing_cases = self.analyzer.identify_failing_cases(eval_results)
        if not failing_cases:
            return []
        
        # Analyze dimension weaknesses
        dim_weaknesses = self.analyzer.analyze_dimension_weaknesses(failing_cases)
        
        # Get current version of weakest role
        current_versions = self.prompt_versions.get(weakest_role, [])
        if not current_versions:
            return []
        
        current_version = current_versions[-1]  # Latest version
        
        # Have meta-agent propose improvement
        improved_prompt, reasoning = self.meta_agent.analyze_and_propose(
            failing_cases,
            current_version,
            dim_weaknesses,
        )
        
        # Create new version
        new_version = PromptVersion(
            role=weakest_role,
            version_number=current_version.version_number + 1,
            content=improved_prompt,
            description=f"Auto-optimized version: {reasoning.split(chr(10))[0]}",
            created_by="meta_agent",
        )
        
        # Generate diff
        diff = self.diff_gen.generate_diff(
            current_version,
            new_version,
            expected_correctness_delta=0.05,  # Expect 5% improvement
            expected_overall_delta=0.03,
            reasoning=reasoning,
        )
        
        self.diffs.append(diff)
        proposed_diffs.append(diff)
        
        # Save for human review
        self._save_diff_for_review(diff, new_version)
        
        return proposed_diffs
    
    def submit_for_approval(
        self,
        diff_id: str,
        approval_notes: str = "",
    ) -> PromptDiff:
        """Submit a proposed diff for human approval (queues it for human review)."""
        diff = next((d for d in self.diffs if d.id == diff_id), None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")
        
        # Mark as pending (already the default)
        diff.approval_status = ApprovalStatus.PENDING
        
        # Save to approval queue
        self._save_to_approval_queue(diff)
        
        return diff
    
    def approve_diff(
        self,
        diff_id: str,
        approved_by: str,
        approval_notes: str = "",
    ) -> PromptDiff:
        """
        Approve a proposed diff (MANDATORY HUMAN STEP).
        
        This transitions the diff to APPROVED status but does NOT apply it yet.
        Application requires a separate explicit action.
        """
        diff = next((d for d in self.diffs if d.id == diff_id), None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")
        
        diff.approval_status = ApprovalStatus.APPROVED
        diff.approved_by = approved_by
        diff.approval_notes = approval_notes
        diff.approval_timestamp = datetime.utcnow()
        
        self._save_diff(diff)
        
        return diff
    
    def reject_diff(
        self,
        diff_id: str,
        rejected_by: str,
        rejection_reason: str,
    ) -> PromptDiff:
        """
        Reject a proposed diff.
        
        The diff is marked as REJECTED and archived.
        """
        diff = next((d for d in self.diffs if d.id == diff_id), None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")
        
        diff.approval_status = ApprovalStatus.REJECTED
        diff.approved_by = rejected_by
        diff.approval_notes = f"Rejected: {rejection_reason}"
        diff.approval_timestamp = datetime.utcnow()
        
        self._save_diff(diff)
        
        return diff
    
    def apply_approved_diff(
        self,
        diff_id: str,
    ) -> Tuple[PromptVersion, PromptDiff]:
        """
        Apply an approved diff to the system.
        
        PRECONDITION: Diff must be in APPROVED status.
        This creates the new version and marks it as active.
        """
        diff = next((d for d in self.diffs if d.id == diff_id), None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")
        
        if diff.approval_status != ApprovalStatus.APPROVED:
            raise ValueError(
                f"Cannot apply diff in {diff.approval_status.value} status. "
                f"Must be APPROVED first."
            )
        
        # Create and register new version
        new_version = PromptVersion(
            role=diff.role,
            version_number=diff.to_version_num,
            content=diff.new_content,
            description=f"Applied optimization (v{diff.to_version_num})",
            is_active=True,
        )
        
        # Deactivate previous versions
        for v in self.prompt_versions[diff.role]:
            v.is_active = False
        
        self.register_prompt_version(new_version)
        
        # Mark diff as applied
        diff.approval_status = ApprovalStatus.APPLIED
        self._save_diff(diff)
        
        return new_version, diff
    
    def record_reeval_results(
        self,
        diff_id: str,
        new_results: List[EvaluationResult],
    ) -> PromptDiff:
        """
        Record re-evaluation results after applying an optimization.
        
        Calculates actual performance delta vs expected delta.
        """
        diff = next((d for d in self.diffs if d.id == diff_id), None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")
        
        if not new_results:
            return diff
        
        # Calculate deltas
        avg_correctness = sum(
            r.dimension_scores.get("correctness", None).numeric_score
            for r in new_results
            if r.dimension_scores.get("correctness", None)
        ) / len(new_results) if new_results else 0.0
        
        avg_overall = sum(r.overall_score for r in new_results) / len(new_results)
        
        # Store actual deltas (would compare to baseline in real system)
        diff.actual_correctness_delta = avg_correctness
        diff.actual_overall_delta = avg_overall
        
        self._save_diff(diff)
        
        return diff
    
    def get_pending_approvals(self) -> List[PromptDiff]:
        """Get all diffs awaiting human approval."""
        return [d for d in self.diffs if d.approval_status == ApprovalStatus.PENDING]
    
    def get_approval_history(self, role: PromptRole) -> List[PromptDiff]:
        """Get approval history for a specific prompt role."""
        return [
            d for d in self.diffs 
            if d.role == role and d.approval_status != ApprovalStatus.PENDING
        ]
    
    def _save_diff_for_review(self, diff: PromptDiff, new_version: PromptVersion) -> None:
        """Save diff to human review queue."""
        review_file = self.output_dir / "pending_approvals" / f"{diff.id}.json"
        review_file.parent.mkdir(parents=True, exist_ok=True)
        
        review_data = {
            "diff": diff.to_dict(),
            "new_version": new_version.to_dict(),
            "action_required": "HUMAN_APPROVAL",
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        with open(review_file, "w") as f:
            json.dump(review_data, f, indent=2, default=str)
    
    def _save_diff(self, diff: PromptDiff) -> None:
        """Save diff to archive."""
        archive_file = self.output_dir / "diffs" / f"{diff.id}.json"
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(archive_file, "w") as f:
            json.dump(diff.to_dict(), f, indent=2, default=str)
    
    def _save_to_approval_queue(self, diff: PromptDiff) -> None:
        """Add diff to approval queue."""
        queue_file = self.output_dir / "approval_queue.jsonl"
        
        with open(queue_file, "a") as f:
            f.write(json.dumps(diff.to_dict(), default=str) + "\n")
