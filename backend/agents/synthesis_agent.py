"""
Synthesis agent for merging outputs from all agents into a final user-safe answer.

WHY: The system needs a final layer that merges evidence, resolves conflicts,
uses critique feedback, and explains why some conflicting claims were rejected.
This agent produces sentence-level provenance so each sentence can be traced to:
- source agent
- source chunks
- critique status
"""

import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from ..core import BaseAgent
from ..schemas import AgentMessage, ExecutionTrace, SharedContext, ToolCall, ToolDefinition
from .schemas import (
    ClaimConfidenceAssessment,
    CritiqueFinding,
    CritiqueIssueType,
    CritiqueResult,
    CritiqueTargetType,
    SynthesisProvenanceEdge,
    SynthesisProvenanceNode,
    SynthesisResult,
    SynthesisSentenceProvenance,
    SynthesisSourceType,
)


logger = logging.getLogger(__name__)


class SynthesisAgent(BaseAgent):
    """Agent that composes a final user-safe answer from all prior agent outputs."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @property
    def agent_id(self) -> str:
        return "synthesis_agent"

    @property
    def agent_version(self) -> str:
        return "1.0.0"

    def get_available_tools(self) -> List[ToolDefinition]:
        return []

    async def validate_tool_call(self, tool_call: ToolCall) -> bool:
        return False

    async def process_message(self, message: AgentMessage, context: SharedContext) -> ExecutionTrace:
        start_time = time.time()
        trace = ExecutionTrace(
            id=uuid4(),
            conversation_id=message.conversation_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            status="in_progress",
            total_duration_ms=0.0,
            metadata={"trace_id": str(message.trace_id)},
        )

        try:
            agent_outputs = self._load_agent_outputs(message, context)
            critique_outputs = [
                self._normalize_output(o, index)
                for index, o in enumerate(agent_outputs)
                if self._is_critique_output(o)
            ]
            critique_outputs = [c for c in critique_outputs if c is not None]
            critique_index = self._build_critique_index(critique_outputs)
            synthesis = self._synthesize(agent_outputs, critique_index)

            trace.status = "completed"
            trace.final_output = synthesis.model_dump()
            return trace

        except Exception as exc:
            trace.status = "failed"
            trace.error_message = str(exc)
            trace.final_output = {
                "status": "failed",
                "failure_mode": "runtime_error",
                "failure_message": str(exc),
                "final_answer": "",
                "sentence_provenance": [],
                "provenance_nodes": [],
                "provenance_edges": [],
                "conflict_resolution_log": [],
                "rejected_claims": [],
                "aggregated_confidence": 0.0,
                "critique_feedback_used": [],
                "safety_notes": [],
                "provenance_map": {},
            }
            self.logger.error("Synthesis failed: %s", exc, exc_info=True)
            return trace

        finally:
            trace.completed_at = datetime.utcnow()
            trace.total_duration_ms = (time.time() - start_time) * 1000

    def _load_agent_outputs(self, message: AgentMessage, context: SharedContext) -> List[Dict[str, Any]]:
        candidates: List[Any] = []
        for source in (
            context.facts.get("agent_outputs") if context.facts else None,
            context.resources.get("agent_outputs") if context.resources else None,
            message.metadata.get("agent_outputs") if message.metadata else None,
        ):
            if isinstance(source, list):
                candidates.extend(source)

        normalized: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            item = self._normalize_output(candidate, index)
            if item is not None:
                normalized.append(item)
        return normalized

    def _normalize_output(self, candidate: Any, index: int = 0) -> Optional[Dict[str, Any]]:
        if candidate is None:
            return None
        if isinstance(candidate, dict):
            output = candidate.get("output") or candidate.get("final_output") or candidate.get("result") or candidate
            output_id = str(candidate.get("output_id", candidate.get("id", f"output_{index+1}")))
            agent_id = str(candidate.get("agent_id", output.get("agent_id", "unknown_agent") if isinstance(output, dict) else "unknown_agent"))
            return {"output_id": output_id, "agent_id": agent_id, "output": output if isinstance(output, dict) else {"value": output}}
        if isinstance(candidate, str):
            return {"output_id": f"output_{index+1}", "agent_id": "unknown_agent", "output": {"value": candidate}}
        return {"output_id": f"output_{index+1}", "agent_id": "unknown_agent", "output": {"value": candidate}}

    def _is_critique_output(self, output: Dict[str, Any]) -> bool:
        payload = output.get("output", {})
        return isinstance(payload, dict) and ("findings" in payload or "claim_assessments" in payload or "reviewed_outputs" in payload)

    def _build_critique_index(self, critique_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        index = {
            "claim_confidence": {},
            "findings_by_target": defaultdict(list),
            "findings_by_issue": defaultdict(list),
            "output_status": defaultdict(lambda: "unreviewed"),
        }

        for output in critique_outputs:
            payload = output["output"]
            for assessment in payload.get("claim_assessments", []):
                if isinstance(assessment, dict):
                    index["claim_confidence"][str(assessment.get("claim_id"))] = assessment

            for finding in payload.get("findings", []):
                if isinstance(finding, dict):
                    target_id = str(finding.get("target_id", ""))
                    issue_type = str(finding.get("issue_type", ""))
                    index["findings_by_target"][target_id].append(finding)
                    index["findings_by_issue"][issue_type].append(finding)
                    if target_id:
                        index["output_status"][target_id] = "rejected" if issue_type in {
                            CritiqueIssueType.CONTRADICTION.value,
                            CritiqueIssueType.HALLUCINATION.value,
                            CritiqueIssueType.FABRICATED_CITATION.value,
                            CritiqueIssueType.PROMPT_INJECTION.value,
                        } else "reviewed"

        return index

    def _synthesize(self, agent_outputs: List[Dict[str, Any]], critique_index: Dict[str, Any]) -> SynthesisResult:
        candidate_claims = self._collect_candidate_claims(agent_outputs)
        resolution = self._resolve_contradictions(candidate_claims, critique_index)
        selected_claims = resolution["selected_claims"]
        rejected_claims = resolution["rejected_claims"]
        conflict_logs = resolution["conflict_logs"]

        sentences: List[str] = []
        sentence_provenance: List[SynthesisSentenceProvenance] = []
        provenance_nodes: List[SynthesisProvenanceNode] = []
        provenance_edges: List[SynthesisProvenanceEdge] = []
        critique_feedback_used: List[str] = []
        safety_notes: List[str] = []

        if selected_claims:
            for claim in selected_claims:
                sentence = self._claim_to_sentence(claim)
                sentences.append(sentence)

                critique_status, critique_note = self._aggregate_critique_status(claim, critique_index)
                critique_feedback_used.extend(critique_note)
                sentence_confidence = self._aggregate_sentence_confidence(claim, critique_index, selected=True)
                source_chunks = claim.get("source_chunks", [])
                source_agent_ids = [claim["agent_id"]]

                sentence_provenance.append(
                    SynthesisSentenceProvenance(
                        sentence_id=f"sent_{len(sentences)}",
                        sentence=sentence,
                        source_agent_ids=source_agent_ids,
                        source_chunks=source_chunks,
                        critique_status=critique_status,
                        supporting_claim_ids=[claim["claim_id"]],
                        rejected_claim_ids=[],
                        confidence=sentence_confidence,
                        explanation=self._sentence_explanation(claim, critique_status, source_chunks),
                    )
                )

                provenance_nodes.append(
                    SynthesisProvenanceNode(
                        node_id=claim["claim_id"],
                        node_type=SynthesisSourceType.CLAIM,
                        source_agent_id=claim["agent_id"],
                        source_chunks=source_chunks,
                        critique_status=critique_status,
                        confidence=sentence_confidence,
                        text=claim["text"],
                    )
                )
        else:
            fallback_sentence = "I could not safely merge the available outputs because the evidence was conflicting or unsupported."
            sentences.append(fallback_sentence)
            fallback_sources = [claim["agent_id"] for claim in rejected_claims] or ["synthesis_agent"]
            fallback_chunks: List[str] = []
            for claim in rejected_claims:
                fallback_chunks.extend(claim.get("source_chunks", []))
            fallback_chunks = list(dict.fromkeys(fallback_chunks))
            sentence_provenance.append(
                SynthesisSentenceProvenance(
                    sentence_id="sent_1",
                    sentence=fallback_sentence,
                    source_agent_ids=fallback_sources,
                    source_chunks=fallback_chunks,
                    critique_status="rejected",
                    supporting_claim_ids=[],
                    rejected_claim_ids=[claim["claim_id"] for claim in rejected_claims],
                    confidence=0.25,
                    explanation="All available claims were rejected by critique or contradiction resolution, so a safe fallback response was produced.",
                )
            )

        for claim in rejected_claims:
            critique_status, critique_note = self._aggregate_critique_status(claim, critique_index)
            critique_feedback_used.extend(critique_note)
            reason = self._rejection_reason(claim, critique_index, resolution["rejection_reasons"].get(claim["claim_id"], []))
            safety_notes.append(reason)
            conflict_logs.append(reason)
            provenance_nodes.append(
                SynthesisProvenanceNode(
                    node_id=claim["claim_id"],
                    node_type=SynthesisSourceType.CLAIM,
                    source_agent_id=claim["agent_id"],
                    source_chunks=claim.get("source_chunks", []),
                    critique_status=critique_status,
                    confidence=self._aggregate_sentence_confidence(claim, critique_index, selected=False),
                    text=claim["text"],
                )
            )

        # Add outputs and critique nodes to provenance graph.
        for output in agent_outputs:
            output_node = SynthesisProvenanceNode(
                node_id=output["output_id"],
                node_type=SynthesisSourceType.AGENT_OUTPUT,
                source_agent_id=output["agent_id"],
                source_chunks=self._extract_output_chunks(output),
                critique_status=self._output_critique_status(output, critique_index),
                confidence=self._output_confidence(output, critique_index),
                text=self._output_summary_text(output),
            )
            provenance_nodes.append(output_node)

            for claim in self._collect_candidate_claims([output]):
                provenance_edges.append(
                    SynthesisProvenanceEdge(
                        edge_id=f"edge_{output['output_id']}__{claim['claim_id']}",
                        from_node_id=output["output_id"],
                        to_node_id=claim["claim_id"],
                        relation="SUPPORTS",
                        rationale="Claim was extracted from this agent output and carried into synthesis.",
                    )
                )

        final_answer = self._compose_final_answer(sentences, safety_notes)
        aggregated_confidence = self._aggregate_confidence(sentence_provenance, rejected_claims, critique_index)

        provenance_map = {
            sp.sentence_id: {
                "sentence": sp.sentence,
                "source_agent_ids": sp.source_agent_ids,
                "source_chunks": sp.source_chunks,
                "critique_status": sp.critique_status,
                "confidence": sp.confidence,
            }
            for sp in sentence_provenance
        }

        return SynthesisResult(
            final_answer=final_answer,
            sentence_provenance=sentence_provenance,
            provenance_nodes=provenance_nodes,
            provenance_edges=provenance_edges,
            conflict_resolution_log=conflict_logs,
            rejected_claims=[claim["claim_id"] for claim in rejected_claims],
            aggregated_confidence=aggregated_confidence,
            critique_feedback_used=sorted(set(critique_feedback_used)),
            safety_notes=safety_notes,
            provenance_map=provenance_map,
        )

    def _collect_candidate_claims(self, agent_outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        claims: List[Dict[str, Any]] = []
        for output in agent_outputs:
            payload = output["output"]
            source_chunks = self._extract_output_chunks(output)

            if "claims" in payload and isinstance(payload["claims"], list):
                for index, claim in enumerate(payload["claims"]):
                    if not isinstance(claim, dict):
                        continue
                    text = str(claim.get("text") or claim.get("claim_text") or "").strip()
                    claim_id = str(claim.get("claim_id") or claim.get("id") or f"{output['output_id']}_claim_{index+1}")
                    claims.append(
                        {
                            "claim_id": claim_id,
                            "text": text,
                            "agent_id": output["agent_id"],
                            "output_id": output["output_id"],
                            "source_chunks": list(dict.fromkeys(source_chunks + [str(c) for c in claim.get("citations", []) if c])),
                            "citations": [str(c) for c in claim.get("citations", []) if c],
                            "raw_claim": claim,
                        }
                    )

            if "answer" in payload and isinstance(payload["answer"], str) and payload["answer"].strip():
                for sentence_index, sentence in enumerate(self._split_sentences(payload["answer"])):
                    claim_id = f"{output['output_id']}_sentence_{sentence_index+1}"
                    claims.append(
                        {
                            "claim_id": claim_id,
                            "text": sentence,
                            "agent_id": output["agent_id"],
                            "output_id": output["output_id"],
                            "source_chunks": list(source_chunks),
                            "citations": [],
                            "raw_claim": {"text": sentence},
                        }
                    )

            if "decomposition_reasoning" in payload and isinstance(payload["decomposition_reasoning"], str):
                for sentence_index, sentence in enumerate(self._split_sentences(payload["decomposition_reasoning"])):
                    claim_id = f"{output['output_id']}_reasoning_{sentence_index+1}"
                    claims.append(
                        {
                            "claim_id": claim_id,
                            "text": sentence,
                            "agent_id": output["agent_id"],
                            "output_id": output["output_id"],
                            "source_chunks": list(source_chunks),
                            "citations": [],
                            "raw_claim": {"text": sentence},
                        }
                    )

        return claims

    def _resolve_contradictions(self, claims: List[Dict[str, Any]], critique_index: Dict[str, Any]) -> Dict[str, Any]:
        selected: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        conflict_logs: List[str] = []
        rejection_reasons: Dict[str, List[str]] = defaultdict(list)

        by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for claim in claims:
            by_topic[self._topic_signature(claim["text"])].append(claim)

        for topic, topic_claims in by_topic.items():
            if len(topic_claims) == 1:
                claim = topic_claims[0]
                if self._claim_is_safe(claim, critique_index):
                    selected.append(claim)
                else:
                    rejected.append(claim)
                    rejection_reasons[claim["claim_id"]].append("Critique feedback marked the claim unsafe or unsupported.")
                continue

            ranked = sorted(
                topic_claims,
                key=lambda c: (
                    self._claim_support_score(c, critique_index),
                    len(c.get("source_chunks", [])),
                    -self._claim_negation_penalty(c["text"]),
                ),
                reverse=True,
            )
            winner = ranked[0]
            selected.append(winner)

            for loser in ranked[1:]:
                rejected.append(loser)
                reason = self._why_rejected(loser, winner, critique_index)
                rejection_reasons[loser["claim_id"]].append(reason)
                conflict_logs.append(
                    f"Rejected {loser['claim_id']} from {loser['agent_id']} because it conflicted with {winner['claim_id']} and had lower support."
                )

        # Add explicit rejection for claims directly flagged by critique.
        for claim in list(selected):
            if not self._claim_is_safe(claim, critique_index):
                selected.remove(claim)
                rejected.append(claim)
                rejection_reasons[claim["claim_id"]].append("Critique feedback overrode this claim due to low confidence or safety issues.")
                conflict_logs.append(
                    f"Rejected {claim['claim_id']} from {claim['agent_id']} because critique feedback marked it unsafe or unsupported."
                )

        return {
            "selected_claims": selected,
            "rejected_claims": rejected,
            "conflict_logs": conflict_logs,
            "rejection_reasons": rejection_reasons,
        }

    def _claim_is_safe(self, claim: Dict[str, Any], critique_index: Dict[str, Any]) -> bool:
        claim_id = claim["claim_id"]
        findings = critique_index["findings_by_target"].get(claim_id, [])
        if not findings:
            return True
        blocked = {CritiqueIssueType.CONTRADICTION.value, CritiqueIssueType.HALLUCINATION.value, CritiqueIssueType.FABRICATED_CITATION.value, CritiqueIssueType.PROMPT_INJECTION.value}
        return not any(str(f.get("issue_type")) in blocked for f in findings)

    def _claim_support_score(self, claim: Dict[str, Any], critique_index: Dict[str, Any]) -> float:
        claim_id = claim["claim_id"]
        assessment = critique_index["claim_confidence"].get(claim_id, {})
        confidence = float(assessment.get("confidence_score", 0.5)) if assessment else 0.5
        citation_bonus = min(0.2, 0.05 * len(claim.get("source_chunks", [])))
        critique_penalty = 0.0
        for finding in critique_index["findings_by_target"].get(claim_id, []):
            issue_type = str(finding.get("issue_type"))
            if issue_type in {CritiqueIssueType.CONTRADICTION.value, CritiqueIssueType.HALLUCINATION.value}:
                critique_penalty += 0.35
            elif issue_type == CritiqueIssueType.FABRICATED_CITATION.value:
                critique_penalty += 0.4
            elif issue_type == CritiqueIssueType.PROMPT_INJECTION.value:
                critique_penalty += 0.5
        return max(0.0, min(1.0, confidence + citation_bonus - critique_penalty))

    def _claim_negation_penalty(self, text: str) -> float:
        tokens = set(re.findall(r"[a-zA-Z0-9']+", text.lower()))
        return 1.0 if tokens & {"not", "no", "never", "false", "cannot", "can't", "won't"} else 0.0

    def _why_rejected(self, loser: Dict[str, Any], winner: Dict[str, Any], critique_index: Dict[str, Any]) -> str:
        reasons: List[str] = []
        loser_findings = critique_index["findings_by_target"].get(loser["claim_id"], [])
        if loser_findings:
            reasons.append(
                "critique flagged " + ", ".join(sorted({str(f.get("issue_type")) for f in loser_findings}))
            )
        reasons.append(f"it had lower support than {winner['claim_id']}")
        if self._claims_conflict(loser["text"], winner["text"]):
            reasons.append("it directly conflicted with the selected claim")
        return "; ".join(reasons)

    def _aggregate_sentence_confidence(self, claim: Dict[str, Any], critique_index: Dict[str, Any], selected: bool) -> float:
        base = self._claim_support_score(claim, critique_index)
        if selected:
            return max(0.1, min(1.0, base))
        return max(0.05, min(0.45, base * 0.5))

    def _aggregate_critique_status(self, claim: Dict[str, Any], critique_index: Dict[str, Any]) -> Tuple[str, List[str]]:
        findings = critique_index["findings_by_target"].get(claim["claim_id"], [])
        if not findings:
            return "clean", []
        issue_types = {str(f.get("issue_type")) for f in findings}
        if issue_types & {CritiqueIssueType.CONTRADICTION.value, CritiqueIssueType.HALLUCINATION.value, CritiqueIssueType.FABRICATED_CITATION.value, CritiqueIssueType.PROMPT_INJECTION.value}:
            return "rejected", [f"{claim['claim_id']} marked rejected by critique: {', '.join(sorted(issue_types))}"]
        return "reviewed", [f"{claim['claim_id']} reviewed with issues: {', '.join(sorted(issue_types))}"]

    def _output_critique_status(self, output: Dict[str, Any], critique_index: Dict[str, Any]) -> str:
        target_findings = critique_index["findings_by_target"].get(output["output_id"], [])
        if not target_findings:
            return "reviewed"
        if any(str(f.get("issue_type")) in {CritiqueIssueType.CONTRADICTION.value, CritiqueIssueType.HALLUCINATION.value, CritiqueIssueType.FABRICATED_CITATION.value, CritiqueIssueType.PROMPT_INJECTION.value} for f in target_findings):
            return "rejected"
        return "reviewed"

    def _output_confidence(self, output: Dict[str, Any], critique_index: Dict[str, Any]) -> float:
        claim_ids = [claim["claim_id"] for claim in self._collect_candidate_claims([output])]
        if not claim_ids:
            return 0.5
        return sum(self._claim_support_score({"claim_id": cid, "source_chunks": [] ,"text": ""}, critique_index) for cid in claim_ids) / len(claim_ids)

    def _compose_final_answer(self, sentences: List[str], safety_notes: List[str]) -> str:
        if not sentences:
            return "I could not produce a reliable final answer from the available evidence."
        answer = " ".join(sentences)
        if safety_notes:
            answer += "\n\nRejected conflicting claims: " + "; ".join(safety_notes)
        return answer

    def _aggregate_confidence(
        self,
        sentence_provenance: List[SynthesisSentenceProvenance],
        rejected_claims: List[Dict[str, Any]],
        critique_index: Dict[str, Any],
    ) -> float:
        if not sentence_provenance:
            return 0.2

        avg_sentence_confidence = sum(sp.confidence for sp in sentence_provenance) / len(sentence_provenance)
        rejection_penalty = min(0.35, 0.07 * len(rejected_claims))
        critique_bonus = 0.05 if critique_index["claim_confidence"] else 0.0
        return max(0.05, min(1.0, avg_sentence_confidence - rejection_penalty + critique_bonus))

    def _claim_to_sentence(self, claim: Dict[str, Any]) -> str:
        text = str(claim.get("text") or claim.get("claim_text") or "").strip()
        if not text:
            return ""
        return text if text.endswith(('.', '!', '?')) else f"{text}."

    def _sentence_explanation(self, claim: Dict[str, Any], critique_status: str, source_chunks: List[str]) -> str:
        chunk_text = ", ".join(source_chunks) if source_chunks else "no chunks"
        return (
            f"Sentence derived from {claim['claim_id']} using {chunk_text}; critique status={critique_status}."
        )

    def _rejection_reason(self, claim: Dict[str, Any], critique_index: Dict[str, Any], reasons: List[str]) -> str:
        critique_status = self._output_critique_status({"output_id": claim["output_id"]}, critique_index)
        reason_text = "; ".join(dict.fromkeys(reasons))
        return f"Rejected {claim['claim_id']} from {claim['agent_id']} ({critique_status}) because {reason_text}."

    def _extract_output_chunks(self, output: Dict[str, Any]) -> List[str]:
        payload = output.get("output", {})
        chunks: List[str] = []
        provenance = payload.get("provenance") or {}
        for chunk in provenance.get("selected_chunks", []):
            if isinstance(chunk, dict):
                chunk_id = str(chunk.get("chunk_id") or chunk.get("source_id") or "")
                if chunk_id:
                    chunks.append(chunk_id)
        source_map = payload.get("source_contribution_mapping") or {}
        if isinstance(source_map, dict):
            chunks.extend([str(k) for k in source_map.keys()])
        claims = payload.get("claims") or []
        for claim in claims:
            if isinstance(claim, dict):
                chunks.extend([str(c) for c in claim.get("citations", []) if c])
        return list(dict.fromkeys(chunks))

    def _output_summary_text(self, output: Dict[str, Any]) -> str:
        payload = output.get("output", {})
        if "answer" in payload and isinstance(payload["answer"], str):
            return payload["answer"]
        if "decomposition_reasoning" in payload and isinstance(payload["decomposition_reasoning"], str):
            return payload["decomposition_reasoning"]
        if "findings" in payload:
            return f"Critique output with {len(payload.get('findings', []))} findings"
        return json.dumps(payload, default=str)[:240]

    def _split_sentences(self, text: str) -> List[str]:
        return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if sentence.strip()]

    def _topic_signature(self, text: str) -> str:
        terms = [token for token in re.findall(r"[a-zA-Z0-9']+", text.lower()) if len(token) > 2]
        filtered = [term for term in terms if term not in {"the", "and", "with", "from", "that", "this", "have", "has", "was", "were"}]
        if not filtered:
            return text.lower()[:40]
        return " ".join(sorted(set(filtered))[:5])

    def _claims_conflict(self, left: str, right: str) -> bool:
        left_terms = set(re.findall(r"[a-zA-Z0-9']+", left.lower()))
        right_terms = set(re.findall(r"[a-zA-Z0-9']+", right.lower()))
        shared = {term for term in (left_terms & right_terms) if len(term) > 2}
        if len(shared) < 2:
            return False
        left_neg = bool(left_terms & {"not", "no", "never", "false", "cannot", "can't", "won't"})
        right_neg = bool(right_terms & {"not", "no", "never", "false", "cannot", "can't", "won't"})
        return left_neg != right_neg
