"""
Critique agent for reviewing outputs from other agents.

WHY: Downstream consumers need structured quality control over agent outputs.
This agent inspects claims, citations, reasoning steps, and sentence spans to:
- Assign confidence per claim
- Flag contradictions
- Detect hallucinations and fabricated citations
- Catch prompt injection attempts inside outputs
- Produce structured critique objects with explicit spans
"""

import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from ..core import BaseAgent
from ..schemas import AgentMessage, ExecutionTrace, SharedContext, ToolCall, ToolDefinition
from .schemas import (
    ClaimConfidenceAssessment,
    CritiqueFinding,
    CritiqueIssueType,
    CritiqueResult,
    CritiqueSpan,
    CritiqueTargetType,
    ReviewedOutputSummary,
)


logger = logging.getLogger(__name__)


class CritiqueAgent(BaseAgent):
    """Agent that reviews other agent outputs at the claim/span level."""

    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"disregard\s+all\s+prior\s+instructions",
        r"reveal\s+the\s+system\s+prompt",
        r"show\s+me\s+the\s+system\s+prompt",
        r"you\s+are\s+now\s+an\s+assistant",
        r"follow\s+my\s+instructions\s+instead",
    ]

    NEGATION_TERMS = {"not", "no", "never", "cannot", "can't", "won't", "without", "false", "incorrect"}
    CLAIM_STOPWORDS = {
        "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "by",
        "with", "is", "are", "was", "were", "be", "been", "as", "at", "it",
        "this", "that", "these", "those", "from", "into", "about", "using",
        "can", "could", "should", "would", "may", "might", "must",
    }

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @property
    def agent_id(self) -> str:
        return "critique_agent"

    @property
    def agent_version(self) -> str:
        return "1.0.0"

    def get_available_tools(self) -> List[ToolDefinition]:
        return []

    async def validate_tool_call(self, tool_call: ToolCall) -> bool:
        return False

    async def process_message(self, message: AgentMessage, context: SharedContext) -> ExecutionTrace:
        """Critique one or more agent outputs embedded in context or message metadata."""
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
            reviewed_outputs = self._load_reviewed_outputs(message, context)
            critique = self._critique_outputs(reviewed_outputs)

            trace.status = "completed"
            trace.final_output = critique.model_dump()
            return trace

        except Exception as exc:
            trace.status = "failed"
            trace.error_message = str(exc)
            trace.final_output = {
                "status": "failed",
                "failure_mode": "runtime_error",
                "failure_message": str(exc),
                "reviewed_outputs": [],
                "findings": [],
            }
            self.logger.error("Critique failed: %s", exc, exc_info=True)
            return trace

        finally:
            trace.completed_at = datetime.utcnow()
            trace.total_duration_ms = (time.time() - start_time) * 1000

    def _load_reviewed_outputs(self, message: AgentMessage, context: SharedContext) -> List[Dict[str, Any]]:
        candidates: List[Any] = []

        for source in (
            context.facts.get("agent_outputs") if context.facts else None,
            context.resources.get("agent_outputs") if context.resources else None,
            message.metadata.get("agent_outputs") if message.metadata else None,
        ):
            if isinstance(source, list):
                candidates.extend(source)

        if not candidates and message.content.strip():
            parsed = self._try_parse_json(message.content)
            if isinstance(parsed, list):
                candidates.extend(parsed)
            elif isinstance(parsed, dict):
                maybe_outputs = parsed.get("agent_outputs") or parsed.get("outputs") or parsed.get("results")
                if isinstance(maybe_outputs, list):
                    candidates.extend(maybe_outputs)
                else:
                    candidates.append(parsed)

        reviewed = []
        for index, candidate in enumerate(candidates):
            normalized = self._normalize_output(candidate, index)
            if normalized is not None:
                reviewed.append(normalized)

        return reviewed

    def _normalize_output(self, candidate: Any, index: int) -> Optional[Dict[str, Any]]:
        if candidate is None:
            return None

        if isinstance(candidate, dict):
            output = candidate.get("output") or candidate.get("final_output") or candidate.get("result") or candidate
            agent_id = str(candidate.get("agent_id", output.get("agent_id", "unknown_agent") if isinstance(output, dict) else "unknown_agent"))
            output_id = str(candidate.get("output_id", candidate.get("id", f"output_{index+1}")))
            return {
                "output_id": output_id,
                "agent_id": agent_id,
                "output": output if isinstance(output, dict) else {"value": output},
            }

        if isinstance(candidate, str):
            return {
                "output_id": f"output_{index+1}",
                "agent_id": "unknown_agent",
                "output": {"value": candidate},
            }

        return {
            "output_id": f"output_{index+1}",
            "agent_id": "unknown_agent",
            "output": {"value": candidate},
        }

    def _critique_outputs(self, reviewed_outputs: List[Dict[str, Any]]) -> CritiqueResult:
        reviewed_summaries: List[ReviewedOutputSummary] = []
        claim_records: List[Dict[str, Any]] = []
        findings: List[CritiqueFinding] = []
        citation_issues: List[CritiqueFinding] = []
        reasoning_step_issues: List[CritiqueFinding] = []

        for reviewed in reviewed_outputs:
            output = reviewed["output"]
            output_kind = self._classify_output(output)
            has_claims = bool(output.get("claims"))
            has_citations = bool(output.get("citation_mapping") or output.get("provenance") or any(self._extract_citations(c) for c in output.get("claims", [])))
            has_reasoning_steps = bool(output.get("reasoning_steps") or output.get("retrieval_reasoning_chain") or output.get("decomposition_reasoning"))

            reviewed_summaries.append(
                ReviewedOutputSummary(
                    output_id=reviewed["output_id"],
                    agent_id=reviewed["agent_id"],
                    output_kind=output_kind,
                    has_claims=has_claims,
                    has_citations=has_citations,
                    has_reasoning_steps=has_reasoning_steps,
                )
            )

            claim_records.extend(
                self._extract_claim_records(reviewed["output_id"], reviewed["agent_id"], output)
            )

            step_findings = self._critique_reasoning_steps(reviewed["output_id"], reviewed["agent_id"], output)
            reasoning_step_issues.extend(step_findings)
            findings.extend(step_findings)

        citation_registry = self._build_citation_registry(reviewed_outputs)
        claim_assessments, claim_findings = self._assess_claims(claim_records, citation_registry)
        findings.extend(claim_findings)

        contradiction_findings = self._detect_contradictions(claim_records)
        findings.extend(contradiction_findings)

        hallucination_findings = [f for f in findings if f.issue_type == CritiqueIssueType.HALLUCINATION]
        citation_issues.extend([f for f in findings if f.issue_type == CritiqueIssueType.FABRICATED_CITATION])
        reasoning_step_issues.extend([f for f in findings if f.issue_type == CritiqueIssueType.PROMPT_INJECTION])

        total_issues = len(findings)
        overall_confidence = self._compute_overall_confidence(claim_assessments, findings)
        rationale = self._build_rationale(reviewed_summaries, claim_assessments, findings)

        return CritiqueResult(
            reviewed_outputs=reviewed_summaries,
            claim_assessments=claim_assessments,
            findings=findings,
            contradictions=contradiction_findings,
            hallucinations=hallucination_findings,
            citation_issues=citation_issues,
            reasoning_step_issues=reasoning_step_issues,
            total_issues=total_issues,
            overall_confidence=overall_confidence,
            rationale=rationale,
            provenance={
                "citation_registry": citation_registry,
                "review_scope": "claim/span/citation/reasoning_step",
            },
        )

    def _extract_claim_records(self, output_id: str, agent_id: str, output: Dict[str, Any]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []

        claims = output.get("claims") or []
        for index, claim in enumerate(claims):
            if isinstance(claim, dict):
                claim_text = str(claim.get("text") or claim.get("claim_text") or claim.get("value") or "").strip()
                claim_id = str(claim.get("claim_id") or claim.get("id") or f"{output_id}_claim_{index+1}")
                citations = self._extract_citations(claim)
                span = self._extract_span(claim_text, claim_text)
                records.append(
                    {
                        "claim_id": claim_id,
                        "claim_text": claim_text,
                        "output_id": output_id,
                        "agent_id": agent_id,
                        "citations": citations,
                        "span": span,
                        "kind": "claim",
                    }
                )
            elif isinstance(claim, str):
                claim_text = claim.strip()
                records.append(
                    {
                        "claim_id": f"{output_id}_claim_{index+1}",
                        "claim_text": claim_text,
                        "output_id": output_id,
                        "agent_id": agent_id,
                        "citations": [],
                        "span": self._extract_span(claim_text, claim_text),
                        "kind": "claim",
                    }
                )

        if not records:
            for field_name in ("answer", "decomposition_reasoning"):
                if isinstance(output.get(field_name), str) and output[field_name].strip():
                    text = output[field_name].strip()
                    for sentence_index, sentence in enumerate(self._split_sentences(text)):
                        span = self._extract_span(text, sentence)
                        records.append(
                            {
                                "claim_id": f"{output_id}_{field_name}_{sentence_index+1}",
                                "claim_text": sentence,
                                "output_id": output_id,
                                "agent_id": agent_id,
                                "citations": [],
                                "span": span,
                                "kind": field_name,
                            }
                        )

        if not records and isinstance(output.get("reasoning_steps"), list):
            for step_index, step in enumerate(output["reasoning_steps"]):
                if isinstance(step, str):
                    sentence = step.strip()
                    records.append(
                        {
                            "claim_id": f"{output_id}_step_{step_index+1}",
                            "claim_text": sentence,
                            "output_id": output_id,
                            "agent_id": agent_id,
                            "citations": [],
                            "span": self._extract_span(sentence, sentence),
                            "kind": "reasoning_step",
                        }
                    )

        return records

    def _critique_reasoning_steps(self, output_id: str, agent_id: str, output: Dict[str, Any]) -> List[CritiqueFinding]:
        findings: List[CritiqueFinding] = []
        texts: List[str] = []

        if isinstance(output.get("reasoning_steps"), list):
            texts.extend([str(step) for step in output["reasoning_steps"] if isinstance(step, (str, int, float))])
        if isinstance(output.get("retrieval_reasoning_chain"), list):
            for step in output["retrieval_reasoning_chain"]:
                if isinstance(step, dict):
                    texts.append(str(step.get("description", "")))
        if isinstance(output.get("decomposition_reasoning"), str):
            texts.append(output["decomposition_reasoning"])

        for text in texts:
            for match in self._find_injection_matches(text):
                span = self._extract_span(text, match)
                findings.append(
                    CritiqueFinding(
                        target_type=CritiqueTargetType.REASONING_STEP,
                        target_id=output_id,
                        issue_type=CritiqueIssueType.PROMPT_INJECTION,
                        severity=1.0,
                        confidence=0.99,
                        span=span,
                        explanation=f"Reasoning step contains prompt-injection language: '{match}'.",
                        disagreement_explanation="The reasoning step attempts to override system instructions rather than analyze evidence.",
                        evidence=[agent_id],
                    )
                )

        return findings

    def _build_citation_registry(self, reviewed_outputs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        registry: Dict[str, Dict[str, Any]] = {}

        for reviewed in reviewed_outputs:
            output = reviewed["output"]
            provenance = output.get("provenance") or {}
            selected_chunks = provenance.get("selected_chunks") or []
            for chunk in selected_chunks:
                if isinstance(chunk, dict):
                    chunk_id = str(chunk.get("chunk_id") or chunk.get("source_id") or "")
                    if chunk_id:
                        registry[chunk_id] = {
                            "agent_id": reviewed["agent_id"],
                            "output_id": reviewed["output_id"],
                            "chunk": chunk,
                        }

            source_map = output.get("source_contribution_mapping") or {}
            if isinstance(source_map, dict):
                for key, value in source_map.items():
                    registry[str(key)] = {
                        "agent_id": reviewed["agent_id"],
                        "output_id": reviewed["output_id"],
                        "chunk": value,
                    }

            citation_mapping = output.get("citation_mapping") or {}
            if isinstance(citation_mapping, dict):
                for claim_id, citations in citation_mapping.items():
                    for citation in citations if isinstance(citations, list) else []:
                        registry[str(citation)] = {
                            "agent_id": reviewed["agent_id"],
                            "output_id": reviewed["output_id"],
                            "claim_id": str(claim_id),
                        }

        return registry

    def _assess_claims(
        self,
        claim_records: List[Dict[str, Any]],
        citation_registry: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[ClaimConfidenceAssessment], List[CritiqueFinding]]:
        assessments: List[ClaimConfidenceAssessment] = []
        findings: List[CritiqueFinding] = []

        for claim in claim_records:
            claim_text = claim["claim_text"]
            citations = claim.get("citations", [])
            valid_citations = [citation for citation in citations if str(citation) in citation_registry]
            invalid_citations = [citation for citation in citations if str(citation) not in citation_registry]

            confidence = 0.88
            reasoning_parts = ["Base confidence 0.88."]

            if valid_citations:
                confidence += 0.08
                reasoning_parts.append(f"Supported by {len(valid_citations)} validated citations.")
            else:
                confidence -= 0.38
                reasoning_parts.append("No validated citations found for the claim.")

            if invalid_citations:
                confidence -= 0.35
                reasoning_parts.append("Contains citation handles that do not appear in reviewed provenance.")
                fabricated_span = self._citation_span(claim_text, invalid_citations[0])
                findings.append(
                    CritiqueFinding(
                        target_type=CritiqueTargetType.CITATION,
                        target_id=claim["claim_id"],
                        issue_type=CritiqueIssueType.FABRICATED_CITATION,
                        severity=0.95,
                        confidence=0.98,
                        span=fabricated_span,
                        explanation=f"Citation '{invalid_citations[0]}' is not present in provenance or source contribution mappings.",
                        disagreement_explanation="The claim cites a source that could not be traced to any reviewed output.",
                        evidence=[str(c) for c in citations],
                    )
                )

            if self._contains_prompt_injection(claim_text):
                confidence -= 0.5
                reasoning_parts.append("Claim text contains prompt-injection language.")
                findings.append(
                    CritiqueFinding(
                        target_type=CritiqueTargetType.SPAN,
                        target_id=claim["claim_id"],
                        issue_type=CritiqueIssueType.PROMPT_INJECTION,
                        severity=1.0,
                        confidence=0.99,
                        span=claim["span"],
                        explanation="Claim text includes prompt-injection instructions.",
                        disagreement_explanation="This is not evidence-backed content; it attempts to redirect the assistant.",
                        evidence=[claim["output_id"]],
                    )
                )

            if not valid_citations and self._looks_like_factual_claim(claim_text):
                confidence -= 0.28
                reasoning_parts.append("Factual-looking claim lacks evidence support.")
                findings.append(
                    CritiqueFinding(
                        target_type=CritiqueTargetType.CLAIM,
                        target_id=claim["claim_id"],
                        issue_type=CritiqueIssueType.HALLUCINATION,
                        severity=0.85,
                        confidence=0.92,
                        span=claim["span"],
                        explanation="The claim reads as factual but has no validated source support.",
                        disagreement_explanation="No corroborating citation or provenance item supports the statement.",
                        evidence=[claim["output_id"]],
                    )
                )

            if self._contains_low_confidence_language(claim_text):
                confidence -= 0.08
                reasoning_parts.append("Claim includes hedging language.")

            confidence = max(0.05, min(1.0, confidence))
            assessments.append(
                ClaimConfidenceAssessment(
                    claim_id=claim["claim_id"],
                    claim_text=claim_text,
                    confidence_score=confidence,
                    reasoning=" ".join(reasoning_parts),
                    citations=[str(citation) for citation in citations],
                    span=claim["span"],
                )
            )

        return assessments, findings

    def _detect_contradictions(self, claim_records: List[Dict[str, Any]]) -> List[CritiqueFinding]:
        findings: List[CritiqueFinding] = []
        for i, left in enumerate(claim_records):
            for right in claim_records[i + 1 :]:
                if left["output_id"] == right["output_id"] and left["claim_id"] == right["claim_id"]:
                    continue

                if not self._claims_about_same_topic(left["claim_text"], right["claim_text"]):
                    continue

                if not self._claims_have_opposite_polarity(left["claim_text"], right["claim_text"]):
                    continue

                shared_topic = self._shared_topic_terms(left["claim_text"], right["claim_text"])
                explanation = (
                    f"Claims disagree on the same topic terms {sorted(shared_topic)[:6]}: "
                    f"'{left['claim_text']}' vs '{right['claim_text']}'."
                )
                span_left = left["span"]
                span_right = right["span"]
                findings.append(
                    CritiqueFinding(
                        target_type=CritiqueTargetType.CLAIM,
                        target_id=f"{left['claim_id']}__vs__{right['claim_id']}",
                        issue_type=CritiqueIssueType.CONTRADICTION,
                        severity=0.9,
                        confidence=0.95,
                        span=span_left,
                        explanation=explanation,
                        disagreement_explanation=(
                            f"A conflicting claim exists at span '{span_right.text}' from output {right['output_id']}."
                        ),
                        evidence=[left["output_id"], right["output_id"]],
                    )
                )
        return findings

    def _compute_overall_confidence(
        self,
        claim_assessments: List[ClaimConfidenceAssessment],
        findings: List[CritiqueFinding],
    ) -> float:
        if not claim_assessments:
            return 0.25

        avg_claim_confidence = sum(c.confidence_score for c in claim_assessments) / len(claim_assessments)
        penalty = 0.0
        for finding in findings:
            if finding.issue_type == CritiqueIssueType.CONTRADICTION:
                penalty += 0.08
            elif finding.issue_type == CritiqueIssueType.HALLUCINATION:
                penalty += 0.12
            elif finding.issue_type == CritiqueIssueType.FABRICATED_CITATION:
                penalty += 0.15
            elif finding.issue_type == CritiqueIssueType.PROMPT_INJECTION:
                penalty += 0.18
            else:
                penalty += 0.04

        return max(0.05, min(1.0, avg_claim_confidence - penalty))

    def _build_rationale(
        self,
        reviewed_outputs: List[ReviewedOutputSummary],
        claim_assessments: List[ClaimConfidenceAssessment],
        findings: List[CritiqueFinding],
    ) -> str:
        return (
            f"Reviewed {len(reviewed_outputs)} outputs, assessed {len(claim_assessments)} claims, "
            f"and produced {len(findings)} structured findings across claims, citations, spans, and reasoning steps."
        )

    def _classify_output(self, output: Dict[str, Any]) -> str:
        if "task_graph" in output:
            return "task_graph"
        if "claims" in output:
            return "retrieval_answer"
        if "ambiguities" in output and "decomposition_reasoning" in output:
            return "decomposition_result"
        if "answer" in output and "retrieval_pipeline" in output:
            return "retrieval_reasoned_answer"
        return "generic_output"

    def _extract_citations(self, claim: Any) -> List[str]:
        citations: List[str] = []
        if isinstance(claim, dict):
            raw = claim.get("citations") or claim.get("citation_ids") or []
            if isinstance(raw, list):
                citations.extend([str(citation) for citation in raw])
            elif isinstance(raw, str):
                citations.append(raw)
        return citations

    def _extract_span(self, parent_text: str, span_text: str) -> CritiqueSpan:
        parent_text = parent_text or ""
        span_text = span_text or ""
        if not parent_text:
            return CritiqueSpan(text=span_text, start_index=0, end_index=len(span_text), source_text=parent_text)

        start = parent_text.find(span_text)
        if start < 0:
            # Fall back to the first sentence containing a matching keyword.
            for sentence in self._split_sentences(parent_text):
                if span_text.lower() in sentence.lower():
                    start = parent_text.find(sentence)
                    return CritiqueSpan(
                        text=sentence,
                        start_index=max(0, start),
                        end_index=max(0, start) + len(sentence),
                        source_text=parent_text,
                    )
            return CritiqueSpan(text=span_text, start_index=0, end_index=len(span_text), source_text=parent_text)

        return CritiqueSpan(
            text=span_text,
            start_index=start,
            end_index=start + len(span_text),
            source_text=parent_text,
        )

    def _citation_span(self, claim_text: str, citation: str) -> CritiqueSpan:
        start = claim_text.find(citation)
        if start < 0:
            return CritiqueSpan(text=str(citation), start_index=0, end_index=len(str(citation)), source_text=claim_text)
        return CritiqueSpan(text=citation, start_index=start, end_index=start + len(citation), source_text=claim_text)

    def _find_injection_matches(self, text: str) -> List[str]:
        matches: List[str] = []
        lowered = text.lower()
        for pattern in self.INJECTION_PATTERNS:
            found = re.search(pattern, lowered, re.IGNORECASE)
            if found:
                matches.append(text[found.start() : found.end()])
        return matches

    def _contains_prompt_injection(self, text: str) -> bool:
        return bool(self._find_injection_matches(text))

    def _contains_low_confidence_language(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in ["maybe", "possibly", "likely", "might", "could"])

    def _looks_like_factual_claim(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        has_numeric = bool(re.search(r"\b\d+(?:\.\d+)?%?\b", text))
        decisive_language = any(term in lowered for term in ["is", "are", "was", "were", "causes", "means", "confirms", "proves", "shows"])
        return has_numeric or decisive_language

    def _split_sentences(self, text: str) -> List[str]:
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if sentence.strip()]
        return sentences or ([text.strip()] if text.strip() else [])

    def _claims_about_same_topic(self, left: str, right: str) -> bool:
        shared = self._shared_topic_terms(left, right)
        return len(shared) >= 2

    def _claims_have_opposite_polarity(self, left: str, right: str) -> bool:
        left_neg = self._contains_negation(left)
        right_neg = self._contains_negation(right)
        if left_neg != right_neg:
            return True

        left_affirm = any(term in left.lower() for term in ["effective", "works", "true", "supports", "improves", "reduces"])
        right_affirm = any(term in right.lower() for term in ["effective", "works", "true", "supports", "improves", "reduces"])
        left_oppose = any(term in left.lower() for term in ["ineffective", "fails", "false", "decreases", "increases"])
        right_oppose = any(term in right.lower() for term in ["ineffective", "fails", "false", "decreases", "increases"])

        return (left_affirm and right_oppose) or (right_affirm and left_oppose)

    def _contains_negation(self, text: str) -> bool:
        tokens = set(re.findall(r"[a-zA-Z0-9']+", text.lower()))
        return bool(tokens & self.NEGATION_TERMS)

    def _shared_topic_terms(self, left: str, right: str) -> Set[str]:
        left_terms = self._content_terms(left)
        right_terms = self._content_terms(right)
        return left_terms & right_terms

    def _content_terms(self, text: str) -> Set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9']+", text.lower())
            if token not in self.CLAIM_STOPWORDS and len(token) > 2
        }

    def _try_parse_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None
