"""
Evaluation runner: executes evaluation harness with test cases.

This module runs a complete evaluation, scoring all test cases across
multidimensional criteria and producing reproducible, traceable results.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time

from backend.evaluation import (
    CaseCategory,
    EvaluationCase,
    EvaluationHarness,
    EvaluationResult,
    create_baseline_cases,
    create_ambiguous_cases,
    create_adversarial_cases,
)


class EvaluationRunner:
    """Run evaluation harness against test cases."""
    
    def __init__(self, output_dir: Path = Path("evaluation_runs")):
        self.output_dir = Path(output_dir)
        self.harness = EvaluationHarness(output_dir=self.output_dir)
    
    def get_all_test_cases(self) -> Dict[CaseCategory, List[EvaluationCase]]:
        """Load all test cases."""
        return {
            CaseCategory.BASELINE: create_baseline_cases(),
            CaseCategory.AMBIGUOUS: create_ambiguous_cases(),
            CaseCategory.ADVERSARIAL: create_adversarial_cases(),
        }
    
    def run_full_evaluation(
        self,
        agent_executor=None,
        verbose: bool = True,
    ) -> Tuple[Path, Dict[str, float]]:
        """
        Run full evaluation on all 15 test cases.
        
        Args:
            agent_executor: Async callable that takes (prompt, context) and returns (trace, outputs)
            verbose: Print progress
        
        Returns:
            (results_file, summary_stats)
        """
        if verbose:
            print(f"🔍 Starting evaluation harness at {datetime.utcnow().isoformat()}")
        
        test_cases = self.get_all_test_cases()
        total_cases = sum(len(cases) for cases in test_cases.values())
        
        if verbose:
            print(f"📋 Loaded {total_cases} test cases:")
            for cat, cases in test_cases.items():
                print(f"   {cat.value}: {len(cases)} cases")
        
        # Default mock executor if none provided
        if agent_executor is None:
            agent_executor = self._mock_executor
        
        # Run evaluation on each case
        results_count = 0
        for category, cases in test_cases.items():
            if verbose:
                print(f"\n🎯 Evaluating {category.value} cases...")
            
            for case in cases:
                try:
                    if verbose:
                        print(f"  ├─ {case.id}: {case.prompt[:60]}...")
                    
                    start_time = time.time()
                    
                    # Execute the agent (or mock)
                    trace, outputs = agent_executor(case.prompt, case.context)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Evaluate the result
                    result = self.harness.evaluate_case(
                        case=case,
                        execution_trace=trace,
                        agent_outputs=outputs or {},
                        duration_ms=duration_ms,
                    )
                    
                    if verbose:
                        print(f"     Score: {result.overall_score:.2f} ({result.case_id})")
                    
                    results_count += 1
                    
                except Exception as e:
                    if verbose:
                        print(f"     ⚠️  Error: {str(e)}")
        
        # Save results
        results_file = self.harness.save_results()
        if verbose:
            print(f"\n✅ Evaluation complete. Results saved to {results_file}")
        
        # Compute summary
        summary = self._compute_summary()
        if verbose:
            self._print_summary(summary)
        
        return results_file, summary
    
    def run_category_evaluation(
        self,
        category: CaseCategory,
        agent_executor=None,
        verbose: bool = True,
    ) -> Tuple[Path, Dict[str, float]]:
        """Run evaluation on a single category."""
        test_cases = self.get_all_test_cases()
        cases = test_cases.get(category, [])
        
        if verbose:
            print(f"🔍 Starting {category.value} evaluation")
            print(f"📋 Loaded {len(cases)} test cases")
        
        if agent_executor is None:
            agent_executor = self._mock_executor
        
        for case in cases:
            try:
                if verbose:
                    print(f"  ├─ {case.id}: {case.prompt[:60]}...")
                
                start_time = time.time()
                trace, outputs = agent_executor(case.prompt, case.context)
                duration_ms = (time.time() - start_time) * 1000
                
                result = self.harness.evaluate_case(
                    case=case,
                    execution_trace=trace,
                    agent_outputs=outputs or {},
                    duration_ms=duration_ms,
                )
                
                if verbose:
                    print(f"     Score: {result.overall_score:.2f}")
                
            except Exception as e:
                if verbose:
                    print(f"     ⚠️  Error: {str(e)}")
        
        results_file = self.harness.save_results()
        summary = self._compute_summary()
        
        if verbose:
            print(f"✅ {category.value} evaluation complete")
            self._print_summary(summary)
        
        return results_file, summary
    
    def compare_to_previous(self, previous_run_id: str, verbose: bool = True) -> Dict:
        """Compare current run to a previous one."""
        diffs = self.harness.compare_runs(previous_run_id, self.harness.run_id)
        
        if verbose:
            self._print_comparison(diffs)
        
        return diffs
    
    def _compute_summary(self) -> Dict[str, float]:
        """Compute summary statistics."""
        if not self.harness.results:
            return {}
        
        results = self.harness.results
        summary = {
            "total_cases": len(results),
            "average_overall_score": sum(r.overall_score for r in results) / len(results),
            "min_score": min(r.overall_score for r in results),
            "max_score": max(r.overall_score for r in results),
        }
        
        # By category
        for cat in CaseCategory:
            cat_results = [r for r in results if r.case_category == cat]
            if cat_results:
                summary[f"{cat.value}_avg"] = sum(r.overall_score for r in cat_results) / len(cat_results)
                summary[f"{cat.value}_count"] = len(cat_results)
        
        # By dimension
        for result in results:
            for dim_val, score in result.dimension_scores.items():
                key = f"avg_{dim_val}"
                if key not in summary:
                    summary[key] = 0.0
        
        if results:
            for dim_val in results[0].dimension_scores.keys():
                key = f"avg_{dim_val}"
                scores = [r.dimension_scores[dim_val].numeric_score for r in results if dim_val in r.dimension_scores]
                if scores:
                    summary[key] = sum(scores) / len(scores)
        
        return summary
    
    def _print_summary(self, summary: Dict[str, float]) -> None:
        """Print summary statistics."""
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        
        print(f"Total cases: {int(summary.get('total_cases', 0))}")
        print(f"Average overall score: {summary.get('average_overall_score', 0):.3f}")
        print(f"Score range: {summary.get('min_score', 0):.3f} - {summary.get('max_score', 0):.3f}")
        
        print("\nBy Category:")
        for cat in CaseCategory:
            avg_key = f"{cat.value}_avg"
            count_key = f"{cat.value}_count"
            if avg_key in summary and count_key in summary:
                print(f"  {cat.value:12s}: {summary[avg_key]:.3f} ({int(summary[count_key])} cases)")
        
        print("\nBy Dimension:")
        for key in sorted(summary.keys()):
            if key.startswith("avg_") and not key.startswith("avg_baseline") and not key.startswith("avg_ambiguous") and not key.startswith("avg_adversarial"):
                dim_name = key[4:]  # Remove "avg_" prefix
                print(f"  {dim_name:25s}: {summary[key]:.3f}")
        
        print("=" * 60 + "\n")
    
    def _print_comparison(self, diffs: Dict) -> None:
        """Print comparison between runs."""
        if "error" in diffs:
            print(f"⚠️  Comparison error: {diffs['error']}")
            return
        
        print("\n" + "=" * 60)
        print("RUN COMPARISON")
        print("=" * 60)
        
        print(f"Run 1: {diffs['run_1_id'][:8]}...")
        print(f"Run 2: {diffs['run_2_id'][:8]}...")
        
        print("\nCase Score Changes:")
        case_diffs = sorted(diffs['case_diffs'], key=lambda x: x['delta'], reverse=True)
        
        for case_diff in case_diffs[:10]:  # Show top 10
            delta = case_diff['delta']
            symbol = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            print(f"  {symbol} {case_diff['case_id']}: {delta:+.3f} ({case_diff['run1_overall']:.3f} → {case_diff['run2_overall']:.3f})")
        
        print("\nDimension Trends:")
        for dim_val in sorted(diffs['dimension_trend'].keys()):
            trend = diffs['dimension_trend'][dim_val]
            delta = trend['delta']
            symbol = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
            print(f"  {symbol} {dim_val:25s}: {delta:+.3f} ({trend['run1_avg']:.3f} → {trend['run2_avg']:.3f})")
        
        print("=" * 60 + "\n")
    
    def _mock_executor(self, prompt: str, context) -> Tuple[None, Dict]:
        """Mock executor for testing (no actual agent execution)."""
        # Returns mock outputs for demonstration
        return None, {
            "final_answer": f"Mock response to: {prompt[:50]}",
            "confidence": 0.7,
            "claims": [
                {"text": "Claim 1", "citations": ["source1"]},
            ],
            "rejected_claims": [],
            "tool_calls": 2,
        }


def main():
    """Run full evaluation."""
    import sys
    
    runner = EvaluationRunner()
    
    # Parse command line args
    category = None
    compare_to = None
    
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--category":
            category = sys.argv[i + 2]
        elif arg == "--compare":
            compare_to = sys.argv[i + 2]
    
    # Run evaluation
    if category:
        try:
            cat = CaseCategory(category)
            results_file, summary = runner.run_category_evaluation(cat)
        except ValueError:
            print(f"Unknown category: {category}")
            print(f"Available: {', '.join(c.value for c in CaseCategory)}")
            return
    else:
        results_file, summary = runner.run_full_evaluation()
    
    # Compare if requested
    if compare_to:
        runner.compare_to_previous(compare_to)


if __name__ == "__main__":
    main()
