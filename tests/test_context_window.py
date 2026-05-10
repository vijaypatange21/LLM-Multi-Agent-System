"""Tests for context window management."""

from uuid import uuid4

import pytest

from backend.orchestration.context_window import ContextWindowManager, StructuredDataPreservingSummarizer, TokenEstimator
from backend.schemas import AgentMessage, ContextMetadata, MessageRole, SharedContext


def _message(content: str) -> AgentMessage:
    return AgentMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        parent_message_id=None,
        trace_id=str(uuid4()),
        role=MessageRole.USER,
        content=content,
        agent_id="user",
        sequence_number=1,
    )


def _context() -> SharedContext:
    return SharedContext(
        conversation_id=uuid4(),
        user_intent="please summarize the latest findings and keep the structured data intact",
        facts={
            "agent_outputs": [
                {
                    "agent_id": "research_agent",
                    "output": {"claim": "structured data should be preserved", "evidence": ["chunk_1"]},
                }
            ],
            "ticket": {"id": "T-123", "status": "open"},
        },
        metadata=ContextMetadata(last_modified_by="test"),
    )


class TestTokenEstimator:
    def test_estimates_payloads(self):
        estimator = TokenEstimator()
        estimate = estimator.estimate_payload({"content": "Hello world", "values": [1, 2, 3]})

        assert estimate.total_tokens > 0
        assert estimate.breakdown["prompt"] == estimate.prompt_tokens


class TestStructuredDataPreservingSummarizer:
    def test_preserves_structured_values_and_compresses_text(self):
        summarizer = StructuredDataPreservingSummarizer()
        context = _context()
        summarized = summarizer.summarize_context(context, max_tokens=24)

        assert summarized.facts["ticket"] == context.facts["ticket"]
        assert summarized.facts["agent_outputs"] == context.facts["agent_outputs"]
        assert summarized.user_intent
        assert len(summarized.user_intent) <= len(context.user_intent)


@pytest.mark.asyncio
class TestContextWindowManager:
    async def test_prepare_agent_input_compresses_when_needed(self):
        manager = ContextWindowManager(total_budget_tokens=120, default_agent_budget_tokens=80)
        message = _message("This is a very long conversational filler message " * 20)
        context = _context()

        prepared = manager.prepare_agent_input("test_agent", message, context, token_budget=60)

        assert prepared.token_estimate.total_tokens <= 60 or not prepared.budget_check.allowed
        assert prepared.compression_result.compression_applied
        assert prepared.context.facts["ticket"] == context.facts["ticket"]

    async def test_budget_check_flags_overflow(self):
        manager = ContextWindowManager(total_budget_tokens=30, default_agent_budget_tokens=20)
        message = _message("word " * 80)
        context = _context()

        prepared = manager.prepare_agent_input("overflow_agent", message, context, token_budget=10)

        assert not prepared.budget_check.allowed
        assert prepared.budget_check.policy_violation is not None
        assert prepared.budget_check.policy_violation.details["estimated_tokens"] > 0
