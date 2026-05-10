"""
Tests for prompt optimization loop.
"""

import pytest
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from backend.evaluation.prompt_optimization import (
    ApprovalStatus,
    PromptRole,
    PromptVersion,
    PromptDiff,
    PromptDiffGenerator,
    PromptAnalyzer,
    MetaAgent,
    PromptOptimizationOrchestrator,
)
from backend.evaluation import (
    CaseCategory,
    EvaluationCase,
    EvaluationResult,
    DimensionScore,
    ScoringDimension,
)


class TestPromptVersion:
    """Test PromptVersion model."""
    
    def test_create_version(self):
        """Create a prompt version."""
        version = PromptVersion(
            role=PromptRole.DECOMPOSITION,
            version_number=1,
            content="Decompose the query into subquestions.",
        )
        
        assert version.role == PromptRole.DECOMPOSITION
        assert version.version_number == 1
        assert version.id
        assert version.created_at
    
    def test_version_to_dict(self):
        """Convert version to dict."""
        version = PromptVersion(
            role=PromptRole.RETRIEVAL_REASONING,
            version_number=2,
            content="Retrieve and reason over documents.",
        )
        
        v_dict = version.to_dict()
        assert v_dict["role"] == "retrieval_reasoning"
        assert v_dict["version_number"] == 2
        assert "created_at" in v_dict


class TestPromptDiff:
    """Test PromptDiff model."""
    
    def test_create_diff(self):
        """Create a diff."""
        diff = PromptDiff(
            role=PromptRole.DECOMPOSITION,
            from_version_num=1,
            to_version_num=2,
            original_content="Original prompt.",
            new_content="Updated prompt with improvements.",
        )
        
        assert diff.approval_status == ApprovalStatus.PENDING
        assert diff.from_version_num == 1
        assert diff.to_version_num == 2
    
    def test_diff_with_approval(self):
        """Diff can be approved."""
        diff = PromptDiff(
            role=PromptRole.SYNTHESIS,
            from_version_num=1,
            to_version_num=2,
            original_content="Old",
            new_content="New",
        )
        
        # Initially pending
        assert diff.approval_status == ApprovalStatus.PENDING
        assert diff.approved_by is None
        
        # Approve it
        diff.approval_status = ApprovalStatus.APPROVED
        diff.approved_by = "alice@example.com"
        diff.approval_notes = "Looks good"
        
        assert diff.approval_status == ApprovalStatus.APPROVED
        assert diff.approved_by == "alice@example.com"


class TestPromptDiffGenerator:
    """Test diff generation."""
    
    def test_generate_diff(self):
        """Generate a diff between two versions."""
        v1 = PromptVersion(
            role=PromptRole.DECOMPOSITION,
            version_number=1,
            content="Step 1: Analyze\nStep 2: Plan\nStep 3: Execute",
        )
        
        v2 = PromptVersion(
            role=PromptRole.DECOMPOSITION,
            version_number=2,
            content="Step 1: Analyze the query\nStep 2: Plan approach\nStep 3: Execute plan\nStep 4: Verify",
        )
        
        gen = PromptDiffGenerator()
        diff = gen.generate_diff(v1, v2)
        
        assert diff.from_version_num == 1
        assert diff.to_version_num == 2
        assert diff.role == PromptRole.DECOMPOSITION
        assert len(diff.diff_lines) > 0


class TestPromptAnalyzer:
    """Test result analysis."""
    
    def _create_test_result(
        self,
        case_id: str,
        category: CaseCategory,
        overall_score: float,
    ) -> EvaluationResult:
        """Helper to create test results."""
        result = EvaluationResult(
            case_id=case_id,
            case_category=category,
            prompt=f"Test case {case_id}",
            overall_score=overall_score,
        )
        
        # Add dimension scores
        result.dimension_scores["correctness"] = DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            numeric_score=overall_score * 0.9,
            justification="Test",
        )
        
        return result
    
    def test_identify_weakest_role(self):
        """Identify role with lowest scores."""
        results = [
            # Baseline cases (high score)
            self._create_test_result("case_1", CaseCategory.BASELINE, 0.8),
            self._create_test_result("case_2", CaseCategory.BASELINE, 0.85),
            
            # Ambiguous cases (low score)
            self._create_test_result("case_3", CaseCategory.AMBIGUOUS, 0.3),
            self._create_test_result("case_4", CaseCategory.AMBIGUOUS, 0.25),
            
            # Adversarial cases (medium score)
            self._create_test_result("case_5", CaseCategory.ADVERSARIAL, 0.5),
        ]
        
        analyzer = PromptAnalyzer()
        weakest_role, avg_score = analyzer.identify_weakest_role(results)
        
        assert weakest_role == PromptRole.RETRIEVAL_REASONING
        assert avg_score < 0.3
    
    def test_identify_failing_cases(self):
        """Identify cases below threshold."""
        results = [
            self._create_test_result("case_1", CaseCategory.BASELINE, 0.6),
            self._create_test_result("case_2", CaseCategory.BASELINE, 0.3),
            self._create_test_result("case_3", CaseCategory.BASELINE, 0.2),
        ]
        
        analyzer = PromptAnalyzer()
        failing = analyzer.identify_failing_cases(results, threshold=0.5)
        
        assert len(failing) == 2
        assert all(r.overall_score < 0.5 for r in failing)


class TestPromptOptimizationOrchestrator:
    """Test the orchestrator."""
    
    def _create_test_result(self, score: float, category: CaseCategory = CaseCategory.BASELINE) -> EvaluationResult:
        """Helper."""
        result = EvaluationResult(
            case_id=f"case_{uuid4()}",
            case_category=category,
            overall_score=score,
        )
        result.dimension_scores["correctness"] = DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            numeric_score=score * 0.8,
            justification="Test",
        )
        return result
    
    def test_register_prompt_version(self, tmp_path):
        """Register a prompt version."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        version = PromptVersion(
            role=PromptRole.DECOMPOSITION,
            version_number=1,
            content="Decompose queries.",
        )
        
        orch.register_prompt_version(version)
        
        assert len(orch.prompt_versions[PromptRole.DECOMPOSITION]) == 1
    
    def test_approval_workflow_mandatory(self, tmp_path):
        """Test mandatory human approval - cannot apply without approval."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        # Create and register versions
        v1 = PromptVersion(role=PromptRole.DECOMPOSITION, version_number=1, content="V1")
        orch.register_prompt_version(v1)
        
        # Create a diff (starts in PENDING state)
        diff = PromptDiff(
            role=PromptRole.DECOMPOSITION,
            from_version_num=1,
            to_version_num=2,
            original_content="V1",
            new_content="V2 with improvements",
        )
        orch.diffs.append(diff)
        
        # CRITICAL TEST: Try to apply without approval - should fail
        with pytest.raises(ValueError, match="APPROVED"):
            orch.apply_approved_diff(diff.id)
    
    def test_approval_before_application(self, tmp_path):
        """Test that approval must come before application."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        # Register initial version
        v1 = PromptVersion(
            role=PromptRole.DECOMPOSITION,
            version_number=1,
            content="Original",
            is_active=True,
        )
        orch.register_prompt_version(v1)
        
        # Create and approve a diff
        diff = PromptDiff(
            role=PromptRole.DECOMPOSITION,
            from_version_num=1,
            to_version_num=2,
            original_content="Original",
            new_content="Improved",
        )
        orch.diffs.append(diff)
        
        # Approve it
        orch.approve_diff(diff.id, approved_by="alice@example.com")
        
        # Now we can apply it
        new_version, applied_diff = orch.apply_approved_diff(diff.id)
        
        assert new_version.version_number == 2
        assert applied_diff.approval_status == ApprovalStatus.APPLIED
    
    def test_rejection_workflow(self, tmp_path):
        """Test rejection option."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        # Create a diff
        diff = PromptDiff(
            role=PromptRole.SYNTHESIS,
            from_version_num=1,
            to_version_num=2,
            original_content="V1",
            new_content="V2",
        )
        orch.diffs.append(diff)
        
        # Human rejects
        rejected = orch.reject_diff(
            diff.id,
            rejected_by="bob@example.com",
            rejection_reason="Too aggressive changes",
        )
        
        assert rejected.approval_status == ApprovalStatus.REJECTED
    
    def test_get_pending_approvals(self, tmp_path):
        """Get list of diffs awaiting approval."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        # Create multiple diffs
        for i in range(3):
            diff = PromptDiff(
                role=PromptRole.DECOMPOSITION,
                from_version_num=1,
                to_version_num=2,
                original_content="V1",
                new_content=f"V2_{i}",
            )
            orch.diffs.append(diff)
        
        pending = orch.get_pending_approvals()
        assert len(pending) == 3
        
        # Approve one
        orch.approve_diff(pending[0].id, approved_by="alice@example.com")
        
        # Should only have 2 pending now
        pending = orch.get_pending_approvals()
        assert len(pending) == 2


class TestIntegration:
    """Integration tests."""
    
    def _create_result(self, score: float, category: CaseCategory) -> EvaluationResult:
        """Helper."""
        r = EvaluationResult(
            case_id=f"case_{uuid4()}",
            case_category=category,
            overall_score=score,
        )
        r.dimension_scores["correctness"] = DimensionScore(
            dimension=ScoringDimension.CORRECTNESS,
            numeric_score=score * 0.8,
            justification="Test",
        )
        return r
    
    def test_full_optimization_workflow(self, tmp_path):
        """Full workflow with mandatory human approval at each step."""
        orch = PromptOptimizationOrchestrator(output_dir=tmp_path)
        
        # Step 1: Register initial versions
        v1_ret = PromptVersion(
            role=PromptRole.RETRIEVAL_REASONING,
            version_number=1,
            content="Retrieve and reason",
        )
        orch.register_prompt_version(v1_ret)
        
        # Step 2: Analyze failed evaluations
        results = [
            self._create_result(0.9, CaseCategory.BASELINE),
            self._create_result(0.2, CaseCategory.AMBIGUOUS),  # Failed
            self._create_result(0.25, CaseCategory.AMBIGUOUS),  # Failed
            self._create_result(0.5, CaseCategory.ADVERSARIAL),
        ]
        
        diffs = orch.analyze_results_and_propose(results)
        assert len(diffs) > 0
        
        proposed_diff = diffs[0]
        assert proposed_diff.approval_status == ApprovalStatus.PENDING
        
        # Step 3: MANDATORY human review and approval
        approved = orch.approve_diff(
            proposed_diff.id,
            approved_by="alice@example.com",
            approval_notes="Approved after review",
        )
        assert approved.approval_status == ApprovalStatus.APPROVED
        
        # Step 4: Only after approval can we apply
        new_version, applied_diff = orch.apply_approved_diff(proposed_diff.id)
        assert applied_diff.approval_status == ApprovalStatus.APPLIED
        
        # Step 5: Record re-evaluation to track delta
        reeval_results = [
            self._create_result(0.95, CaseCategory.BASELINE),
            self._create_result(0.5, CaseCategory.AMBIGUOUS),  # Improved
            self._create_result(0.55, CaseCategory.AMBIGUOUS),  # Improved
            self._create_result(0.60, CaseCategory.ADVERSARIAL),
        ]
        
        final_diff = orch.record_reeval_results(proposed_diff.id, reeval_results)
        assert final_diff.actual_overall_delta is not None
