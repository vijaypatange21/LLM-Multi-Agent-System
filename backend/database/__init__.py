"""
Database layer module.

Architecture Overview:
This module defines ORM models and database access patterns for storing
persistent data. We use SQLAlchemy ORM + PostgreSQL.

Data Entities:

1. Conversation
   - conversation_id: UUID (primary key)
   - user_id: references User
   - created_at: timestamp
   - updated_at: timestamp
   - metadata: JSON (extensible)
   - Status: active, completed, failed, archived
   
   WHY: Conversations are sessions. We need to track them for:
   - User history (what conversations has user had?)
   - Billing (how many conversations per user?)
   - Analytics (which types of conversations succeed most?)

2. ExecutionTrace
   - id: UUID (primary key)
   - conversation_id: UUID (foreign key)
   - agent_id: string
   - status: enum (completed, failed, in_progress)
   - started_at, completed_at: timestamps
   - total_duration_ms: float
   - total_cost: float
   - tokens_used: JSON
   - steps: JSON (serialized list of ExecutionSteps)
   
   WHY: Traces are the audit log. We store them for:
   - Debugging (what did the agent do?)
   - Cost tracking (how much did this execution cost?)
   - Analytics (latency trends, success rates)
   - Compliance (audit trail)

3. SharedContext
   - conversation_id: UUID (primary key)
   - version: int
   - facts: JSON
   - constraints: JSON
   - resources: JSON
   - metadata: JSON
   - created_at, updated_at: timestamps
   
   WHY: We need durable storage of context for:
   - Persistence across worker restarts
   - Multi-agent consistency
   - Historical context tracking

4. PromptVersion
   - id: UUID (primary key)
   - prompt_id: string
   - version_number: string
   - content: text
   - config: JSON
   - is_active: boolean
   - created_at: timestamp
   - created_by: string
   - usage_count: int
   - average_rating: float
   
   WHY: Prompts are versioned for:
   - Reproducibility (exactly which prompt was used?)
   - A/B testing (compare prompt versions)
   - Rollback (revert to previous prompt)
   - Analytics (which prompt versions work best?)

5. EvalResult
   - id: UUID (primary key)
   - execution_trace_id: UUID (foreign key)
   - evaluator_id: string
   - metrics: JSON
   - overall_pass: boolean
   - overall_score: float
   - evaluated_at: timestamp
   
   WHY: Evaluations enable:
   - Quality gates (only deploy passing agents)
   - Performance tracking (are agents improving?)
   - A/B testing (which variant is better?)
   - Monitoring (alert on quality drops)

6. ToolDefinition (cache)
   - id: string (primary key)
   - version: string
   - content: JSON
   - created_at: timestamp
   
   WHY: Cache tool definitions for:
   - Fast lookup (avoid refetching)
   - History (what tools were available at time T?)
   - Audit (which tools changed when?)

Indexing strategy:
- conversation_id is heavily queried (history retrieval)
- created_at for time-range queries (analytics)
- agent_id for agent-specific analytics
- status for filtering (show only failed traces)
- is_active for prompt discovery

Connection pooling:
- Use SQLAlchemy connection pool
- Handle connection timeouts
- Automatic reconnection on database restart

Transaction handling:
- Use transactions for multi-step operations
- Ensure atomicity (all or nothing)
- Retry on serialization conflicts

No ORM implementations yet - only architectural documentation.
"""
