"""
Custom evaluation harness for reproducible, multidimensional agent testing.

Design principles:
- No external eval frameworks (all logic self-contained)
- Reproducible: deterministic seeding, exact payload capture
- Multidimensional: 6 independent scoring dimensions
- Explainable: every score includes textual justification
- Traceable: full provenance stored (prompts, outputs, traces, metadata)
- Comparable: diffs between sequential runs
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import hashlib
from uuid import uuid4

from ..schemas import AgentMessage, ExecutionTrace, MessageRole, SharedContext, ContextMetadata


class CaseCategory(str, Enum):
    """Test case categories."""
    BASELINE = "baseline"           # Straightforward, clear correct answer
    AMBIGUOUS = "ambiguous"         # Multiple valid interpretations
    ADVERSARIAL = "adversarial"     # Designed to expose weaknesses


class ScoringDimension(str, Enum):
    """Scoring dimensions."""
    CORRECTNESS = "correctness"                            # Answer accuracy (0-1)
    CITATION_ACCURACY = "citation_accuracy"               # Citation correctness (0-1)
    CONTRADICTION_RESOLUTION = "contradiction_resolution" # Handles contradictions well (0-1)
    TOOL_EFFICIENCY = "tool_efficiency"                   # Tool calls vs needed (0-1)
    CONTEXT_COMPLIANCE = "context_compliance"             # Follows constraints (0-1)
    CRITIQUE_AGREEMENT = "critique_agreement"             # Aligns with critique feedback (0-1)


@dataclass
class DimensionScore:
    """Score for a single dimension."""
    
    dimension: ScoringDimension
    numeric_score: float  # 0.0 to 1.0
    justification: str    # Textual explanation
    evidence: Dict[str, Any] = field(default_factory=dict)  # Supporting details


@dataclass
class EvaluationResult:
    """Complete evaluation of a case."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    case_id: str = ""
    case_category: CaseCategory = CaseCategory.BASELINE
    prompt: str = ""
    
    # Execution details
    execution_trace: Optional[ExecutionTrace] = None
    agent_outputs: Dict[str, Any] = field(default_factory=dict)
    
    # Scoring
    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)
    overall_score: float = 0.0
    
    # Metadata
    run_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    
    def get_score(self, dimension: ScoringDimension) -> Optional[DimensionScore]:
        """Retrieve score for a dimension."""
        return self.dimension_scores.get(dimension.value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "case_id": self.case_id,
            "case_category": self.case_category.value,
            "prompt": self.prompt,
            "execution_trace_id": str(self.execution_trace.id) if self.execution_trace else None,
            "agent_outputs": self.agent_outputs,
            "dimension_scores": {
                dim: {
                    "numeric_score": score.numeric_score,
                    "justification": score.justification,
                    "evidence": score.evidence,
                }
                for dim, score in self.dimension_scores.items()
            },
            "overall_score": self.overall_score,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }


@dataclass
class EvaluationCase:
    """Single evaluation case."""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    category: CaseCategory = CaseCategory.BASELINE
    
    # The query
    prompt: str = ""
    context: Optional[SharedContext] = None
    
    # Expected outcomes
    expected_correctness: str = ""      # Ideal answer
    expected_contradictions: List[str] = field(default_factory=list)  # Known contradictions to resolve
    expected_citations: List[Dict[str, str]] = field(default_factory=list)  # (claim, source_id)
    constraints_to_check: List[str] = field(default_factory=list)  # Context constraints to verify
    
    # Adversarial notes
    adversarial_goal: str = ""  # What we're testing for (e.g., "detect hallucination")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "category": self.category.value,
            "prompt": self.prompt,
            "expected_correctness": self.expected_correctness,
            "expected_contradictions": self.expected_contradictions,
            "expected_citations": self.expected_citations,
            "constraints_to_check": self.constraints_to_check,
            "adversarial_goal": self.adversarial_goal,
        }


class DimensionScorer:
    """Scores a single dimension."""
    
    def score_correctness(
        self,
        prompt: str,
        agent_output: Dict[str, Any],
        expected_answer: str,
    ) -> DimensionScore:
        """Score correctness of the answer."""
        output_text = agent_output.get("final_answer") or agent_output.get("answer") or str(agent_output)
        
        # Simple heuristics: check if key terms from expected answer appear in output
        expected_terms = set(expected_answer.lower().split()) - {"the", "a", "an", "is", "are", "and", "or", "to", "in", "of"}
        output_terms = set(output_text.lower().split()) - {"the", "a", "an", "is", "are", "and", "or", "to", "in", "of"}
        
        overlap = len(expected_terms & output_terms)
        possible = max(len(expected_terms), 1)
        numeric_score = min(1.0, overlap / possible * 1.5)  # 1.5x to account for partial matches
        
        justification = f"Expected key terms: {expected_terms}. Found: {expected_terms & output_terms}. Match rate: {numeric_score:.2f}"
        
        return DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"expected_terms": list(expected_terms), "matched_terms": list(expected_terms & output_terms)},
        )
    
    def score_citation_accuracy(
        self,
        agent_output: Dict[str, Any],
        expected_citations: List[Dict[str, str]],
    ) -> DimensionScore:
        """Score citation accuracy."""
        output_citations = agent_output.get("citation_mapping", {})
        
        if not expected_citations:
            numeric_score = 1.0 if not output_citations else 0.8
            justification = "No citations expected. Output contains citations." if output_citations else "No citations expected or provided."
            return DimensionScore(
                dimension=ScoringDimension.CITATION_ACCURACY,
                numeric_score=numeric_score,
                justification=justification,
                evidence={"output_citations": len(output_citations)},
            )
        
        matched = 0
        for claim in agent_output.get("claims", []):
            claim_citations = claim.get("citations", [])
            if claim_citations:
                matched += 1
        
        citation_rate = matched / len(expected_citations) if expected_citations else 1.0
        numeric_score = min(1.0, citation_rate)
        
        justification = f"Expected {len(expected_citations)} citations. Found {matched} claims with citations."
        
        return DimensionScore(
            dimension=ScoringDimension.CITATION_ACCURACY,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"expected": len(expected_citations), "matched": matched},
        )
    
    def score_contradiction_resolution(
        self,
        agent_output: Dict[str, Any],
        expected_contradictions: List[str],
    ) -> DimensionScore:
        """Score handling of contradictions."""
        if not expected_contradictions:
            numeric_score = 1.0
            justification = "No contradictions expected."
            return DimensionScore(
                dimension=ScoringDimension.CONTRADICTION_RESOLUTION,
                numeric_score=numeric_score,
                justification=justification,
                evidence={},
            )
        
        # Check if output acknowledges contradictions or picks one consistently
        rejected_claims = agent_output.get("rejected_claims", [])
        conflict_log = agent_output.get("conflict_resolution_log", [])
        
        resolved = len(rejected_claims) + len(conflict_log)
        numeric_score = min(1.0, resolved / len(expected_contradictions))
        
        justification = f"Expected {len(expected_contradictions)} contradictions. Resolved {resolved} explicitly."
        
        return DimensionScore(
            dimension=ScoringDimension.CONTRADICTION_RESOLUTION,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"rejected": len(rejected_claims), "conflicts_logged": len(conflict_log)},
        )
    
    def score_tool_efficiency(
        self,
        execution_trace: Optional[ExecutionTrace],
    ) -> DimensionScore:
        """Score tool call efficiency."""
        if not execution_trace:
            numeric_score = 0.5
            justification = "No execution trace available."
            return DimensionScore(
                dimension=ScoringDimension.TOOL_EFFICIENCY,
                numeric_score=numeric_score,
                justification=justification,
                evidence={},
            )
        
        tool_calls = len([s for s in execution_trace.steps if hasattr(s, 'step_type') and s.step_type.value == "tool_call"])
        
        # Heuristic: fewer tool calls is better, but some calls are necessary
        # Optimal range is 2-4 calls; penalize if too few (< 1) or too many (> 8)
        if tool_calls < 1:
            numeric_score = 0.3
        elif 1 <= tool_calls <= 4:
            numeric_score = 1.0
        elif 5 <= tool_calls <= 8:
            numeric_score = 0.7
        else:
            numeric_score = 0.4
        
        justification = f"Made {tool_calls} tool calls. Optimal range is 2-4."
        
        return DimensionScore(
            dimension=ScoringDimension.TOOL_EFFICIENCY,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"tool_calls": tool_calls},
        )
    
    def score_context_compliance(
        self,
        context: Optional[SharedContext],
        agent_output: Dict[str, Any],
        constraints_to_check: List[str],
    ) -> DimensionScore:
        """Score adherence to context constraints."""
        if not constraints_to_check:
            numeric_score = 1.0
            justification = "No constraints to check."
            return DimensionScore(
                dimension=ScoringDimension.CONTEXT_COMPLIANCE,
                numeric_score=numeric_score,
                justification=justification,
                evidence={},
            )
        
        if not context:
            numeric_score = 0.5
            justification = "No context provided to check constraints."
            return DimensionScore(
                dimension=ScoringDimension.CONTEXT_COMPLIANCE,
                numeric_score=numeric_score,
                justification=justification,
                evidence={},
            )
        
        satisfied = 0
        for constraint_desc in constraints_to_check:
            # Very simple check: see if constraint keywords appear in output
            if any(word in str(agent_output).lower() for word in constraint_desc.lower().split()):
                satisfied += 1
        
        numeric_score = satisfied / len(constraints_to_check)
        justification = f"Satisfied {satisfied}/{len(constraints_to_check)} constraints."
        
        return DimensionScore(
            dimension=ScoringDimension.CONTEXT_COMPLIANCE,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"satisfied": satisfied, "total": len(constraints_to_check)},
        )
    
    def score_critique_agreement(
        self,
        agent_output: Dict[str, Any],
        critique_feedback: Optional[Dict[str, Any]] = None,
    ) -> DimensionScore:
        """Score agreement with critique feedback."""
        if not critique_feedback:
            # No critique available; assume neutral
            numeric_score = 0.5
            justification = "No critique feedback available for comparison."
            return DimensionScore(
                dimension=ScoringDimension.CRITIQUE_AGREEMENT,
                numeric_score=numeric_score,
                justification=justification,
                evidence={},
            )
        
        # Check if output addresses critique concerns
        findings = critique_feedback.get("findings", [])
        rejected_claims = agent_output.get("rejected_claims", [])
        
        # Agreement: high if claims flagged by critique are in rejected_claims
        addressed = 0
        for finding in findings:
            finding_target = finding.get("target_id")
            if finding_target in rejected_claims:
                addressed += 1
        
        numeric_score = addressed / len(findings) if findings else 1.0
        justification = f"Addressed {addressed}/{len(findings)} critique findings."
        
        return DimensionScore(
            dimension=ScoringDimension.CRITIQUE_AGREEMENT,
            numeric_score=numeric_score,
            justification=justification,
            evidence={"addressed": addressed, "total": len(findings)},
        )


class EvaluationHarness:
    """Main evaluation harness orchestrator."""
    
    def __init__(self, output_dir: Path = Path("evaluation_runs")):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = str(uuid4())
        self.run_timestamp = datetime.utcnow()
        self.scorer = DimensionScorer()
        self.results: List[EvaluationResult] = []
    
    def evaluate_case(
        self,
        case: EvaluationCase,
        execution_trace: Optional[ExecutionTrace] = None,
        agent_outputs: Optional[Dict[str, Any]] = None,
        critique_feedback: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
    ) -> EvaluationResult:
        """Evaluate a single case and return scored result."""
        agent_outputs = agent_outputs or {}
        
        result = EvaluationResult(
            case_id=case.id,
            case_category=case.category,
            prompt=case.prompt,
            execution_trace=execution_trace,
            agent_outputs=agent_outputs,
            run_id=self.run_id,
            timestamp=datetime.utcnow(),
            duration_ms=duration_ms,
        )
        
        # Score each dimension
        scores = {
            ScoringDimension.CORRECTNESS: self.scorer.score_correctness(
                case.prompt,
                agent_outputs,
                case.expected_correctness,
            ),
            ScoringDimension.CITATION_ACCURACY: self.scorer.score_citation_accuracy(
                agent_outputs,
                case.expected_citations,
            ),
            ScoringDimension.CONTRADICTION_RESOLUTION: self.scorer.score_contradiction_resolution(
                agent_outputs,
                case.expected_contradictions,
            ),
            ScoringDimension.TOOL_EFFICIENCY: self.scorer.score_tool_efficiency(
                execution_trace,
            ),
            ScoringDimension.CONTEXT_COMPLIANCE: self.scorer.score_context_compliance(
                case.context,
                agent_outputs,
                case.constraints_to_check,
            ),
            ScoringDimension.CRITIQUE_AGREEMENT: self.scorer.score_critique_agreement(
                agent_outputs,
                critique_feedback,
            ),
        }
        
        result.dimension_scores = {dim.value: score for dim, score in scores.items()}
        result.overall_score = sum(score.numeric_score for score in scores.values()) / len(scores)
        
        self.results.append(result)
        return result
    
    def save_results(self) -> Path:
        """Save all results to JSON file."""
        results_file = self.output_dir / f"results_{self.run_id}.json"
        results_data = {
            "run_id": self.run_id,
            "timestamp": self.run_timestamp.isoformat(),
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_cases": len(self.results),
                "average_overall_score": sum(r.overall_score for r in self.results) / len(self.results) if self.results else 0.0,
                "by_category": self._summary_by_category(),
            }
        }
        
        with open(results_file, "w") as f:
            json.dump(results_data, f, indent=2, default=str)
        
        return results_file
    
    def load_previous_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load a previous evaluation run for comparison."""
        results_file = self.output_dir / f"results_{run_id}.json"
        if results_file.exists():
            with open(results_file, "r") as f:
                return json.load(f)
        return None
    
    def compare_runs(self, run_id_1: str, run_id_2: str) -> Dict[str, Any]:
        """Compare two runs and return diffs."""
        run1 = self.load_previous_run(run_id_1)
        run2 = self.load_previous_run(run_id_2)
        
        if not run1 or not run2:
            return {"error": "One or both runs not found"}
        
        results_1 = {r["case_id"]: r for r in run1["results"]}
        results_2 = {r["case_id"]: r for r in run2["results"]}
        
        diffs = {
            "run_1_id": run_id_1,
            "run_2_id": run_id_2,
            "timestamp": datetime.utcnow().isoformat(),
            "case_diffs": [],
            "dimension_trend": {},
        }
        
        all_case_ids = set(results_1.keys()) | set(results_2.keys())
        
        for case_id in all_case_ids:
            r1 = results_1.get(case_id)
            r2 = results_2.get(case_id)
            
            if r1 and r2:
                score_delta = r2["overall_score"] - r1["overall_score"]
                diffs["case_diffs"].append({
                    "case_id": case_id,
                    "run1_overall": r1["overall_score"],
                    "run2_overall": r2["overall_score"],
                    "delta": score_delta,
                    "dimension_deltas": self._dimension_deltas(r1, r2),
                })
        
        # Aggregate trends
        for dim in ScoringDimension:
            dim_val = dim.value
            scores_1 = [r["dimension_scores"].get(dim_val, {}).get("numeric_score", 0.5) for r in run1["results"]]
            scores_2 = [r["dimension_scores"].get(dim_val, {}).get("numeric_score", 0.5) for r in run2["results"]]
            
            avg_1 = sum(scores_1) / len(scores_1) if scores_1 else 0.0
            avg_2 = sum(scores_2) / len(scores_2) if scores_2 else 0.0
            
            diffs["dimension_trend"][dim_val] = {
                "run1_avg": avg_1,
                "run2_avg": avg_2,
                "delta": avg_2 - avg_1,
            }
        
        return diffs
    
    def _summary_by_category(self) -> Dict[str, float]:
        """Summary statistics by case category."""
        by_cat = {}
        for cat in CaseCategory:
            cat_results = [r for r in self.results if r.case_category == cat]
            if cat_results:
                by_cat[cat.value] = sum(r.overall_score for r in cat_results) / len(cat_results)
        return by_cat
    
    def _dimension_deltas(self, r1: Dict[str, Any], r2: Dict[str, Any]) -> Dict[str, float]:
        """Calculate per-dimension score changes."""
        deltas = {}
        for dim in ScoringDimension:
            dim_val = dim.value
            s1 = r1.get("dimension_scores", {}).get(dim_val, {}).get("numeric_score", 0.5)
            s2 = r2.get("dimension_scores", {}).get(dim_val, {}).get("numeric_score", 0.5)
            deltas[dim_val] = s2 - s1
        return deltas
