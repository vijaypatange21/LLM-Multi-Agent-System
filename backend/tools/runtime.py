"""Tool runtime infrastructure for validation, retries, logging, and trace storage."""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

from ..core import BaseTool
from ..schemas import (
    SharedContext,
    ToolCall,
    ToolCallDecision,
    ToolDefinition,
    ToolExecutionAttempt,
    ToolExecutionTrace,
    ToolResult,
    ToolResultStatus,
    ToolRetryOutcome,
    ToolValidationIssue,
    ToolValidationResult,
)


class ToolValidationError(Exception):
    """Raised when a tool call cannot be validated or executed."""


@dataclass(frozen=True)
class RetryDecision:
    """Retry policy outcome for a tool execution attempt."""

    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class FallbackStrategy:
    """Ordered fallback strategy when the primary tool fails."""

    fallback_tool_ids: Sequence[str] = ()
    max_fallback_depth: int = 1


class ToolExecutionStore:
    """Abstract storage interface for tool execution traces."""

    async def record_trace(self, trace: ToolExecutionTrace) -> None:
        raise NotImplementedError

    async def get_trace(self, tool_call_id: UUID) -> Optional[ToolExecutionTrace]:
        raise NotImplementedError

    async def list_traces(self) -> List[ToolExecutionTrace]:
        raise NotImplementedError


class InMemoryToolExecutionStore(ToolExecutionStore):
    """In-memory storage for tool execution traces."""

    def __init__(self):
        self._traces: Dict[UUID, ToolExecutionTrace] = {}

    async def record_trace(self, trace: ToolExecutionTrace) -> None:
        self._traces[trace.tool_call_id] = trace

    async def get_trace(self, tool_call_id: UUID) -> Optional[ToolExecutionTrace]:
        return self._traces.get(tool_call_id)

    async def list_traces(self) -> List[ToolExecutionTrace]:
        return list(self._traces.values())


class ToolExecutionTraceStore(InMemoryToolExecutionStore):
    """Alias-compatible store for tool execution traces."""


class ToolRegistry:
    """Registry for discovered tools and their definitions."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.get_definition().id] = tool

    def get(self, tool_id: str) -> Optional[BaseTool]:
        return self._tools.get(tool_id)

    def list(self) -> List[BaseTool]:
        return list(self._tools.values())


class ToolResultValidator:
    """Compatibility wrapper for validating tool outputs."""

    @staticmethod
    def validate(result: ToolResult, tool_definition: ToolDefinition) -> ToolValidationResult:
        return ToolValidationManager.validate_tool_result(result, tool_definition)


class ToolExecutionLogger:
    """Structured logging helper for tool execution and retries."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def log_attempt(self, *, level: int, message: str, trace: ToolExecutionTrace, attempt: ToolExecutionAttempt, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "trace_id": str(trace.id),
            "tool_call_id": str(trace.tool_call_id),
            "tool_id": trace.tool_id,
            "agent_id": trace.agent_id,
            "attempt_number": attempt.attempt_number,
            "latency_ms": attempt.latency_ms,
            "status": attempt.status.value,
            "decision": attempt.decision.value,
            "outcome": attempt.outcome.value,
        }
        if extra:
            payload.update(extra)
        self.logger.log(level, message, extra=payload)

    def log_validation(self, *, trace_id: UUID, tool_id: str, agent_id: str, accepted: bool, reason: str, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "trace_id": str(trace_id),
            "tool_id": tool_id,
            "agent_id": agent_id,
            "accepted": accepted,
            "reason": reason,
        }
        if extra:
            payload.update(extra)
        level = logging.INFO if accepted else logging.WARNING
        self.logger.log(level, "Tool call validation", extra=payload)


class ToolValidationManager:
    """Validates tool calls and tool results against their schemas."""

    @staticmethod
    def validate_tool_call(tool_call: ToolCall, tool_definition: ToolDefinition) -> ToolValidationResult:
        issues: List[ToolValidationIssue] = []
        if not isinstance(tool_call.arguments, dict):
            issues.append(
                ToolValidationIssue(
                    field="arguments",
                    issue="Tool arguments must be a dictionary",
                    expected="object",
                    actual=type(tool_call.arguments).__name__,
                )
            )
            return ToolValidationResult(is_valid=False, issues=issues, normalized_arguments={})

        normalized = dict(tool_call.arguments)

        schema = tool_definition.input_schema or {}
        ToolValidationManager._validate_schema(schema, normalized, issues, path="arguments")

        return ToolValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            normalized_arguments=normalized,
            rejected_reason="; ".join(issue.issue for issue in issues) if issues else None,
        )

    @staticmethod
    def validate_tool_result(result: ToolResult, tool_definition: ToolDefinition) -> ToolValidationResult:
        issues: List[ToolValidationIssue] = []
        if result.status != ToolResultStatus.SUCCESS and result.output is None:
            issues.append(
                ToolValidationIssue(
                    field="output",
                    issue=f"Tool returned non-success status {result.status.value} without output",
                    expected="output for successful or partial responses",
                    actual="None",
                )
            )

        if result.output is not None:
            ToolValidationManager._validate_schema(tool_definition.output_schema or {}, result.output, issues, path="output")

        return ToolValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            normalized_arguments=result.output or {},
            rejected_reason="; ".join(issue.issue for issue in issues) if issues else None,
        )

    @staticmethod
    def _validate_schema(schema: Dict[str, Any], value: Any, issues: List[ToolValidationIssue], path: str) -> None:
        if not isinstance(schema, dict):
            return

        schema_type = schema.get("type")
        if schema_type == "object":
            if not isinstance(value, dict):
                issues.append(
                    ToolValidationIssue(
                        field=path,
                        issue="Expected object",
                        expected="object",
                        actual=type(value).__name__,
                    )
                )
                return

            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    issues.append(
                        ToolValidationIssue(
                            field=f"{path}.{key}",
                            issue="Missing required field",
                            expected="present",
                            actual="missing",
                        )
                    )

            properties = schema.get("properties", {})
            if isinstance(properties, dict):
                for key, prop_schema in properties.items():
                    if key in value:
                        ToolValidationManager._validate_schema(prop_schema, value[key], issues, path=f"{path}.{key}")
            return

        if schema_type == "array":
            if not isinstance(value, list):
                issues.append(
                    ToolValidationIssue(
                        field=path,
                        issue="Expected array",
                        expected="array",
                        actual=type(value).__name__,
                    )
                )
                return
            item_schema = schema.get("items")
            if item_schema:
                for index, item in enumerate(value):
                    ToolValidationManager._validate_schema(item_schema, item, issues, path=f"{path}[{index}]")
            return

        if schema_type == "string" and not isinstance(value, str):
            issues.append(ToolValidationIssue(field=path, issue="Expected string", expected="string", actual=type(value).__name__))
        elif schema_type == "integer" and not isinstance(value, int):
            issues.append(ToolValidationIssue(field=path, issue="Expected integer", expected="integer", actual=type(value).__name__))
        elif schema_type == "number" and not isinstance(value, (int, float)):
            issues.append(ToolValidationIssue(field=path, issue="Expected number", expected="number", actual=type(value).__name__))
        elif schema_type == "boolean" and not isinstance(value, bool):
            issues.append(ToolValidationIssue(field=path, issue="Expected boolean", expected="boolean", actual=type(value).__name__))


class RetryManager:
    """Retry policy and backoff manager for tool calls."""

    def __init__(self, max_attempts: int = 3, base_delay_seconds: float = 0.5, max_delay_seconds: float = 8.0, jitter: float = 0.1):
        self.max_attempts = max(1, max_attempts)
        self.base_delay_seconds = max(0.0, base_delay_seconds)
        self.max_delay_seconds = max_delay_seconds
        self.jitter = max(0.0, jitter)

    def should_retry(self, attempt_number: int, result: ToolResult) -> RetryDecision:
        if attempt_number >= self.max_attempts:
            return RetryDecision(False, 0.0, "max_attempts_reached")

        if result.status in {ToolResultStatus.TIMEOUT, ToolResultStatus.RATE_LIMITED}:
            return RetryDecision(True, self._backoff(attempt_number), f"retryable_status:{result.status.value}")

        if result.status == ToolResultStatus.FAILED and self._is_transient_error(result.error_message or ""):
            return RetryDecision(True, self._backoff(attempt_number), "transient_failure")

        return RetryDecision(False, 0.0, "non_retryable")

    def _backoff(self, attempt_number: int) -> float:
        delay = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempt_number - 1)))
        if self.jitter > 0:
            delay += random.uniform(0, delay * self.jitter)
        return delay

    @staticmethod
    def _is_transient_error(error_message: str) -> bool:
        lowered = error_message.lower()
        transient_markers = ["timeout", "temporarily", "rate limit", "unavailable", "connection reset", "try again"]
        return any(marker in lowered for marker in transient_markers)


class ToolExecutor:
    """Centralized tool execution runtime with retries, validation, and trace storage."""

    def __init__(
        self,
        tools: Optional[List[BaseTool]] = None,
        store: Optional[ToolExecutionStore] = None,
        retry_manager: Optional[RetryManager] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.tools: Dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register_tool(tool)
        self.store = store or InMemoryToolExecutionStore()
        self.retry_manager = retry_manager or RetryManager()
        self.logger = ToolExecutionLogger(logger or logging.getLogger(__name__))

    def register_tool(self, tool: BaseTool) -> None:
        self.tools[tool.get_definition().id] = tool

    def get_tool(self, tool_id: str) -> Optional[BaseTool]:
        return self.tools.get(tool_id)

    async def execute_tool(self, tool_call: ToolCall, context: SharedContext) -> ToolResult:
        tool = self.get_tool(tool_call.tool_id)
        trace = ToolExecutionTrace(
            tool_call_id=tool_call.id,
            tool_id=tool_call.tool_id,
            agent_id=tool_call.agent_id,
            accepted=tool is not None,
            rejected_reason=None if tool is not None else f"Tool {tool_call.tool_id} not found",
            final_result_status=ToolResultStatus.FAILED,
            metadata={
                "conversation_id": str(context.conversation_id),
                "tool_version": tool_call.tool_version,
            },
        )

        if not tool:
            result = self._rejected_result(tool_call, "tool_not_found")
            await self.store.record_trace(trace)
            self.logger.log_validation(
                trace_id=trace.id,
                tool_id=tool_call.tool_id,
                agent_id=tool_call.agent_id,
                accepted=False,
                reason="tool_not_found",
            )
            return result

        definition = tool.get_definition()
        validation = ToolValidationManager.validate_tool_call(tool_call, definition)
        trace.accepted = validation.is_valid
        trace.rejected_reason = validation.rejected_reason
        if not validation.is_valid:
            attempt = ToolExecutionAttempt(
                tool_call_id=tool_call.id,
                attempt_number=1,
                decision=ToolCallDecision.REJECTED,
                outcome=ToolRetryOutcome.FAILED,
                status=ToolResultStatus.FAILED,
                latency_ms=0.0,
                error_message=validation.rejected_reason,
                structured_log={
                    "trace_id": str(trace.id),
                    "tool_id": tool_call.tool_id,
                    "agent_id": tool_call.agent_id,
                    "accepted": False,
                    "validation_issues": [issue.model_dump() for issue in validation.issues],
                },
                input_snapshot=validation.normalized_arguments,
            )
            trace.attempts.append(attempt)
            trace.total_attempts = 1
            trace.total_latency_ms = 0.0
            await self.store.record_trace(trace)
            self.logger.log_validation(
                trace_id=trace.id,
                tool_id=tool_call.tool_id,
                agent_id=tool_call.agent_id,
                accepted=False,
                reason=validation.rejected_reason or "validation_failed",
                extra={"validation_issues": [issue.model_dump() for issue in validation.issues]},
            )
            return self._validation_failure_result(tool_call, validation)

        self.logger.log_validation(
            trace_id=trace.id,
            tool_id=tool_call.tool_id,
            agent_id=tool_call.agent_id,
            accepted=True,
            reason="validation_passed",
        )

        result = await self._execute_with_retries(tool, tool_call, context, trace, definition)
        await self.store.record_trace(trace)
        return result

    async def _execute_with_retries(
        self,
        tool: BaseTool,
        tool_call: ToolCall,
        context: SharedContext,
        trace: ToolExecutionTrace,
        definition: ToolDefinition,
    ) -> ToolResult:
        fallback = FallbackStrategy(definition.fallback_tool_ids, max_fallback_depth=max(1, len(definition.fallback_tool_ids)))
        attempt_number = 0
        last_result: Optional[ToolResult] = None

        for fallback_index, tool_id in enumerate([definition.id] + list(fallback.fallback_tool_ids), start=1):
            current_tool = tool if tool_id == definition.id else self.get_tool(tool_id)
            if current_tool is None:
                continue

            current_definition = current_tool.get_definition()
            per_tool_attempt = 0

            while per_tool_attempt < self.retry_manager.max_attempts:
                per_tool_attempt += 1
                attempt_number += 1
                attempt_start = time.time()
                structured_log = {
                    "trace_id": str(trace.id),
                    "tool_call_id": str(tool_call.id),
                    "tool_id": tool_id,
                    "agent_id": tool_call.agent_id,
                    "attempt_number": attempt_number,
                    "fallback_index": fallback_index,
                }
                try:
                    self.logger.log_attempt(
                        level=logging.INFO,
                        message=f"Starting tool attempt {attempt_number} for {tool_id}",
                        trace=trace,
                        attempt=ToolExecutionAttempt(
                            tool_call_id=tool_call.id,
                            attempt_number=attempt_number,
                            decision=ToolCallDecision.ACCEPTED,
                            outcome=ToolRetryOutcome.RETRIED if attempt_number > 1 else ToolRetryOutcome.SUCCEEDED,
                            status=ToolResultStatus.SUCCESS,
                            latency_ms=0.0,
                            structured_log=structured_log,
                            input_snapshot=tool_call.arguments,
                        ),
                    )

                    raw_result = await asyncio.wait_for(
                        current_tool.execute(tool_call, context),
                        timeout=current_definition.timeout_seconds,
                    )
                    latency_ms = (time.time() - attempt_start) * 1000
                    raw_result.execution_metadata = {
                        **(raw_result.execution_metadata or {}),
                        "attempt_number": attempt_number,
                        "tool_id": tool_id,
                        "fallback_index": fallback_index,
                    }
                    validation = ToolValidationManager.validate_tool_result(raw_result, current_tool.get_definition())

                    attempt = ToolExecutionAttempt(
                        tool_call_id=tool_call.id,
                        attempt_number=attempt_number,
                        decision=ToolCallDecision.ACCEPTED,
                        outcome=ToolRetryOutcome.SUCCEEDED if raw_result.status == ToolResultStatus.SUCCESS and validation.is_valid else ToolRetryOutcome.FAILED,
                        status=raw_result.status,
                        latency_ms=latency_ms,
                        error_message=None if validation.is_valid else validation.rejected_reason,
                        structured_log={**structured_log, "status": raw_result.status.value, "validation_issues": [issue.model_dump() for issue in validation.issues]},
                        input_snapshot=tool_call.arguments,
                        output_snapshot=raw_result.output,
                    )
                    trace.attempts.append(attempt)
                    trace.total_latency_ms += latency_ms
                    trace.total_attempts = len(trace.attempts)
                    trace.final_result_status = raw_result.status if validation.is_valid else ToolResultStatus.FAILED

                    self.logger.log_attempt(
                        level=logging.INFO,
                        message=f"Completed tool attempt {attempt_number} for {tool_id}",
                        trace=trace,
                        attempt=attempt,
                        extra={"validation_issues": [issue.model_dump() for issue in validation.issues]},
                    )

                    if raw_result.status == ToolResultStatus.SUCCESS and validation.is_valid:
                        raw_result.execution_metadata = {
                            **raw_result.execution_metadata,
                            "accepted": True,
                            "trace_id": str(trace.id),
                            "tool_call_id": str(tool_call.id),
                        }
                        return raw_result

                    if validation.is_valid:
                        last_result = raw_result
                    else:
                        last_result = ToolResult(
                            tool_call_id=tool_call.id,
                            status=ToolResultStatus.FAILED,
                            output=raw_result.output,
                            error_message=f"Validation failed: {validation.rejected_reason}",
                            execution_time_ms=latency_ms,
                            execution_metadata={
                                **(raw_result.execution_metadata or {}),
                                "validation_issues": [issue.model_dump() for issue in validation.issues],
                            },
                        )

                    retry_decision = self.retry_manager.should_retry(
                        per_tool_attempt,
                        last_result,
                    )
                    if not retry_decision.should_retry:
                        break

                    self.logger.logger.warning(
                        "Retrying tool %s after attempt %s", tool_id, attempt_number, extra={
                            "trace_id": str(trace.id),
                            "tool_call_id": str(tool_call.id),
                            "tool_id": tool_id,
                            "retry_delay_seconds": retry_decision.delay_seconds,
                            "retry_reason": retry_decision.reason,
                            "attempt_number": attempt_number,
                        }
                    )
                    await asyncio.sleep(retry_decision.delay_seconds)

                except asyncio.TimeoutError:
                    latency_ms = (time.time() - attempt_start) * 1000
                    timeout_result = ToolResult(
                        tool_call_id=tool_call.id,
                        status=ToolResultStatus.TIMEOUT,
                        output=None,
                        error_message=f"Tool execution exceeded timeout of {current_definition.timeout_seconds}s",
                        execution_time_ms=latency_ms,
                        execution_metadata={"attempt_number": attempt_number, "tool_id": tool_id, "timeout_seconds": current_definition.timeout_seconds},
                    )
                    attempt = ToolExecutionAttempt(
                        tool_call_id=tool_call.id,
                        attempt_number=attempt_number,
                        decision=ToolCallDecision.ACCEPTED,
                        outcome=ToolRetryOutcome.TIMED_OUT,
                        status=ToolResultStatus.TIMEOUT,
                        latency_ms=latency_ms,
                        error_message=timeout_result.error_message,
                        structured_log={**structured_log, "status": "timeout", "timeout_seconds": current_definition.timeout_seconds},
                        input_snapshot=tool_call.arguments,
                    )
                    trace.attempts.append(attempt)
                    trace.total_latency_ms += latency_ms
                    trace.total_attempts = len(trace.attempts)
                    trace.final_result_status = ToolResultStatus.TIMEOUT
                    self.logger.log_attempt(
                        level=logging.WARNING,
                        message=f"Tool attempt {attempt_number} timed out for {tool_id}",
                        trace=trace,
                        attempt=attempt,
                    )
                    last_result = timeout_result
                    retry_decision = self.retry_manager.should_retry(per_tool_attempt, timeout_result)
                    if not retry_decision.should_retry:
                        break
                    await asyncio.sleep(retry_decision.delay_seconds)

                except Exception as exc:
                    latency_ms = (time.time() - attempt_start) * 1000
                    failed_result = ToolResult(
                        tool_call_id=tool_call.id,
                        status=ToolResultStatus.FAILED,
                        output=None,
                        error_message=str(exc),
                        execution_time_ms=latency_ms,
                        execution_metadata={"attempt_number": attempt_number, "tool_id": tool_id, "exception_type": type(exc).__name__},
                    )
                    attempt = ToolExecutionAttempt(
                        tool_call_id=tool_call.id,
                        attempt_number=attempt_number,
                        decision=ToolCallDecision.ACCEPTED,
                        outcome=ToolRetryOutcome.FAILED,
                        status=ToolResultStatus.FAILED,
                        latency_ms=latency_ms,
                        error_message=str(exc),
                        structured_log={**structured_log, "status": "failed", "exception_type": type(exc).__name__},
                        input_snapshot=tool_call.arguments,
                    )
                    trace.attempts.append(attempt)
                    trace.total_latency_ms += latency_ms
                    trace.total_attempts = len(trace.attempts)
                    trace.final_result_status = ToolResultStatus.FAILED
                    self.logger.log_attempt(
                        level=logging.ERROR,
                        message=f"Tool attempt {attempt_number} failed for {tool_id}",
                        trace=trace,
                        attempt=attempt,
                        extra={"exception_type": type(exc).__name__},
                    )
                    last_result = failed_result
                    retry_decision = self.retry_manager.should_retry(per_tool_attempt, failed_result)
                    if not retry_decision.should_retry:
                        break
                    await asyncio.sleep(retry_decision.delay_seconds)

            if last_result and last_result.status == ToolResultStatus.SUCCESS:
                break

        if last_result is not None:
            last_result.execution_metadata = {
                **(last_result.execution_metadata or {}),
                "accepted": trace.accepted,
                "trace_id": str(trace.id),
                "tool_call_id": str(tool_call.id),
                "total_attempts": trace.total_attempts,
                "total_latency_ms": trace.total_latency_ms,
            }
            return last_result

        return self._rejected_result(tool_call, "fallback_exhausted")

    def _validation_failure_result(self, tool_call: ToolCall, validation: ToolValidationResult) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.FAILED,
            output=None,
            error_message=f"Validation failed: {validation.rejected_reason}",
            execution_time_ms=0.0,
            execution_metadata={
                "accepted": False,
                "validation_issues": [issue.model_dump() for issue in validation.issues],
                "tool_id": tool_call.tool_id,
                "tool_call_id": str(tool_call.id),
            },
        )

    def _rejected_result(self, tool_call: ToolCall, reason: str) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            status=ToolResultStatus.FAILED,
            output=None,
            error_message=reason,
            execution_time_ms=0.0,
            execution_metadata={"accepted": False, "rejected_reason": reason, "tool_id": tool_call.tool_id},
        )
