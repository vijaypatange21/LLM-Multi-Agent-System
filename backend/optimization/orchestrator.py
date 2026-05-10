"""
Orchestrator for the prompt optimization pipeline.

Coordinates:
1. Analysis of failed evaluations
2. Weakness identification
3. Recommendation generation
4. Diff creation
5. Approval request workflow
6. Performance tracking
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json

from backend.evaluation import EvaluationResult, CaseCategory
from .prompt_optimizer import (
    MetaAgent,
    PromptOptimizer,
    PromptRecommendation,
    PromptDiff,
    ApprovalRequest,
    PromptVersion,
    PerformanceDelta,
)


class PromptOptimizationPipeline:
    """End-to-end prompt optimization with mandatory approval."""
    
    def __init__(
        self,
        storage_dir: Path = Path("prompt_optimization"),
        failure_threshold: float = 0.7,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.failure_threshold = failure_threshold
        self.meta_agent = MetaAgent()
        self.optimizer = PromptOptimizer(storage_dir=self.storage_dir / "versions")
        
        self.analysis_log_file = self.storage_dir / "analysis.jsonl"
    
    def analyze_and_recommend(
        self,
        eval_results: List[EvaluationResult],
        current_prompt: str,
    ) -> Dict[str, any]:
        """
        Analyze evaluation results and generate improvement recommendations.
        
        Returns:
        {
            "failed_evals": [...],
            "weaknesses": [...],
            "recommendations": [...],
            "diffs": [...],
            "approval_requests": [...],
        }
        """
        # Step 1: Identify failures
        failed_evals = self.meta_agent.analyze_failed_evals(
            eval_results,
            threshold=self.failure_threshold,
        )
        
        if not failed_evals:
            return {
                "status": "no_failures",
                "message": f"All evaluations above {self.failure_threshold} threshold",
                "failed_evals": [],
                "weaknesses": [],
                "recommendations": [],
                "diffs": [],
                "approval_requests": [],
            }
        
        # Step 2: Identify weaknesses
        weaknesses = self.meta_agent.identify_prompt_weaknesses(failed_evals)
        
        # Step 3: Generate recommendations (one per weakness)
        recommendations = []
        for weakness in weaknesses:
            rec = self.meta_agent.generate_prompt_recommendation(
                current_prompt,
                weakness,
            )
            recommendations.append(rec)
        
        # Step 4: Create diffs
        diffs = []
        for rec in recommendations:
            diff = self.meta_agent.create_prompt_diff(rec)
            diff.original_id = "current"
            diff.updated_id = rec.id
            diffs.append(diff)
        
        # Step 5: Create approval requests (MANDATORY HUMAN REVIEW)
        approval_requests = []
        for diff in diffs:
            request = self.optimizer.create_approval_request(diff)
            approval_requests.append(request)
        
        # Log analysis
        self._log_analysis({
            "timestamp": datetime.utcnow().isoformat(),
            "num_failed_evals": len(failed_evals),
            "num_weaknesses": len(weaknesses),
            "num_recommendations": len(recommendations),
            "approval_requests": [r.id for r in approval_requests],
        })
        
        return {
            "status": "pending_approval",
            "timestamp": datetime.utcnow().isoformat(),
            "failed_evals": [asdict_eval(e) for e in failed_evals],
            "weaknesses": [asdict_weakness(w) for w in weaknesses],
            "recommendations": [r.to_dict() for r in recommendations],
            "diffs": [d.to_dict() for d in diffs],
            "approval_requests": [r.to_dict() for r in approval_requests],
        }
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approval requests awaiting human review."""
        requests = self.optimizer.get_pending_approvals()
        return [r.to_dict() for r in requests]
    
    def approve_and_deploy(
        self,
        approval_request_id: str,
        approved_by: str,
        new_prompt: str,
    ) -> PromptVersion:
        """
        Approve a prompt change and deploy it.
        
        This is the ONLY way to apply prompt changes.
        Requires explicit human approval.
        """
        return self.optimizer.approve_prompt(
            approval_request_id,
            approved_by,
            new_prompt,
        )
    
    def reject_change(
        self,
        approval_request_id: str,
        rejected_by: str,
        reason: str,
    ) -> None:
        """Reject a proposed prompt change."""
        self.optimizer.reject_prompt(
            approval_request_id,
            rejected_by,
            reason,
        )
    
    def evaluate_new_prompt(
        self,
        version_id: str,
        results: List[EvaluationResult],
    ) -> PromptVersion:
        """Record performance of a new prompt version."""
        return self.optimizer.record_version_performance(version_id, results)
    
    def compare_performance(
        self,
        baseline_version_id: str,
        new_version_id: str,
        baseline_results: List[EvaluationResult],
        new_results: List[EvaluationResult],
    ) -> PerformanceDelta:
        """Compare performance between prompt versions."""
        return self.optimizer.compare_versions(
            baseline_version_id,
            new_version_id,
            baseline_results,
            new_results,
        )
    
    def get_optimization_history(self) -> Dict[str, any]:
        """Get full history of optimization attempts."""
        return {
            "optimization_dir": str(self.storage_dir),
            "num_versions": len(self.optimizer.versions),
            "num_approval_requests": len(self.optimizer.approval_requests),
            "num_performance_deltas": len(self.optimizer.performance_deltas),
            "active_version": self._active_version_summary(),
            "approval_summary": self._approval_summary(),
            "performance_trend": self._performance_trend(),
        }
    
    def print_status(self) -> None:
        """Print human-readable status."""
        print("\n" + "=" * 70)
        print("PROMPT OPTIMIZATION STATUS")
        print("=" * 70)
        
        pending = self.get_pending_approvals()
        print(f"\n⏳ Pending Approvals: {len(pending)}")
        
        for req in pending[:5]:  # Show first 5
            diff = req.get("prompt_diff", {})
            print(f"   ID: {req['id'][:8]}...")
            print(f"   Added: {len(diff.get('added_sections', []))} sections")
            print(f"   Removed: {len(diff.get('removed_sections', []))} sections")
            print()
        
        active = self.optimizer.get_active_version()
        if active:
            print(f"\n✅ Active Version: {active.id[:8]}...")
            print(f"   Score: {active.avg_overall_score:.3f}")
            print(f"   Evals: {active.total_evals}")
        
        print("=" * 70 + "\n")
    
    def _log_analysis(self, data: Dict) -> None:
        """Log analysis to file."""
        with open(self.analysis_log_file, "a") as f:
            f.write(json.dumps(data, default=str) + "\n")
    
    def _active_version_summary(self) -> Dict:
        """Summarize active version."""
        active = self.optimizer.get_active_version()
        if not active:
            return {}
        return {
            "id": active.id,
            "version": active.version,
            "score": active.avg_overall_score,
            "total_evals": active.total_evals,
            "failed_cases": len(active.failed_cases),
        }
    
    def _approval_summary(self) -> Dict[str, int]:
        """Summarize approval statuses."""
        from collections import defaultdict
        summary = defaultdict(int)
        for req in self.optimizer.approval_requests.values():
            summary[req.status.value] += 1
        return dict(summary)
    
    def _performance_trend(self) -> List[Dict]:
        """Get performance improvement trend."""
        trend = []
        for delta in self.optimizer.performance_deltas[-10:]:  # Last 10
            trend.append({
                "timestamp": delta.timestamp.isoformat(),
                "delta": delta.overall_score_delta,
                "improved": delta.is_improvement,
            })
        return trend


def asdict_eval(eval_obj) -> Dict:
    """Convert FailedEval to dict."""
    return {
        "result_id": eval_obj.result_id,
        "case_id": eval_obj.case_id,
        "case_category": eval_obj.case_category.value,
        "prompt": eval_obj.prompt[:100],  # Truncate
        "overall_score": eval_obj.overall_score,
        "weakest_dimensions": eval_obj.weakest_dimensions,
    }


def asdict_weakness(weakness_obj) -> Dict:
    """Convert PromptWeakness to dict."""
    return {
        "weakness_type": weakness_obj.weakness_type,
        "num_affected_cases": len(weakness_obj.affected_cases),
        "avg_impact": weakness_obj.avg_impact,
        "affected_cases": weakness_obj.affected_cases[:5],  # First 5
    }
