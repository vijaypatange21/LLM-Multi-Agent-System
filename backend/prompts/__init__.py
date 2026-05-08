"""
Prompt versioning and management module.

Architecture Overview:
This module manages prompt versions and configurations. Prompts are the
"code" of LLM-based systems. Like all code, they evolve and need versioning.

Why prompt versioning?
- Reproducibility: exactly which prompt was used?
- A/B testing: compare prompt variants
- Rollback: revert to previous if regression
- Analytics: which prompts work best?
- Traceability: audit trail of changes

Prompt structure:

1. Prompt Template
   - Static structure (instructions, context setup)
   - Variable placeholders ({user_query}, {context}, etc.)
   - Examples (few-shot demonstrations)
   - Output format specification

2. Configuration
   - Model: which LLM? (GPT-4, Claude, etc.)
   - Temperature: creativity/randomness
   - Max tokens: output length limit
   - Sampling: top-p, top-k
   - Stop sequences: when to stop generating

3. Metadata
   - Version number
   - Change log (what changed from previous?)
   - Created by/when
   - Usage metrics
   - Performance metrics

Prompt lifecycle:

1. Authoring
   - Prompt engineer writes template
   - Defines variables and format
   - Tests locally

2. Registration
   - Save to database
   - Assign version number (v1.0.0)
   - Mark as inactive

3. Testing
   - Run against test set
   - Evaluate outputs
   - Compare to baseline
   - Iterate if needed

4. Activation
   - Promote to production
   - Mark is_active=true
   - Only one version active at a time
   - Previous version becomes fallback

5. Monitoring
   - Track usage (how many times used?)
   - Track ratings (user feedback)
   - Alert on regression (score drops)

6. Archival
   - Old versions kept for reference
   - Can be reactivated if needed
   - Available for rollback

Example prompt template:

```
You are an expert customer service agent. Your task is to help the user
with their question about {product_name}.

User's question:
{user_question}

Context about {product_name}:
{product_context}

You should:
1. Understand the user's intent
2. Provide accurate information
3. Be polite and helpful
4. Offer to escalate if needed

Respond in JSON format:
{
  "intent": "...",
  "answer": "...",
  "confidence": 0.0-1.0,
  "needs_escalation": true/false
}
```

Prompt versioning strategies:

1. Semantic Versioning
   - Major.Minor.Patch
   - v1.0.0 -> v1.1.0 (minor fix)
   - v1.0.0 -> v2.0.0 (major change)
   - Enables version constraints (>=1.0.0, <2.0.0)

2. Sequential
   - Simple integers: 1, 2, 3, ...
   - Easy to understand
   - No semantic meaning

3. Timestamp
   - 2026-05-09_v1
   - Unique, sorted by date
   - Less human-readable

Integration points:

Agent selection:
- Agent loads active prompt version at startup
- Or loads dynamically per request
- Or loads version specified in context

Evaluation:
- Store which prompt version was used
- Correlate eval results with prompt versions
- Answer: "which prompt versions work best?"

A/B testing:
- Run agents with different prompt versions
- Collect metrics
- Statistical comparison
- Promote winner

Rollback:
- If new prompt performs worse
- Mark as inactive
- Revert to previous version
- Minimal downtime

Cost optimization:
- Shorter prompts = fewer input tokens = cheaper
- Track token usage per prompt version
- Optimize for cost without sacrificing quality

No implementations yet - only architectural framework.
"""
