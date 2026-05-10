"""
Tests for the evaluation harness.
"""

import pytest
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from backend.evaluation import (
    CaseCategory,
    DimensionScore,
    DimensionScorer,
    EvaluationCase,
    EvaluationHarness,
    EvaluationResult,
    ScoringDimension,
    create_baseline_cases,
    create_ambiguous_cases,
    create_adversarial_cases,
)
from backend.schemas import ContextMetadata, SharedContext


class TestEvaluationCase:
    """Test EvaluationCase model."""
    
    def test_baseline_case_creation(self):
        """Create a baseline case."""
        case = EvaluationCase(
            category=CaseCategory.BASELINE,
            prompt="What is the capital of France?",
            expected_correctness="Paris",
        )
        
        assert case.category == CaseCategory.BASELINE
        assert case.prompt == "What is the capital of France?"
        assert case.expected_correctness == "Paris"
        assert case.id  # Should have auto-generated ID
    
    def test_case_with_constraints(self):
        """Create case with constraints."""
        case = EvaluationCase(
            category=CaseCategory.AMBIGUOUS,
            prompt="Analyze the issue",
            constraints_to_check=["constraint_1", "constraint_2"],
        )
        
        assert case.category == CaseCategory.AMBIGUOUS
        assert len(case.constraints_to_check) == 2
    
    def test_case_to_dict(self):
        """Convert case to dict."""
        case = EvaluationCase(
            id="test_001",
            category=CaseCategory.ADVERSARIAL,
            prompt="Test prompt",
            adversarial_goal="Test goal",
        )
        
        case_dict = case.to_dict()
        assert case_dict["id"] == "test_001"
        assert case_dict["category"] == "adversarial"
        assert case_dict["prompt"] == "Test prompt"
        assert case_dict["adversarial_goal"] == "Test goal"


class TestDimensionScorer:
    """Test scoring logic."""
    
    def test_score_correctness_exact_match(self):
        """Score correctness with exact match."""
        scorer = DimensionScorer()
        
        score = scorer.score_correctness(
            prompt="What is X?",
            agent_output={"final_answer": "X is the answer"},
            expected_answer="X is the answer",
        )
        
        assert score.dimension == ScoringDimension.CORRECTNESS
        assert score.numeric_score > 0.5
        assert "Match rate" in score.justification
    
    def test_score_correctness_partial_match(self):
        """Score correctness with partial overlap."""
        scorer = DimensionScorer()
        
        score = scorer.score_correctness(
            prompt="What is X?",
            agent_output={"final_answer": "X is known to be something"},
            expected_answer="X is the specific thing",
        )
        
        assert score.dimension == ScoringDimension.CORRECTNESS
        assert 0 <= score.numeric_score <= 1.0
    
    def test_score_citation_accuracy_with_citations(self):
        """Score citation accuracy when citations present."""
        scorer = DimensionScorer()
        
        score = scorer.score_citation_accuracy(
            agent_output={
                "claims": [
                    {"text": "claim 1", "citations": ["source1"]},
                    {"text": "claim 2", "citations": ["source2"]},
                ]
            },
            expected_citations=[
                {"claim": "claim 1", "source": "source1"},
            ],
        )
        
        assert score.dimension == ScoringDimension.CITATION_ACCURACY
        assert score.numeric_score > 0.5
    
    def test_score_citation_accuracy_no_citations_expected(self):
        """Score citation accuracy when no citations expected."""
        scorer = DimensionScorer()
        
        score = scorer.score_citation_accuracy(
            agent_output={"claims": []},
            expected_citations=[],
        )
        
        assert score.numeric_score == 1.0
    
    def test_score_contradiction_resolution(self):
        """Score contradiction resolution."""
        scorer = DimensionScorer()
        
        score = scorer.score_contradiction_resolution(
            agent_output={
                "rejected_claims": ["claim_id_1"],
                "conflict_resolution_log": ["conflict_1"],
            },
            expected_contradictions=["contradiction_1"],
        )
        
        assert score.dimension == ScoringDimension.CONTRADICTION_RESOLUTION
        assert score.numeric_score > 0.5
    
    def test_score_tool_efficiency_optimal(self):
        """Score tool efficiency with optimal call count."""
        scorer = DimensionScorer()
        
        # Mock execution trace
        from backend.schemas import ExecutionTrace, ExecutionStep
        from backend.schemas.execution import ExecutionStepType
        
        trace = ExecutionTrace(
            id=uuid4(),
            conversation_id=uuid4(),
            agent_id="test_agent",
            total_duration_ms=100.0,
        )
        trace.steps = [
            ExecutionStep(step_type=ExecutionStepType.TOOL_CALL),
            ExecutionStep(step_type=ExecutionStepType.TOOL_CALL),
            ExecutionStep(step_type=ExecutionStepType.TOOL_CALL),
        ]
        
        score = scorer.score_tool_efficiency(trace)
        
        assert score.dimension == ScoringDimension.TOOL_EFFICIENCY
        assert score.numeric_score == 1.0  # 3 calls is in optimal range
    
    def test_score_context_compliance_with_context(self):
        """Score context compliance."""
        scorer = DimensionScorer()
        
        context = SharedContext(
            conversation_id=uuid4(),
            user_intent="test",
            facts={"constraint_keyword": "value"},
            metadata=ContextMetadata(last_modified_by="test"),
        )
        
        score = scorer.score_context_compliance(
            context=context,
            agent_output={"answer": "Uses the constraint_keyword"},
            constraints_to_check=["constraint_keyword"],
        )
        
        assert score.dimension == ScoringDimension.CONTEXT_COMPLIANCE
        assert score.numeric_score > 0.5


class TestEvaluationResult:
    """Test EvaluationResult model."""
    
    def test_create_result(self):
        """Create an evaluation result."""
        result = EvaluationResult(
            case_id="test_case_001",
            case_category=CaseCategory.BASELINE,
            prompt="Test",
            overall_score=0.85,
        )
        
        assert result.case_id == "test_case_001"
        assert result.overall_score == 0.85
        assert result.timestamp  # Auto-generated
    
    def test_result_with_dimension_scores(self):
        """Add dimension scores to result."""
        result = EvaluationResult(
            case_id="test_001",
            case_category=CaseCategory.BASELINE,
        )
        
        score = DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            numeric_score=0.9,
            justification="Good match",
        )
        
        result.dimension_scores["correctness"] = score
        
        assert len(result.dimension_scores) == 1
        assert result.get_score(ScoringDimension.CORRECTNESS) is not None
    
    def test_result_to_dict(self):
        """Convert result to JSON-serializable dict."""
        result = EvaluationResult(
            case_id="test_001",
            case_category=CaseCategory.BASELINE,
            prompt="Test prompt",
            overall_score=0.75,
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["case_id"] == "test_001"
        assert result_dict["overall_score"] == 0.75
        assert result_dict["timestamp"]  # Should be ISO format string


class TestEvaluationHarness:
    """Test the main harness."""
    
    def test_harness_creation(self, tmp_path):
        """Create a harness."""
        harness = EvaluationHarness(output_dir=tmp_path)
        
        assert harness.output_dir == tmp_path
        assert harness.run_id
        assert len(harness.results) == 0
    
    def test_evaluate_case(self, tmp_path):
        """Evaluate a single case."""
        harness = EvaluationHarness(output_dir=tmp_path)
        
        case = EvaluationCase(
            id="test_001",
            category=CaseCategory.BASELINE,
            prompt="What is 2+2?",
            expected_correctness="2+2 equals 4",
        )
        
        result = harness.evaluate_case(
            case=case,
            agent_outputs={"final_answer": "2 plus 2 is 4"},
        )
        
        assert result.case_id == "test_001"
        assert result.overall_score >= 0.0 and result.overall_score <= 1.0
        assert len(result.dimension_scores) == 6  # All 6 dimensions scored
        assert len(harness.results) == 1
    
    def test_evaluate_multiple_cases(self, tmp_path):
        """Evaluate multiple cases."""
        harness = EvaluationHarness(output_dir=tmp_path)
        
        for i in range(3):
            case = EvaluationCase(
                id=f"case_{i}",
                category=CaseCategory.BASELINE,
                prompt=f"Question {i}",
            )
            harness.evaluate_case(case, agent_outputs={})
        
        assert len(harness.results) == 3
    
    def test_save_results(self, tmp_path):
        """Save evaluation results."""
        harness = EvaluationHarness(output_dir=tmp_path)
        
        case = EvaluationCase(
            id="test_001",
            category=CaseCategory.BASELINE,
            prompt="Test",
        )
        
        harness.evaluate_case(case, agent_outputs={})
        results_file = harness.save_results()
        
        assert results_file.exists()
        assert results_file.suffix == ".json"
        
        # Verify JSON is readable
        import json
        with open(results_file) as f:
            data = json.load(f)
        
        assert "run_id" in data
        assert "results" in data
        assert len(data["results"]) == 1
    
    def test_load_previous_run(self, tmp_path):
        """Load a previous run."""
        harness1 = EvaluationHarness(output_dir=tmp_path)
        
        case = EvaluationCase(id="test", category=CaseCategory.BASELINE)
        harness1.evaluate_case(case, agent_outputs={})
        results_file = harness1.save_results()
        
        # Create new harness and load previous
        harness2 = EvaluationHarness(output_dir=tmp_path)
        loaded = harness2.load_previous_run(harness1.run_id)
        
        assert loaded is not None
        assert loaded["run_id"] == harness1.run_id
    
    def test_compare_runs(self, tmp_path):
        """Compare two runs."""
        # Run 1
        harness1 = EvaluationHarness(output_dir=tmp_path)
        case1 = EvaluationCase(id="test", category=CaseCategory.BASELINE)
        harness1.evaluate_case(case1, agent_outputs={})
        file1 = harness1.save_results()
        run1_id = harness1.run_id
        
        # Run 2
        harness2 = EvaluationHarness(output_dir=tmp_path)
        case2 = EvaluationCase(id="test", category=CaseCategory.BASELINE)
        result = harness2.evaluate_case(case2, agent_outputs={"final_answer": "better output"})
        file2 = harness2.save_results()
        run2_id = harness2.run_id
        
        # Compare
        harness3 = EvaluationHarness(output_dir=tmp_path)
        diffs = harness3.compare_runs(run1_id, run2_id)
        
        assert "run_1_id" in diffs
        assert "run_2_id" in diffs
        assert "case_diffs" in diffs
        assert "dimension_trend" in diffs


class TestTestCaseGeneration:
    """Test test case generators."""
    
    def test_baseline_cases(self):
        """Generate baseline cases."""
        cases = create_baseline_cases()
        
        assert len(cases) == 5
        assert all(c.category == CaseCategory.BASELINE for c in cases)
        assert all(c.expected_correctness for c in cases)
    
    def test_ambiguous_cases(self):
        """Generate ambiguous cases."""
        cases = create_ambiguous_cases()
        
        assert len(cases) == 5
        assert all(c.category == CaseCategory.AMBIGUOUS for c in cases)
        # Ambiguous cases should have some contradictions
        assert any(len(c.expected_contradictions) > 0 for c in cases)
    
    def test_adversarial_cases(self):
        """Generate adversarial cases."""
        cases = create_adversarial_cases()
        
        assert len(cases) == 5
        assert all(c.category == CaseCategory.ADVERSARIAL for c in cases)
        # Adversarial cases should have goals
        assert all(c.adversarial_goal for c in cases)
    
    def test_all_cases_have_unique_ids(self):
        """All test cases should have unique IDs."""
        baseline = create_baseline_cases()
        ambiguous = create_ambiguous_cases()
        adversarial = create_adversarial_cases()
        
        all_cases = baseline + ambiguous + adversarial
        ids = [c.id for c in all_cases]
        
        assert len(ids) == len(set(ids))  # All unique
    
    def test_all_cases_have_prompts(self):
        """All test cases should have prompts."""
        baseline = create_baseline_cases()
        ambiguous = create_ambiguous_cases()
        adversarial = create_adversarial_cases()
        
        all_cases = baseline + ambiguous + adversarial
        
        assert all(c.prompt for c in all_cases)


class TestIntegration:
    """Integration tests."""
    
    def test_full_evaluation_workflow(self, tmp_path):
        """Full workflow: create cases, evaluate, save, compare."""
        # First run
        harness1 = EvaluationHarness(output_dir=tmp_path)
        cases1 = create_baseline_cases()[:2]  # Use 2 baseline cases
        
        for case in cases1:
            harness1.evaluate_case(
                case,
                agent_outputs={"final_answer": "Initial response"},
            )
        
        file1 = harness1.save_results()
        run1_id = harness1.run_id
        
        assert file1.exists()
        assert len(harness1.results) == 2
        
        # Second run with "improved" outputs
        harness2 = EvaluationHarness(output_dir=tmp_path)
        cases2 = create_baseline_cases()[:2]
        
        for case in cases2:
            harness2.evaluate_case(
                case,
                agent_outputs={"final_answer": case.expected_correctness},  # Perfect match
            )
        
        file2 = harness2.save_results()
        run2_id = harness2.run_id
        
        # Verify improvement
        avg1 = sum(r.overall_score for r in harness1.results) / len(harness1.results)
        avg2 = sum(r.overall_score for r in harness2.results) / len(harness2.results)
        
        assert avg2 > avg1  # Second run should score higher
        
        # Compare runs
        harness3 = EvaluationHarness(output_dir=tmp_path)
        diffs = harness3.compare_runs(run1_id, run2_id)
        
        assert diffs["run_1_id"] == run1_id
        assert diffs["run_2_id"] == run2_id
        assert len(diffs["case_diffs"]) == 2
