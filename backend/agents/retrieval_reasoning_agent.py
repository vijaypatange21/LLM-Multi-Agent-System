"""
Retrieval-augmented reasoning agent.

WHY: Some user queries require evidence-backed answers. This agent performs:
- Multi-hop retrieval over available chunks
- Query reformulation retries when retrieval quality is poor
- Claim-level citation attribution
- Structured provenance and source contribution mapping
- Failure handling for empty, irrelevant, and conflicting retrieval outcomes
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from ..core import BaseAgent
from ..schemas import AgentMessage, ExecutionTrace, SharedContext, ToolCall, ToolDefinition


logger = logging.getLogger(__name__)


class RetrievalReasoningAgent(BaseAgent):
    """Agent that answers queries using multi-hop retrieval and explicit provenance."""

    MIN_CHUNKS_REQUIRED = 2
    DEFAULT_TOP_K = 5
    DEFAULT_MAX_HOPS = 2
    DEFAULT_MAX_RETRIES = 2
    RELEVANCE_THRESHOLD = 0.1
    NEGATION_TERMS = {"not", "no", "never", "cannot", "can't", "won't", "without"}

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @property
    def agent_id(self) -> str:
        return "retrieval_reasoning_agent"

    @property
    def agent_version(self) -> str:
        return "1.0.0"

    def get_available_tools(self) -> List[ToolDefinition]:
        # This agent is corpus-driven for now and does not issue tool calls directly.
        return []

    async def validate_tool_call(self, tool_call: ToolCall) -> bool:
        return False

    async def process_message(self, message: AgentMessage, context: SharedContext) -> ExecutionTrace:
        """Run retrieval pipeline and return evidence-backed reasoning output."""
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
            query = message.content.strip()
            corpus = self._load_corpus(context, message)

            pipeline = self._run_retrieval_pipeline(query=query, corpus=corpus)
            selected_chunks = pipeline["selected_chunks"]

            if pipeline["failure_mode"] is not None:
                trace.status = "failed"
                trace.error_message = pipeline["failure_message"]
                trace.final_output = {
                    "query": query,
                    "status": "failed",
                    "answer": None,
                    "failure_mode": pipeline["failure_mode"],
                    "failure_message": pipeline["failure_message"],
                    "retrieval_pipeline": pipeline["pipeline"],
                    "retrieval_reasoning_chain": pipeline["reasoning_chain"],
                    "citation_mapping": {},
                    "claims": [],
                    "source_contribution_mapping": {},
                    "provenance": {
                        "selected_chunks": [],
                        "conflicts": [],
                        "selection_policy": {
                            "min_chunks_required": self.MIN_CHUNKS_REQUIRED,
                            "relevance_threshold": self.RELEVANCE_THRESHOLD,
                        },
                    },
                }
                return trace

            claims, citation_mapping = self._build_claims_and_citations(query, selected_chunks)
            contribution_map = self._build_source_contribution_map(selected_chunks, claims)
            conflicts = self._detect_conflicts(selected_chunks)

            answer = self._compose_answer(claims, conflicts)

            trace.status = "completed"
            trace.final_output = {
                "query": query,
                "status": "completed",
                "answer": answer,
                "retrieval_pipeline": pipeline["pipeline"],
                "retrieval_reasoning_chain": pipeline["reasoning_chain"],
                "claims": claims,
                "citation_mapping": citation_mapping,
                "source_contribution_mapping": contribution_map,
                "provenance": {
                    "selected_chunks": [
                        {
                            "chunk_id": c["chunk_id"],
                            "source_id": c["source_id"],
                            "source_title": c["source_title"],
                            "score": c["score"],
                            "hop_index": c["hop_index"],
                            "selected_reason": c["selected_reason"],
                        }
                        for c in selected_chunks
                    ],
                    "conflicts": conflicts,
                    "selection_policy": {
                        "min_chunks_required": self.MIN_CHUNKS_REQUIRED,
                        "relevance_threshold": self.RELEVANCE_THRESHOLD,
                    },
                },
            }
            return trace

        except Exception as exc:
            trace.status = "failed"
            trace.error_message = str(exc)
            trace.final_output = {
                "query": message.content,
                "status": "failed",
                "failure_mode": "runtime_error",
                "failure_message": str(exc),
            }
            self.logger.error("Retrieval reasoning failed: %s", exc, exc_info=True)
            return trace
        finally:
            trace.completed_at = datetime.utcnow()
            trace.total_duration_ms = (time.time() - start_time) * 1000

    def _load_corpus(self, context: SharedContext, message: AgentMessage) -> List[Dict[str, Any]]:
        """
        Load candidate chunks from context and message metadata.

        Supported sources:
        - context.facts["retrieval_chunks"]
        - context.resources["retrieval"]["chunks"]
        - message.metadata["retrieval_chunks"]
        """
        raw_chunks: List[Any] = []

        facts_chunks = context.facts.get("retrieval_chunks") if context.facts else None
        if isinstance(facts_chunks, list):
            raw_chunks.extend(facts_chunks)

        retrieval_resource = context.resources.get("retrieval", {}) if context.resources else {}
        resource_chunks = retrieval_resource.get("chunks") if isinstance(retrieval_resource, dict) else None
        if isinstance(resource_chunks, list):
            raw_chunks.extend(resource_chunks)

        metadata_chunks = message.metadata.get("retrieval_chunks") if message.metadata else None
        if isinstance(metadata_chunks, list):
            raw_chunks.extend(metadata_chunks)

        corpus: List[Dict[str, Any]] = []
        for i, item in enumerate(raw_chunks):
            if isinstance(item, str):
                content = item.strip()
                if not content:
                    continue
                corpus.append(
                    {
                        "chunk_id": f"chunk_{i+1}",
                        "source_id": "unknown_source",
                        "source_title": "Untitled source",
                        "content": content,
                        "metadata": {},
                    }
                )
                continue

            if isinstance(item, dict):
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                corpus.append(
                    {
                        "chunk_id": str(item.get("chunk_id", f"chunk_{i+1}")),
                        "source_id": str(item.get("source_id", "unknown_source")),
                        "source_title": str(item.get("source_title", "Untitled source")),
                        "content": content,
                        "metadata": item.get("metadata", {}),
                    }
                )

        # Ensure stable uniqueness by chunk_id.
        unique_by_id: Dict[str, Dict[str, Any]] = {}
        for chunk in corpus:
            unique_by_id[chunk["chunk_id"]] = chunk
        return list(unique_by_id.values())

    def _run_retrieval_pipeline(self, query: str, corpus: List[Dict[str, Any]]) -> Dict[str, Any]:
        pipeline: Dict[str, Any] = {
            "hops": [],
            "reformulations": [],
            "minimum_chunks_required": self.MIN_CHUNKS_REQUIRED,
        }
        reasoning_chain: List[Dict[str, Any]] = []

        if not corpus:
            return {
                "selected_chunks": [],
                "pipeline": pipeline,
                "reasoning_chain": reasoning_chain,
                "failure_mode": "empty_retrieval",
                "failure_message": "No retrieval corpus is available in context.",
            }

        selected_by_id: Dict[str, Dict[str, Any]] = {}
        current_query = query
        used_terms: Set[str] = set()

        for hop_index in range(1, self.DEFAULT_MAX_HOPS + 1):
            hop_record = {
                "hop_index": hop_index,
                "query": current_query,
                "retries": [],
                "selected_chunk_ids": [],
            }

            ranked = self._rank_chunks(current_query, corpus, exclude_ids=set(selected_by_id.keys()))
            if self._is_irrelevant(ranked):
                # Retry with reformulations.
                retry_success = False
                for retry_index in range(1, self.DEFAULT_MAX_RETRIES + 1):
                    current_query = self._reformulate_query(query, current_query, selected_by_id.values(), used_terms)
                    pipeline["reformulations"].append(
                        {
                            "hop_index": hop_index,
                            "retry": retry_index,
                            "reformulated_query": current_query,
                            "reason": "low_relevance_or_empty",
                        }
                    )
                    retried_ranked = self._rank_chunks(
                        current_query,
                        corpus,
                        exclude_ids=set(selected_by_id.keys()),
                    )
                    hop_record["retries"].append(
                        {
                            "retry": retry_index,
                            "query": current_query,
                            "top_score": retried_ranked[0]["score"] if retried_ranked else 0.0,
                        }
                    )
                    if not self._is_irrelevant(retried_ranked):
                        ranked = retried_ranked
                        retry_success = True
                        break
                if not retry_success and self._is_irrelevant(ranked):
                    if len(selected_by_id) >= self.MIN_CHUNKS_REQUIRED:
                        pipeline["hops"].append(hop_record)
                        break
                    pipeline["hops"].append(hop_record)
                    if 0 < len(selected_by_id) < self.MIN_CHUNKS_REQUIRED:
                        return {
                            "selected_chunks": list(selected_by_id.values()),
                            "pipeline": pipeline,
                            "reasoning_chain": reasoning_chain,
                            "failure_mode": "insufficient_evidence",
                            "failure_message": "At least two retrieved chunks are required before generating an answer.",
                        }
                    failure_mode = "irrelevant_retrieval" if ranked else "empty_retrieval"
                    return {
                        "selected_chunks": list(selected_by_id.values()),
                        "pipeline": pipeline,
                        "reasoning_chain": reasoning_chain,
                        "failure_mode": failure_mode,
                        "failure_message": "Retrieved chunks are missing or not relevant enough to answer.",
                    }

            hop_selected = ranked[: self.DEFAULT_TOP_K]
            for candidate in hop_selected:
                cid = candidate["chunk_id"]
                if cid in selected_by_id:
                    continue
                candidate["hop_index"] = hop_index
                selected_by_id[cid] = candidate
                used_terms.update(candidate["matched_terms"])

            hop_record["selected_chunk_ids"] = [c["chunk_id"] for c in hop_selected]
            hop_record["selection_rationale"] = [
                {
                    "chunk_id": c["chunk_id"],
                    "score": c["score"],
                    "reason": c["selected_reason"],
                }
                for c in hop_selected
            ]
            pipeline["hops"].append(hop_record)

            reasoning_chain.append(
                {
                    "step": len(reasoning_chain) + 1,
                    "type": "retrieval_hop",
                    "description": f"Hop {hop_index} selected {len(hop_selected)} chunks based on lexical overlap and source diversity.",
                    "used_chunks": [c["chunk_id"] for c in hop_selected],
                }
            )

            # Continue to second hop for explicit multi-hop behavior.
            if hop_index < self.DEFAULT_MAX_HOPS:
                current_query = self._reformulate_query(query, current_query, selected_by_id.values(), used_terms)

        selected_chunks = list(selected_by_id.values())
        if len(selected_chunks) < self.MIN_CHUNKS_REQUIRED:
            return {
                "selected_chunks": selected_chunks,
                "pipeline": pipeline,
                "reasoning_chain": reasoning_chain,
                "failure_mode": "insufficient_evidence",
                "failure_message": "At least two retrieved chunks are required before generating an answer.",
            }

        return {
            "selected_chunks": selected_chunks,
            "pipeline": pipeline,
            "reasoning_chain": reasoning_chain,
            "failure_mode": None,
            "failure_message": None,
        }

    def _rank_chunks(
        self,
        query: str,
        corpus: List[Dict[str, Any]],
        exclude_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        query_terms = self._tokenize(query)
        ranked: List[Dict[str, Any]] = []

        for chunk in corpus:
            if chunk["chunk_id"] in exclude_ids:
                continue

            content = chunk["content"]
            content_terms = self._tokenize(content)
            overlap = sorted(query_terms & content_terms)
            if not query_terms:
                base_score = 0.0
            else:
                base_score = len(overlap) / len(query_terms)

            # Light bonus for exact query phrase appearance.
            phrase_bonus = 0.15 if query.lower() in content.lower() else 0.0
            score = round(base_score + phrase_bonus, 4)

            if score <= 0:
                continue

            ranked.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "source_id": chunk["source_id"],
                    "source_title": chunk["source_title"],
                    "content": content,
                    "metadata": chunk.get("metadata", {}),
                    "score": score,
                    "matched_terms": overlap,
                    "selected_reason": self._selection_reason(score, overlap, chunk),
                    "hop_index": 0,
                }
            )

        ranked.sort(key=lambda item: item["score"], reverse=True)
        for idx, item in enumerate(ranked):
            # Set hop rank to preserve deterministic order in provenance.
            item["rank"] = idx + 1
        return ranked

    def _is_irrelevant(self, ranked: List[Dict[str, Any]]) -> bool:
        if not ranked:
            return True
        return ranked[0]["score"] < self.RELEVANCE_THRESHOLD

    def _reformulate_query(
        self,
        original_query: str,
        current_query: str,
        selected_chunks: Any,
        used_terms: Set[str],
    ) -> str:
        original_terms = self._tokenize(original_query)
        remaining_terms = sorted(original_terms - used_terms)
        if remaining_terms:
            return f"{current_query} evidence {' '.join(remaining_terms[:5])}".strip()

        # If no uncovered terms, nudge toward explanatory detail.
        return f"{current_query} supporting evidence details".strip()

    def _build_claims_and_citations(
        self,
        query: str,
        selected_chunks: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        """
        Build claim list and explicit claim->chunk citation mapping.

        Claims are generated from top chunk sentences aligned to query terms.
        """
        claims: List[Dict[str, Any]] = []
        citation_mapping: Dict[str, List[str]] = {}
        query_terms = self._tokenize(query)

        sorted_chunks = sorted(selected_chunks, key=lambda c: c["score"], reverse=True)
        for i, chunk in enumerate(sorted_chunks[: max(self.MIN_CHUNKS_REQUIRED, 3)]):
            sentence = self._best_sentence(chunk["content"], query_terms)
            claim_id = f"C{i + 1}"

            supporting_chunks = [chunk["chunk_id"]]
            # Attach one additional chunk for each claim when available.
            for peer in sorted_chunks:
                if peer["chunk_id"] == chunk["chunk_id"]:
                    continue
                if self._tokenize(sentence) & self._tokenize(peer["content"]):
                    supporting_chunks.append(peer["chunk_id"])
                if len(supporting_chunks) >= 2:
                    break

            claim_text = sentence if sentence else chunk["content"][:180]
            contribution_map = [
                {
                    "chunk_id": cid,
                    "contribution": f"Provides evidence for claim {claim_id} via lexical overlap and contextual support.",
                }
                for cid in supporting_chunks
            ]

            claim = {
                "claim_id": claim_id,
                "text": claim_text,
                "citations": supporting_chunks,
                "contribution_map": contribution_map,
                "selection_explanation": (
                    f"Claim derived from chunk {chunk['chunk_id']} because it matched query terms "
                    f"{chunk['matched_terms']} with score {chunk['score']}."
                ),
            }
            claims.append(claim)
            citation_mapping[claim_id] = supporting_chunks

        return claims, citation_mapping

    def _build_source_contribution_map(
        self,
        selected_chunks: List[Dict[str, Any]],
        claims: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        contribution_map: Dict[str, Dict[str, Any]] = {}
        for chunk in selected_chunks:
            chunk_id = chunk["chunk_id"]
            contributes_to = [c["claim_id"] for c in claims if chunk_id in c["citations"]]
            contribution_map[chunk_id] = {
                "source_id": chunk["source_id"],
                "source_title": chunk["source_title"],
                "score": chunk["score"],
                "selected_reason": chunk["selected_reason"],
                "claims": contributes_to,
                "contribution_summary": (
                    "Primary evidence" if contributes_to else "Contextual background evidence"
                ),
            }
        return contribution_map

    def _detect_conflicts(self, selected_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        for i in range(len(selected_chunks)):
            a = selected_chunks[i]
            a_terms = self._tokenize(a["content"])
            a_neg = bool(a_terms & self.NEGATION_TERMS)

            for j in range(i + 1, len(selected_chunks)):
                b = selected_chunks[j]
                b_terms = self._tokenize(b["content"])
                b_neg = bool(b_terms & self.NEGATION_TERMS)

                shared = (a_terms & b_terms) - self.NEGATION_TERMS
                if a_neg != b_neg and len(shared) >= 3:
                    conflicts.append(
                        {
                            "chunk_a": a["chunk_id"],
                            "chunk_b": b["chunk_id"],
                            "reason": "Potential contradiction detected: overlapping topic terms with opposite polarity.",
                            "shared_terms": sorted(list(shared))[:8],
                        }
                    )
        return conflicts

    def _compose_answer(self, claims: List[Dict[str, Any]], conflicts: List[Dict[str, Any]]) -> str:
        if not claims:
            return "Insufficient evidence to produce an answer."

        claim_lines = []
        for claim in claims:
            citations = ", ".join(claim["citations"])
            claim_lines.append(f"- {claim['text']} [{citations}]")

        answer = "Evidence-backed answer:\n" + "\n".join(claim_lines)
        if conflicts:
            answer += "\n\nNote: Conflicting evidence was detected across sources; review provenance.conflicts."
        return answer

    def _best_sentence(self, content: str, query_terms: Set[str]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        best = ""
        best_score = -1
        for sentence in sentences:
            score = len(self._tokenize(sentence) & query_terms)
            if score > best_score:
                best = sentence.strip()
                best_score = score
        return best

    def _selection_reason(self, score: float, overlap: List[str], chunk: Dict[str, Any]) -> str:
        if overlap:
            overlap_text = ", ".join(overlap[:6])
            return (
                f"Selected due to relevance score {score} with matched terms: {overlap_text}; "
                f"source={chunk['source_id']}."
            )
        return f"Selected as fallback evidence with score {score}; source={chunk['source_id']}."

    def _tokenize(self, text: str) -> Set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
            if len(token) >= 3
        }
