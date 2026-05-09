"""Unit tests for retrieval-augmented reasoning agent."""

import pytest
from uuid import uuid4

from backend.agents import RetrievalReasoningAgent
from backend.schemas import AgentMessage, ContextMetadata, MessageRole, SharedContext


def _build_context(chunks):
    return SharedContext(
        conversation_id=uuid4(),
        user_intent="answer with retrieval",
        facts={"retrieval_chunks": chunks},
        metadata=ContextMetadata(last_modified_by="test"),
    )


def _build_message(content: str):
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


@pytest.mark.asyncio
class TestRetrievalReasoningAgent:
    async def test_multi_hop_retrieval_pipeline(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "c1",
                    "source_id": "s1",
                    "source_title": "Doc 1",
                    "content": "Transformer models use self-attention for sequence modeling.",
                },
                {
                    "chunk_id": "c2",
                    "source_id": "s2",
                    "source_title": "Doc 2",
                    "content": "Self-attention enables capturing long-range dependencies in text.",
                },
                {
                    "chunk_id": "c3",
                    "source_id": "s3",
                    "source_title": "Doc 3",
                    "content": "Long-range dependency handling improves summarization quality.",
                },
            ]
        )
        message = _build_message("How do transformers handle long-range dependencies?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)

        assert trace.status == "completed"
        output = trace.final_output
        assert output is not None
        assert len(output["retrieval_pipeline"]["hops"]) >= 2

    async def test_minimum_two_chunks_before_answer(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "c1",
                    "source_id": "s1",
                    "source_title": "Single Doc",
                    "content": "A single evidence chunk is available for this topic.",
                }
            ]
        )
        message = _build_message("single evidence chunk available topic")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "failed"
        assert output["answer"] is None
        assert output["failure_mode"] == "insufficient_evidence"

    async def test_citation_mapping_and_claim_attribution(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "c1",
                    "source_id": "s1",
                    "source_title": "Policy A",
                    "content": "Policy A reduced latency by 20 percent in production.",
                },
                {
                    "chunk_id": "c2",
                    "source_id": "s2",
                    "source_title": "Policy B",
                    "content": "Independent audit confirms reduced latency after rollout.",
                },
            ]
        )
        message = _build_message("What was the latency impact?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "completed"
        assert output["claims"]
        assert output["citation_mapping"]
        first_claim = output["claims"][0]
        assert first_claim["citations"]
        assert first_claim["contribution_map"]
        assert first_claim["claim_id"] in output["citation_mapping"]

    async def test_query_reformulation_retries_present(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "x1",
                    "source_id": "sx1",
                    "source_title": "Unrelated",
                    "content": "This source discusses marine biology and coral reefs.",
                },
                {
                    "chunk_id": "x2",
                    "source_id": "sx2",
                    "source_title": "Unrelated 2",
                    "content": "This source discusses astronomy and distant galaxies.",
                },
            ]
        )
        message = _build_message("Explain distributed tracing in microservices")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "failed"
        assert output["retrieval_pipeline"]["reformulations"]

    async def test_structured_provenance_and_source_contribution_mapping(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "p1",
                    "source_id": "paper-1",
                    "source_title": "Paper 1",
                    "content": "Embedding caching reduces vector retrieval latency in online systems.",
                },
                {
                    "chunk_id": "p2",
                    "source_id": "paper-2",
                    "source_title": "Paper 2",
                    "content": "Latency reduction also depends on index pruning strategy.",
                },
            ]
        )
        message = _build_message("How can latency be reduced in retrieval systems?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "completed"
        assert "provenance" in output
        assert "selected_chunks" in output["provenance"]
        assert "source_contribution_mapping" in output
        assert output["source_contribution_mapping"]

    async def test_failure_handling_empty_retrieval(self):
        agent = RetrievalReasoningAgent()
        context = _build_context([])
        message = _build_message("Any answer?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "failed"
        assert output["failure_mode"] == "empty_retrieval"

    async def test_failure_handling_irrelevant_retrieval(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "i1",
                    "source_id": "misc-1",
                    "source_title": "Misc",
                    "content": "Banana recipes and smoothie ingredients.",
                },
                {
                    "chunk_id": "i2",
                    "source_id": "misc-2",
                    "source_title": "Misc 2",
                    "content": "Tropical fruit storage and ripening tips.",
                },
            ]
        )
        message = _build_message("How does Raft leader election handle split votes?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "failed"
        assert output["failure_mode"] in {"irrelevant_retrieval", "empty_retrieval"}

    async def test_failure_handling_conflicting_sources(self):
        agent = RetrievalReasoningAgent()
        context = _build_context(
            [
                {
                    "chunk_id": "k1",
                    "source_id": "study-a",
                    "source_title": "Study A",
                    "content": "The treatment is effective and reduces symptoms significantly.",
                },
                {
                    "chunk_id": "k2",
                    "source_id": "study-b",
                    "source_title": "Study B",
                    "content": "The treatment is not effective and does not reduce symptoms.",
                },
                {
                    "chunk_id": "k3",
                    "source_id": "study-c",
                    "source_title": "Study C",
                    "content": "Symptoms were measured across randomized cohorts.",
                },
            ]
        )
        message = _build_message("Is the treatment effective?")
        context.conversation_id = message.conversation_id

        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "completed"
        assert "conflicts" in output["provenance"]
        assert output["provenance"]["conflicts"]
