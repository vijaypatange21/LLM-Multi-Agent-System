"""
Tests for production API endpoints and schemas.
"""

import pytest
from uuid import uuid4
from datetime import datetime

from backend.api.schemas import (
    ErrorResponse,
    QueryRequest,
    QueryResponse,
    ExecutionTraceResponse,
    TraceMetadata,
    EvalSummaryResponse,
    EvaluationMetrics,
    EvaluationCase,
    ApprovalDecision,
    PromptApprovalRequest,
    PromptApprovalResponse,
    TargetedReEvalRequest,
    TargetedReEvalResponse,
    ReEvalCase,
    HealthResponse,
)


class TestQueryRequest:
    """Test query request validation."""
    
    def test_create_valid_query(self):
        """Create a valid query request."""
        req = QueryRequest(
            query="What is climate change?",
            budget_tokens=5000,
            timeout_seconds=60,
        )
        
        assert req.query == "What is climate change?"
        assert req.budget_tokens == 5000
        assert req.timeout_seconds == 60
    
    def test_query_with_conversation_id(self):
        """Query with existing conversation ID."""
        conv_id = uuid4()
        
        req = QueryRequest(
            query="Follow-up question",
            conversation_id=conv_id,
            budget_tokens=3000,
        )
        
        assert req.conversation_id == conv_id
    
    def test_query_budget_validation(self):
        """Query with budget below minimum should fail."""
        with pytest.raises(ValueError):
            QueryRequest(
                query="Test",
                budget_tokens=50,  # Below minimum of 100
            )
    
    def test_query_empty_validation(self):
        """Empty query should fail."""
        with pytest.raises(ValueError):
            QueryRequest(
                query="   ",  # Whitespace only
                budget_tokens=1000,
            )
    
    def test_query_max_length(self):
        """Query exceeding max length should fail."""
        with pytest.raises(ValueError):
            QueryRequest(
                query="x" * 10001,
                budget_tokens=1000,
            )
    
    def test_query_timeout_validation(self):
        """Timeout outside allowed range should fail."""
        with pytest.raises(ValueError):
            QueryRequest(
                query="Test",
                budget_tokens=1000,
                timeout_seconds=1000,  # Max is 600
            )


class TestQueryResponse:
    """Test query response model."""
    
    def test_create_query_response(self):
        """Create query response."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        resp = QueryResponse(
            trace_id=trace_id,
            conversation_id=conv_id,
            status="started",
        )
        
        assert resp.trace_id == trace_id
        assert resp.conversation_id == conv_id
        assert resp.status == "started"
    
    def test_response_serialization(self):
        """Response serializes to JSON."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        resp = QueryResponse(
            trace_id=trace_id,
            conversation_id=conv_id,
        )
        
        data = resp.model_dump()
        assert "trace_id" in data
        assert "conversation_id" in data
        assert "created_at" in data


class TestExecutionTrace:
    """Test execution trace response model."""
    
    def test_create_trace_response(self):
        """Create execution trace response."""
        trace_id = uuid4()
        conv_id = uuid4()
        
        metadata = TraceMetadata(
            step_count=7,
            total_duration_ms=3450.0,
            status="completed",
            agent_id="orchestrator",
        )
        
        resp = ExecutionTraceResponse(
            trace_id=trace_id,
            conversation_id=conv_id,
            metadata=metadata,
        )
        
        assert resp.trace_id == trace_id
        assert resp.metadata.step_count == 7
    
    def test_trace_with_steps(self):
        """Trace response with execution steps."""
        trace_id = uuid4()
        
        resp = ExecutionTraceResponse(
            trace_id=trace_id,
            conversation_id=uuid4(),
            metadata=TraceMetadata(
                step_count=3,
                total_duration_ms=1500.0,
                status="completed",
                agent_id="test_agent",
            ),
            steps_summary=[
                {"step_number": 1, "type": "planning", "duration_ms": 100},
                {"step_number": 2, "type": "execution", "duration_ms": 1000},
                {"step_number": 3, "type": "synthesis", "duration_ms": 400},
            ],
        )
        
        assert len(resp.steps_summary) == 3
        assert resp.metadata.step_count == 3


class TestEvaluationMetrics:
    """Test evaluation metrics model."""
    
    def test_create_metrics(self):
        """Create evaluation metrics."""
        metrics = EvaluationMetrics(
            correctness=0.95,
            citation_accuracy=0.87,
            contradiction_resolution=0.92,
            tool_efficiency=0.88,
            context_compliance=0.90,
            critique_agreement=0.85,
        )
        
        assert metrics.correctness == 0.95
        assert 0.88 < metrics.overall_score < 0.90
    
    def test_metrics_boundary_values(self):
        """Metrics must be 0-1 range."""
        with pytest.raises(ValueError):
            EvaluationMetrics(
                correctness=1.5,  # Above max
                citation_accuracy=0.5,
                contradiction_resolution=0.5,
                tool_efficiency=0.5,
                context_compliance=0.5,
                critique_agreement=0.5,
            )
    
    def test_overall_score_calculation(self):
        """Overall score is average of all metrics."""
        metrics = EvaluationMetrics(
            correctness=1.0,
            citation_accuracy=0.8,
            contradiction_resolution=0.8,
            tool_efficiency=0.8,
            context_compliance=0.8,
            critique_agreement=0.8,
        )
        
        # Average of 1.0, 0.8, 0.8, 0.8, 0.8, 0.8 = 0.8667
        expected = (1.0 + 0.8 + 0.8 + 0.8 + 0.8 + 0.8) / 6
        assert metrics.overall_score == pytest.approx(expected, rel=0.01)


class TestEvalSummaryResponse:
    """Test evaluation summary response."""
    
    def test_create_eval_summary(self):
        """Create evaluation summary response."""
        resp = EvalSummaryResponse(
            eval_run_id=uuid4(),
            timestamp=datetime.now(),
            total_cases=100,
            baseline_cases=50,
            ambiguous_cases=30,
            adversarial_cases=20,
            average_metrics=EvaluationMetrics(
                correctness=0.85,
                citation_accuracy=0.80,
                contradiction_resolution=0.88,
                tool_efficiency=0.82,
                context_compliance=0.86,
                critique_agreement=0.81,
            ),
            duration_ms=5000.0,
        )
        
        assert resp.total_cases == 100
        assert resp.baseline_cases == 50
        assert resp.average_metrics.overall_score > 0
    
    def test_eval_summary_with_recommendations(self):
        """Eval summary can include recommendations."""
        resp = EvalSummaryResponse(
            eval_run_id=uuid4(),
            timestamp=datetime.now(),
            total_cases=50,
            baseline_cases=50,
            average_metrics=EvaluationMetrics(
                correctness=0.75,
                citation_accuracy=0.70,
                contradiction_resolution=0.80,
                tool_efficiency=0.75,
                context_compliance=0.78,
                critique_agreement=0.72,
            ),
            duration_ms=3000.0,
            recommendations=[
                "Improve citation accuracy in retrieval step",
                "Optimize tool selection for efficiency",
            ],
        )
        
        assert len(resp.recommendations) == 2


class TestLatestEvaluation:
    """Test latest evaluation response model."""
    
    def test_evaluation_response_structure(self):
        """Evaluation response has correct structure."""
        resp = EvalSummaryResponse(
            eval_run_id=uuid4(),
            timestamp=datetime.now(),
            total_cases=100,
            baseline_cases=50,
            ambiguous_cases=30,
            adversarial_cases=20,
            average_metrics=EvaluationMetrics(
                correctness=0.85,
                citation_accuracy=0.80,
                contradiction_resolution=0.88,
                tool_efficiency=0.82,
                context_compliance=0.86,
                critique_agreement=0.81,
            ),
            duration_ms=5000.0,
        )
        
        data = resp.model_dump()
        assert "eval_run_id" in data
        assert "timestamp" in data
        assert "total_cases" in data
        assert "average_metrics" in data
        
        metrics = data["average_metrics"]
        assert "correctness" in metrics
        assert "citation_accuracy" in metrics
        assert "overall_score" in metrics


class TestPromptApprovalRequest:
    """Test prompt approval request validation."""
    
    def test_create_approval_request(self):
        """Create a valid approval request."""
        req = PromptApprovalRequest(
            decision=ApprovalDecision.APPROVE,
            notes="Looks good",
            approved_by="alice@example.com",
        )
        
        assert req.decision == ApprovalDecision.APPROVE
        assert req.notes == "Looks good"
        assert req.approved_by == "alice@example.com"
    
    def test_rejection_request(self):
        """Create a rejection request."""
        req = PromptApprovalRequest(
            decision=ApprovalDecision.REJECT,
            notes="Breaks edge cases",
            approved_by="bob@example.com",
        )
        
        assert req.decision == ApprovalDecision.REJECT
    
    def test_approval_without_notes(self):
        """Approval without notes should work."""
        req = PromptApprovalRequest(
            decision=ApprovalDecision.APPROVE,
            approved_by="charlie@example.com",
        )
        
        assert req.approved_by == "charlie@example.com"
    
    def test_approval_without_approver_fails(self):
        """Missing approver should fail."""
        with pytest.raises(ValueError):
            PromptApprovalRequest(
                decision=ApprovalDecision.APPROVE,
                notes="OK",
                approved_by="   ",  # Whitespace only
            )
    
    def test_approval_notes_too_long(self):
        """Notes exceeding max length should fail."""
        with pytest.raises(ValueError):
            PromptApprovalRequest(
                decision=ApprovalDecision.APPROVE,
                notes="x" * 5001,
                approved_by="user@example.com",
            )


class TestPromptApprovalResponse:
    """Test prompt approval response model."""
    
    def test_create_approval_response(self):
        """Create approval response."""
        diff_id = uuid4()
        
        resp = PromptApprovalResponse(
            diff_id=diff_id,
            decision=ApprovalDecision.APPROVE,
            next_step="awaiting_application",
        )
        
        assert resp.diff_id == diff_id
        assert resp.decision == ApprovalDecision.APPROVE
    
    def test_rejection_response(self):
        """Create rejection response."""
        diff_id = uuid4()
        
        resp = PromptApprovalResponse(
            diff_id=diff_id,
            decision=ApprovalDecision.REJECT,
            next_step="archived_with_feedback",
        )
        
        assert resp.decision == ApprovalDecision.REJECT


class TestTargetedReEvalRequest:
    """Test targeted re-evaluation request validation."""
    
    def test_create_reeval_request(self):
        """Create targeted re-eval request."""
        req = TargetedReEvalRequest(
            prompt_version_ids=["v1.2.1", "v1.2.2"],
            test_categories=["baseline", "ambiguous"],
            timeout_seconds=180,
        )
        
        assert len(req.prompt_version_ids) == 2
        assert len(req.test_categories) == 2
    
    def test_reeval_with_focus_cases(self):
        """Re-eval with focus cases."""
        req = TargetedReEvalRequest(
            prompt_version_ids=["v1.2.1"],
            focus_cases=["ambiguous_1", "ambiguous_2"],
        )
        
        assert len(req.focus_cases) == 2
    
    def test_reeval_no_versions_fails(self):
        """No versions should fail."""
        with pytest.raises(ValueError):
            TargetedReEvalRequest(
                prompt_version_ids=[],
                test_categories=["baseline"],
            )
    
    def test_reeval_too_many_versions_fails(self):
        """Too many versions should fail."""
        with pytest.raises(ValueError):
            TargetedReEvalRequest(
                prompt_version_ids=["v1", "v2", "v3", "v4", "v5", "v6"],
            )
    
    def test_reeval_invalid_timeout_fails(self):
        """Invalid timeout should fail."""
        with pytest.raises(ValueError):
            TargetedReEvalRequest(
                prompt_version_ids=["v1"],
                timeout_seconds=10,  # Below minimum of 30
            )


class TestTargetedReEvalResponse:
    """Test targeted re-evaluation response model."""
    
    def test_create_reeval_response(self):
        """Create re-eval response."""
        resp = TargetedReEvalResponse(
            eval_id=uuid4(),
            status="started",
            prompt_versions_tested=2,
            total_cases=100,
        )
        
        assert resp.status == "started"
        assert resp.prompt_versions_tested == 2
    
    def test_reeval_response_with_results(self):
        """Re-eval response with results."""
        resp = TargetedReEvalResponse(
            eval_id=uuid4(),
            status="completed",
            prompt_versions_tested=1,
            total_cases=50,
            results=[
                ReEvalCase(
                    case_id="baseline_1",
                    old_score=0.85,
                    new_score=0.92,
                    improved=True,
                    delta=0.07,
                ),
                ReEvalCase(
                    case_id="baseline_2",
                    old_score=0.80,
                    new_score=0.78,
                    improved=False,
                    delta=-0.02,
                ),
            ],
        )
        
        assert len(resp.results) == 2
        assert resp.results[0].improved is True
        assert resp.results[1].improved is False


class TestHealthResponse:
    """Test health check response model."""
    
    def test_create_health_response(self):
        """Create health response."""
        resp = HealthResponse(
            status="healthy",
            components={
                "database": "ok",
                "cache": "ok",
                "queue": "ok",
            },
        )
        
        assert resp.status == "healthy"
        assert resp.components["database"] == "ok"
    
    def test_health_response_has_version(self):
        """Health response includes version."""
        resp = HealthResponse(
            status="healthy",
        )
        
        data = resp.model_dump()
        assert "timestamp" in data
        assert "version" in data


class TestPromptApproval:
    """Test prompt approval request/response models."""
    
    def test_approval_workflow(self):
        """Full approval workflow."""
        # Create request
        req = PromptApprovalRequest(
            decision=ApprovalDecision.APPROVE,
            notes="Looks good, ~8% improvement in ambiguous cases",
            approved_by="alice@example.com",
        )
        
        # Create response
        diff_id = uuid4()
        resp = PromptApprovalResponse(
            diff_id=diff_id,
            decision=req.decision,
            next_step="awaiting_application",
        )
        
        assert resp.decision == req.decision
        assert resp.next_step == "awaiting_application"


class TestTargetedReeval:
    """Test targeted re-evaluation request/response models."""
    
    def test_reeval_workflow(self):
        """Full re-eval workflow."""
        # Create request
        req = TargetedReEvalRequest(
            prompt_version_ids=["v1.2.1", "v1.2.2"],
            test_categories=["baseline", "ambiguous"],
            timeout_seconds=300,
        )
        
        # Create response
        resp = TargetedReEvalResponse(
            eval_id=uuid4(),
            status="completed",
            prompt_versions_tested=len(req.prompt_version_ids),
            total_cases=100,
            results=[
                ReEvalCase(
                    case_id="baseline_1",
                    old_score=0.85,
                    new_score=0.90,
                    improved=True,
                    delta=0.05,
                ),
            ],
        )
        
        assert resp.prompt_versions_tested == 2
        assert resp.results[0].improved is True


class TestErrorResponse:
    """Test error response model."""
    
    def test_create_error_response(self):
        """Create error response."""
        trace_id = uuid4()
        
        err = ErrorResponse(
            error="Query execution failed",
            error_code="EXECUTION_ERROR",
            trace_id=trace_id,
        )
        
        assert err.error == "Query execution failed"
        assert err.error_code == "EXECUTION_ERROR"
        assert err.trace_id == trace_id
    
    def test_error_with_details(self):
        """Error with detailed information."""
        err = ErrorResponse(
            error="Validation failed",
            error_code="INVALID_BUDGET",
            details={"budget": "Must be >= 100"},
        )
        
        assert "budget" in err.details
