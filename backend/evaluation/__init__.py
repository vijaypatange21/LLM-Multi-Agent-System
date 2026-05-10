"""
Evaluation framework module.

Architecture Overview:
This module provides evaluation/grading infrastructure. Production systems
must measure quality. Evaluators are pluggable implementations that assess
agent outputs.

Why evaluation?
- Quality gates: don't deploy bad agents
- Performance tracking: are agents improving?
- Comparison: which agent variant is better?
- Monitoring: alert on quality regression
- Learning: use evals to train/improve agents

Evaluator Types:

1. Automated Evaluators
   - Judge LLM: uses another LLM to grade outputs
   - Pattern matcher: checks for specific patterns
   - Schema validator: validates output structure
   - Semantic similarity: compares output to reference
   
   Pros: fast, scalable, reproducible
   Cons: may not capture nuance, hallucination-prone

2. Human Evaluators
   - Expert review: skilled human judges
   - Crowdsourced: multiple annotators
   - User feedback: implicit (clicks, time spent)
   
   Pros: captures nuance, aligns with user needs
   Cons: slow, expensive, subjective

3. Hybrid Evaluators
   - Judge LLM as first-pass (quick)
   - Escalate disagreements to human
   - Use human feedback to improve judge

Metrics to evaluate:

Correctness:
- Does the output answer the question?
- Is the answer factually accurate?
- Are there hallucinations?

Completeness:
- Are all requirements addressed?
- Did agent follow all constraints?
- Are edge cases handled?

Clarity:
- Is the output understandable?
- Is reasoning transparent?
- Are steps explained?

Relevance:
- Is output relevant to the query?
- No off-topic content?
- No unnecessary information?

Safety:
- No constraint violations?
- No dangerous suggestions?
- Appropriate tone/content?

Efficiency:
- Did it meet latency targets?
- Did it stay within budget?
- Minimal token usage?

Evaluation workflow:

1. Execution completes
   - Agent produces ExecutionTrace
   - Trace is stored in database

2. Evaluation triggered
   - Queued to evaluation workers
   - Evaluator fetches ExecutionTrace
   - Evaluator loads evaluation prompts/models

3. Evaluation runs
   - Evaluator analyzes execution
   - Computes metrics
   - Produces EvalResult

4. Results stored
   - EvalResult saved to database
   - Indexed by execution_trace_id
   - Searchable for analytics

5. Results published
   - Published to streaming channel (optional)
   - Metrics aggregated
   - Alerts triggered if quality drops

Evaluation configuration:

Per-conversation:
- Which evaluator to use?
- Which metrics to measure?
- Pass/fail thresholds?
- Budget for evaluation?

Per-agent:
- Required evaluators
- Required minimum score
- Auto-deploy if threshold met?

Per-metric:
- Weight (importance)
- Threshold (minimum acceptable)
- Target (ideal score)

Evaluation storage:
- EvalResult in PostgreSQL
- Raw evaluation data (JSON) for debugging
- Evaluation artifacts (test cases, references)
- Historical data for trending

Comparison/baseline:
- Compare current to previous version
- Compare to other agent variants
- Compare to human performance
- Identify regressions

Integration points:
- CI/CD: block deployment if evals fail
- Monitoring: track eval metrics over time
- Analytics: answer "which agents work best?"
- Learning: use eval data to improve prompts/agents
"""

# Evaluation harness
from .harness import (
    CaseCategory,
    DimensionScorer,
    DimensionScore,
    EvaluationCase,
    EvaluationHarness,
    EvaluationResult,
    ScoringDimension,
)

# Test cases
from .test_cases import (
    create_baseline_cases,
    create_ambiguous_cases,
    create_adversarial_cases,
)

# Prompt optimization
from .prompt_optimization import (
    ApprovalStatus,
    PromptRole,
    PromptVersion,
    PromptDiff,
    PromptDiffGenerator,
    PromptAnalyzer,
    MetaAgent,
    PromptOptimizationOrchestrator,
)

__all__ = [
    # Harness
    "CaseCategory",
    "ScoringDimension",
    "DimensionScore",
    "EvaluationCase",
    "EvaluationResult",
    "DimensionScorer",
    "EvaluationHarness",
    # Test cases
    "create_baseline_cases",
    "create_ambiguous_cases",
    "create_adversarial_cases",
    # Prompt optimization
    "ApprovalStatus",
    "PromptRole",
    "PromptVersion",
    "PromptDiff",
    "PromptDiffGenerator",
    "PromptAnalyzer",
    "MetaAgent",
    "PromptOptimizationOrchestrator",
]
