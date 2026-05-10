"""
Context window management for orchestration.

This module centralizes:
- token estimation
- dynamic budget checks
- context compression
- structured-data-preserving summarization
- overflow enforcement

Structured data is preserved losslessly whenever possible. Conversational text
is the primary compression target.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..schemas import AgentMessage, SharedContext
from .schemas import PolicyViolation, PolicyViolationType


TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_PATTERN = re.compile(r"\s+")

FILLER_PHRASES = (
    "sort of",
    "kind of",
    "basically",
    "actually",
    "maybe",
    "just",
    "really",
    "very",
    "perhaps",
    "I think",
    "you know",
    "like",
)

LOSSLESS_CONTEXT_KEYS = {"facts", "constraints", "resources", "metadata", "user_id", "user_preferences"}


@dataclass
class TokenEstimate:
    """Token estimate for a payload."""

    prompt_tokens: int
    completion_tokens: int = 0
    breakdown: Dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class BudgetCheckResult:
    """Result of checking whether an agent can execute within budget."""

    agent_id: str
    allowed: bool
    estimated_tokens: int
    remaining_total_tokens: int
    remaining_agent_tokens: int
    projected_total_tokens: int
    projected_agent_tokens: int
    reason: str
    policy_violation: Optional[PolicyViolation] = None


@dataclass
class CompressionResult:
    """Outcome of compressing a payload."""

    original_tokens: int
    compressed_tokens: int
    compression_applied: bool
    lossy_fields: List[str] = field(default_factory=list)
    preserved_fields: List[str] = field(default_factory=list)


@dataclass
class PreparedAgentContext:
    """Agent message/context prepared for execution."""

    message: AgentMessage
    context: SharedContext
    token_estimate: TokenEstimate
    budget_check: BudgetCheckResult
    compression_result: CompressionResult


class TokenEstimator:
    """Heuristic token estimator.

    The implementation is intentionally dependency-free and deterministic.
    """

    def estimate_text(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(TOKEN_PATTERN.findall(text)))

    def estimate_value(self, value: Any) -> int:
        if value is None:
            return 1
        if isinstance(value, bool):
            return 1
        if isinstance(value, (int, float)):
            return 2
        if isinstance(value, str):
            return self.estimate_text(value)
        if isinstance(value, dict):
            total = 2
            for key, nested_value in value.items():
                total += self.estimate_text(str(key))
                total += self.estimate_value(nested_value)
            return total
        if isinstance(value, (list, tuple, set)):
            total = 2
            for item in value:
                total += self.estimate_value(item)
            return total
        return self.estimate_text(str(value))

    def estimate_payload(self, payload: Any) -> TokenEstimate:
        prompt_tokens = self.estimate_value(payload)
        return TokenEstimate(prompt_tokens=prompt_tokens, breakdown={"prompt": prompt_tokens})


class StructuredDataPreservingSummarizer:
    """Lossy summarizer for conversational text that preserves structured values."""

    def summarize_text(self, text: str, max_tokens: int) -> str:
        if not text:
            return text

        normalized = WHITESPACE_PATTERN.sub(" ", text).strip()
        if self._looks_structured(normalized):
            return normalized

        cleaned = self._remove_fillers(normalized)
        sentences = [sentence.strip() for sentence in SENTENCE_PATTERN.split(cleaned) if sentence.strip()]
        if not sentences:
            sentences = [cleaned]

        key_sentences = self._select_key_sentences(sentences)
        summary = " ".join(key_sentences).strip()
        if not summary:
            summary = cleaned

        return self._trim_to_token_budget(summary, max_tokens)

    def summarize_message_content(self, message: AgentMessage, max_tokens: int) -> AgentMessage:
        compressed_content = self.summarize_text(message.content, max_tokens)
        return message.model_copy(update={"content": compressed_content}, deep=True)

    def summarize_context(self, context: SharedContext, max_tokens: int) -> SharedContext:
        payload = context.model_dump()
        compressed_payload, _, _ = self._compress_structure(payload, max_tokens=max_tokens, path=())
        return SharedContext.model_validate(compressed_payload)

    def _compress_structure(
        self,
        value: Any,
        *,
        max_tokens: int,
        path: Tuple[str, ...],
    ) -> Tuple[Any, List[str], List[str]]:
        preserved_fields: List[str] = []
        lossy_fields: List[str] = []

        if isinstance(value, dict):
            compressed: Dict[str, Any] = {}
            for key, nested_value in value.items():
                child_path = path + (key,)
                child_path_name = ".".join(child_path)
                if key in LOSSLESS_CONTEXT_KEYS:
                    compressed[key] = nested_value
                    preserved_fields.append(child_path_name)
                    continue

                compressed_value, child_preserved, child_lossy = self._compress_structure(
                    nested_value,
                    max_tokens=max_tokens,
                    path=child_path,
                )
                compressed[key] = compressed_value
                preserved_fields.extend(child_preserved)
                lossy_fields.extend(child_lossy)
            return compressed, preserved_fields, lossy_fields

        if isinstance(value, list):
            compressed_list: List[Any] = []
            for index, item in enumerate(value):
                compressed_item, child_preserved, child_lossy = self._compress_structure(
                    item,
                    max_tokens=max_tokens,
                    path=path + (str(index),),
                )
                compressed_list.append(compressed_item)
                preserved_fields.extend(child_preserved)
                lossy_fields.extend(child_lossy)
            return compressed_list, preserved_fields, lossy_fields

        if isinstance(value, str):
            if self._looks_structured(value) or self._should_preserve_text(path):
                preserved_fields.append(".".join(path))
                return value, preserved_fields, lossy_fields
            lossy_fields.append(".".join(path))
            return self.summarize_text(value, max_tokens=max_tokens), preserved_fields, lossy_fields

        return value, preserved_fields, lossy_fields

    def _should_preserve_text(self, path: Tuple[str, ...]) -> bool:
        return any(part in {"facts", "constraints", "resources", "metadata", "agent_outputs", "retrieval_chunks"} for part in path)

    def _looks_structured(self, text: str) -> bool:
        stripped = text.lstrip()
        return stripped.startswith(("{", "[", "<")) or (":" in stripped and "\n" in stripped)

    def _remove_fillers(self, text: str) -> str:
        cleaned = text
        for phrase in FILLER_PHRASES:
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", "", cleaned, flags=re.IGNORECASE)
        return WHITESPACE_PATTERN.sub(" ", cleaned).strip()

    def _select_key_sentences(self, sentences: Iterable[str]) -> List[str]:
        sentence_list = list(sentences)
        selected: List[str] = []
        for sentence in sentence_list:
            if sentence not in selected:
                selected.append(sentence)
            if len(selected) >= 2:
                break
        if len(selected) == 1 and len(sentence_list) > 1:
            selected.append(sentence_list[-1])
        return selected

    def _trim_to_token_budget(self, text: str, max_tokens: int) -> str:
        tokens = TOKEN_PATTERN.findall(text)
        if len(tokens) <= max_tokens:
            return text
        trimmed = tokens[:max_tokens]
        return re.sub(r"\s+([,.;:!?])", r"\1", " ".join(trimmed)).strip()


class CompressionPipeline:
    """Compression pipeline for context window management."""

    def __init__(self, estimator: Optional[TokenEstimator] = None, summarizer: Optional[StructuredDataPreservingSummarizer] = None):
        self.estimator = estimator or TokenEstimator()
        self.summarizer = summarizer or StructuredDataPreservingSummarizer()

    def compress_message_and_context(
        self,
        message: AgentMessage,
        context: SharedContext,
        *,
        max_tokens: int,
    ) -> Tuple[AgentMessage, SharedContext, CompressionResult]:
        original_payload = self._build_payload(message, context)
        original_tokens = self.estimator.estimate_payload(original_payload).total_tokens

        if original_tokens <= max_tokens:
            return (
                message.model_copy(deep=True),
                context.model_copy(deep=True),
                CompressionResult(
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    compression_applied=False,
                ),
            )

        compressed_message = self.summarizer.summarize_message_content(message, max_tokens=max(16, max_tokens // 4))
        compressed_context = self.summarizer.summarize_context(
            context,
            max_tokens=max(32, max_tokens - self.estimator.estimate_text(compressed_message.content)),
        )

        compressed_payload = self._build_payload(compressed_message, compressed_context)
        compressed_tokens = self.estimator.estimate_payload(compressed_payload).total_tokens

        _, preserved_fields, lossy_fields = self.summarizer._compress_structure(
            context.model_dump(),
            max_tokens=max_tokens,
            path=(),
        )

        return (
            compressed_message,
            compressed_context,
            CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_applied=True,
                preserved_fields=preserved_fields,
                lossy_fields=lossy_fields,
            ),
        )

    def _build_payload(self, message: AgentMessage, context: SharedContext) -> Dict[str, Any]:
        return {
            "content": message.content,
            "metadata": message.metadata,
            "context": context.model_dump(),
        }


class BudgetManager:
    """Tracks token budgets per agent and globally."""

    def __init__(self, total_budget_tokens: int, default_agent_budget_tokens: Optional[int] = None):
        self.total_budget_tokens = max(1, int(total_budget_tokens))
        self.default_agent_budget_tokens = max(1, int(default_agent_budget_tokens or total_budget_tokens))
        self._agent_budgets: Dict[str, int] = {}
        self._agent_usage: Dict[str, int] = defaultdict(int)
        self._total_usage: int = 0

    def set_agent_budget(self, agent_id: str, token_budget: Optional[int] = None) -> None:
        self._agent_budgets[agent_id] = max(1, int(token_budget or self.default_agent_budget_tokens))

    def remaining_total_tokens(self) -> int:
        return max(0, self.total_budget_tokens - self._total_usage)

    def remaining_agent_tokens(self, agent_id: str) -> int:
        agent_budget = self._agent_budgets.get(agent_id, self.default_agent_budget_tokens)
        return max(0, agent_budget - self._agent_usage.get(agent_id, 0))

    def check_agent_budget(self, agent_id: str, estimated_tokens: int) -> BudgetCheckResult:
        if agent_id not in self._agent_budgets:
            self.set_agent_budget(agent_id)

        projected_total_tokens = self._total_usage + estimated_tokens
        projected_agent_tokens = self._agent_usage.get(agent_id, 0) + estimated_tokens
        remaining_total = self.remaining_total_tokens()
        remaining_agent = self.remaining_agent_tokens(agent_id)

        allowed = projected_total_tokens <= self.total_budget_tokens and projected_agent_tokens <= self._agent_budgets[agent_id]
        if allowed:
            reason = "within_budget"
            violation = None
        else:
            if projected_total_tokens > self.total_budget_tokens and projected_agent_tokens > self._agent_budgets[agent_id]:
                reason = "agent_and_total_budget_exceeded"
            elif projected_total_tokens > self.total_budget_tokens:
                reason = "total_budget_exceeded"
            else:
                reason = "agent_budget_exceeded"

            violation = PolicyViolation(
                violation_type=PolicyViolationType.BUDGET_EXCEEDED,
                message=f"Agent {agent_id} would exceed its token budget",
                agent_id=agent_id,
                details={
                    "estimated_tokens": estimated_tokens,
                    "projected_total_tokens": projected_total_tokens,
                    "projected_agent_tokens": projected_agent_tokens,
                    "remaining_total_tokens": remaining_total,
                    "remaining_agent_tokens": remaining_agent,
                },
                severity=1.0,
            )

        return BudgetCheckResult(
            agent_id=agent_id,
            allowed=allowed,
            estimated_tokens=estimated_tokens,
            remaining_total_tokens=remaining_total,
            remaining_agent_tokens=remaining_agent,
            projected_total_tokens=projected_total_tokens,
            projected_agent_tokens=projected_agent_tokens,
            reason=reason,
            policy_violation=violation,
        )

    def record_usage(self, agent_id: str, prompt_tokens: int, completion_tokens: int = 0) -> Dict[str, int]:
        total_tokens = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        self._agent_usage[agent_id] += total_tokens
        self._total_usage += total_tokens
        return {
            "prompt": max(0, int(prompt_tokens)),
            "completion": max(0, int(completion_tokens)),
            "total": total_tokens,
        }

    def get_agent_usage(self) -> Dict[str, int]:
        return dict(self._agent_usage)

    def get_total_usage(self) -> int:
        return self._total_usage


class OverflowEnforcer:
    """Raises policy violations when compressed content still exceeds budget."""

    def __init__(self, budget_manager: BudgetManager, estimator: Optional[TokenEstimator] = None):
        self.budget_manager = budget_manager
        self.estimator = estimator or TokenEstimator()

    def enforce(self, agent_id: str, message: AgentMessage, context: SharedContext) -> BudgetCheckResult:
        payload = {
            "content": message.content,
            "metadata": message.metadata,
            "context": context.model_dump(),
        }
        token_estimate = self.estimator.estimate_payload(payload).total_tokens
        return self.budget_manager.check_agent_budget(agent_id, token_estimate)


class ContextWindowManager:
    """Facade that combines estimation, compression, budget checks, and overflow enforcement."""

    def __init__(self, total_budget_tokens: int, default_agent_budget_tokens: Optional[int] = None):
        self.estimator = TokenEstimator()
        self.summarizer = StructuredDataPreservingSummarizer()
        self.compression_pipeline = CompressionPipeline(self.estimator, self.summarizer)
        self.budget_manager = BudgetManager(total_budget_tokens, default_agent_budget_tokens)
        self.overflow_enforcer = OverflowEnforcer(self.budget_manager, self.estimator)

    def register_agent(self, agent_id: str, token_budget: Optional[int] = None) -> None:
        self.budget_manager.set_agent_budget(agent_id, token_budget)

    def prepare_agent_input(
        self,
        agent_id: str,
        message: AgentMessage,
        context: SharedContext,
        *,
        token_budget: Optional[int] = None,
    ) -> PreparedAgentContext:
        self.register_agent(agent_id, token_budget)

        compressed_message, compressed_context, compression_result = self.compression_pipeline.compress_message_and_context(
            message,
            context,
            max_tokens=self.budget_manager.remaining_agent_tokens(agent_id),
        )

        token_estimate = self.estimator.estimate_payload(
            {
                "content": compressed_message.content,
                "metadata": compressed_message.metadata,
                "context": compressed_context.model_dump(),
            }
        )

        budget_check = self.budget_manager.check_agent_budget(agent_id, token_estimate.total_tokens)
        if not budget_check.allowed and budget_check.policy_violation is not None:
            budget_check.policy_violation.details.update(
                {
                    "compression_applied": compression_result.compression_applied,
                    "original_tokens": compression_result.original_tokens,
                    "compressed_tokens": compression_result.compressed_tokens,
                    "preserved_fields": compression_result.preserved_fields,
                    "lossy_fields": compression_result.lossy_fields,
                }
            )

        return PreparedAgentContext(
            message=compressed_message,
            context=compressed_context,
            token_estimate=token_estimate,
            budget_check=budget_check,
            compression_result=compression_result,
        )
