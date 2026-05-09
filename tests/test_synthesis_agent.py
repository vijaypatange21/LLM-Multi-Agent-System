"""Tests for the synthesis agent."""

import pytest
from uuid import uuid4

from backend.agents import SynthesisAgent
from backend.agents.schemas import CritiqueIssueType, SynthesisResult
from backend.schemas import AgentMessage, ContextMetadata, MessageRole, SharedContext


def _message(content: str = "synthesize final answer"):
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


def _context(agent_outputs):
    message = _message()
    return message, SharedContext(
        conversation_id=message.conversation_id,
        user_intent=message.content,
        facts={"agent_outputs": agent_outputs},
        metadata=ContextMetadata(last_modified_by="test"),
    )


@pytest.mark.asyncio
class TestSynthesisAgent:
    async def test_merges_outputs_and_builds_provenance_map(self):
        agent = SynthesisAgent()
        agent_outputs = [
            {
                "output_id": "retrieval-1",
                "agent_id": "retrieval_reasoning_agent",
                "output": {
                    "claims": [
                        {
                            "claim_id": "C1",
                            "text": "Transformer models use self-attention to capture long-range dependencies.",
                            "citations": ["chunk_1", "chunk_2"],
                        }
                    ],
                    "provenance": {"selected_chunks": [{"chunk_id": "chunk_1"}, {"chunk_id": "chunk_2"}]},
                },
            },
            {
                "output_id": "critique-1",
                "agent_id": "critique_agent",
                "output": {
                    "findings": [],
                    "claim_assessments": [
                        {"claim_id": "C1", "confidence_score": 0.92, "reasoning": "Supported by evidence."}
                    ],
                    "reviewed_outputs": [],
                },
            },
        ]
        message, context = _context(agent_outputs)
        trace = await agent.process_message(message, context)

        assert trace.status == "completed"
        output = trace.final_output
        assert isinstance(SynthesisResult.model_validate(output), SynthesisResult)
        assert output["final_answer"]
        assert output["sentence_provenance"]
        first_sentence = output["sentence_provenance"][0]
        assert first_sentence["source_agent_ids"] == ["retrieval_reasoning_agent"]
        assert first_sentence["source_chunks"] == ["chunk_1", "chunk_2"]
        assert first_sentence["critique_status"] in {"clean", "reviewed"}
        assert first_sentence["sentence"] in output["final_answer"]

    async def test_resolves_contradictions_and_explains_rejection(self):
        agent = SynthesisAgent()
        agent_outputs = [
            {
                "output_id": "out-a",
                "agent_id": "retrieval_reasoning_agent",
                "output": {
                    "claims": [
                        {
                            "claim_id": "A1",
                            "text": "The treatment is effective and reduces symptoms.",
                            "citations": ["chunk_1"],
                        }
                    ],
                    "provenance": {"selected_chunks": [{"chunk_id": "chunk_1"}]},
                },
            },
            {
                "output_id": "out-b",
                "agent_id": "retrieval_reasoning_agent",
                "output": {
                    "claims": [
                        {
                            "claim_id": "B1",
                            "text": "The treatment is not effective and does not reduce symptoms.",
                            "citations": ["chunk_2"],
                        }
                    ],
                    "provenance": {"selected_chunks": [{"chunk_id": "chunk_2"}]},
                },
            },
            {
                "output_id": "critique-2",
                "agent_id": "critique_agent",
                "output": {
                    "findings": [
                        {
                            "finding_id": str(uuid4()),
                            "target_type": "claim",
                            "target_id": "B1",
                            "issue_type": CritiqueIssueType.CONTRADICTION.value,
                            "severity": 0.9,
                            "confidence": 0.97,
                            "span": {
                                "text": "The treatment is not effective and does not reduce symptoms.",
                                "start_index": 0,
                                "end_index": 64,
                                "sentence_index": None,
                                "source_text": "The treatment is not effective and does not reduce symptoms.",
                            },
                            "explanation": "Conflicts with another supported claim.",
                            "disagreement_explanation": "Direct disagreement over effectiveness.",
                            "evidence": ["out-a", "out-b"],
                        }
                    ],
                    "claim_assessments": [],
                    "reviewed_outputs": [],
                },
            },
        ]
        message, context = _context(agent_outputs)
        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "completed"
        assert output["rejected_claims"]
        assert "Rejected" in " ".join(output["conflict_resolution_log"])
        assert any("because" in note.lower() for note in output["safety_notes"])
        assert any("treatment is effective" in sent["sentence"] for sent in output["sentence_provenance"])
        assert not any("not effective" in sent["sentence"] for sent in output["sentence_provenance"])

    async def test_uses_critique_feedback_to_lower_confidence(self):
        agent = SynthesisAgent()
        agent_outputs = [
            {
                "output_id": "out-1",
                "agent_id": "retrieval_reasoning_agent",
                "output": {
                    "claims": [
                        {
                            "claim_id": "C1",
                            "text": "The model improves accuracy by 20%.",
                            "citations": ["chunk_1"],
                        }
                    ],
                    "provenance": {"selected_chunks": [{"chunk_id": "chunk_1"}]},
                },
            },
            {
                "output_id": "critique-3",
                "agent_id": "critique_agent",
                "output": {
                    "findings": [
                        {
                            "finding_id": str(uuid4()),
                            "target_type": "claim",
                            "target_id": "C1",
                            "issue_type": CritiqueIssueType.HALLUCINATION.value,
                            "severity": 0.85,
                            "confidence": 0.94,
                            "span": {
                                "text": "The model improves accuracy by 20%.",
                                "start_index": 0,
                                "end_index": 34,
                                "sentence_index": None,
                                "source_text": "The model improves accuracy by 20%.",
                            },
                            "explanation": "No supporting evidence found.",
                            "disagreement_explanation": "Unsupported factual claim.",
                            "evidence": ["out-1"],
                        }
                    ],
                    "claim_assessments": [
                        {"claim_id": "C1", "confidence_score": 0.18, "reasoning": "Critique found hallucination."}
                    ],
                    "reviewed_outputs": [],
                },
            },
        ]
        message, context = _context(agent_outputs)
        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert trace.status == "completed"
        assert output["aggregated_confidence"] < 0.6
        assert any("critique" in note.lower() for note in output["critique_feedback_used"])
        assert output["sentence_provenance"][0]["critique_status"] in {"reviewed", "clean", "rejected"}

    async def test_sentence_level_provenance_covers_each_sentence(self):
        agent = SynthesisAgent()
        agent_outputs = [
            {
                "output_id": "out-1",
                "agent_id": "retrieval_reasoning_agent",
                "output": {
                    "claims": [
                        {
                            "claim_id": "C1",
                            "text": "First sentence from evidence.",
                            "citations": ["chunk_1"],
                        },
                        {
                            "claim_id": "C2",
                            "text": "Second sentence from evidence.",
                            "citations": ["chunk_2"],
                        },
                    ],
                    "provenance": {"selected_chunks": [{"chunk_id": "chunk_1"}, {"chunk_id": "chunk_2"}]},
                },
            }
        ]
        message, context = _context(agent_outputs)
        trace = await agent.process_message(message, context)
        output = trace.final_output

        assert len(output["sentence_provenance"]) >= 2
        for sentence in output["sentence_provenance"]:
            assert sentence["source_agent_ids"]
            assert sentence["source_chunks"]
            assert sentence["critique_status"]
            assert sentence["sentence"]
            assert sentence["sentence_id"] in output["provenance_map"]
