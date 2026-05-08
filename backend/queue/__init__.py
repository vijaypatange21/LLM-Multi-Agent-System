"""
Queue/message broker layer module.

Architecture Overview:
This module manages asynchronous task execution using Redis queues.
Messages flow through Redis to background workers for processing.

Why Redis queues?
- Reliable: persists to disk
- Fast: in-memory
- FIFO: ordered processing
- Pub/Sub: fan-out messaging
- Atomic: transactional operations

Queue Types:

1. Agent Execution Queue
   - Task: process_agent_message
   - Payload: (conversation_id, message, agent_id, trace_id)
   - Workers: 1+ AgentWorker processes
   - Retry: on failure, exponential backoff
   
   WHY: Decouples API from agent processing. Enables:
   - Scalability (more workers = more throughput)
   - Resilience (if worker dies, job is retried)
   - Load smoothing (jobs queued if workers are busy)

2. Tool Execution Queue
   - Task: execute_tool
   - Payload: (tool_id, arguments, execution_trace_id)
   - Workers: 1+ ToolWorker processes
   - Priority: high-priority tools get queue priority
   
   WHY: Some tools are slow. Async execution prevents blocking.

3. Evaluation Queue
   - Task: evaluate_execution
   - Payload: (execution_trace_id, evaluator_id)
   - Workers: 1+ EvalWorker processes
   - Async: non-blocking evaluation (results queued back)
   
   WHY: Evaluations can be expensive. Don't want to block user requests.

4. Streaming Response Queue
   - Task: stream_chunk
   - Payload: (conversation_id, chunk)
   - Subscribers: connected WebSocket clients
   - TTL: chunks expire if not delivered
   
   WHY: Enable Server-Sent Events (SSE) streaming to clients.
   Agents produce output, chunks pushed to clients in real-time.

5. Dead Letter Queue (DLQ)
   - Failed jobs that exhausted retries
   - Manual review/intervention
   - Monitoring alerts
   
   WHY: Some jobs fail permanently. Need human investigation.

Queue configuration:
- Retry policy: 3 retries with exponential backoff
- Job timeout: 5 minutes (configurable per job type)
- Max queue size: prevent memory exhaustion
- Persistence: flush to disk
- Replication: Redis cluster for HA

Job lifecycle:
1. Enqueued: Job added to queue
2. Processing: Worker starts processing
3. Completed: Worker finishes, job removed
4. Failed: Worker error, job re-queued (if retries remain)
5. Abandoned: Exhausted retries, moved to DLQ

Monitoring:
- Queue depth (are jobs piling up?)
- Worker utilization (are workers busy?)
- Job latency (how long do jobs take?)
- Error rates (what % of jobs fail?)
- DLQ size (manual intervention needed?)

Pub/Sub patterns:
- ExecutionTrace updates: agents publish trace updates
- Tool results: tools publish results for orchestrator
- Evaluations: evaluators publish results
- SSE chunks: workers push to client subscribers

Backpressure handling:
- If queue depth exceeds threshold, reject new submissions
- Prioritize user-facing requests over background tasks
- Rate-limit slow consumers (prevent queue buildup)

No implementations yet - only architecture and design.
"""
