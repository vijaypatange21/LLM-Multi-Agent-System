"""
Configuration module.

Architecture Overview:
This directory contains configuration files for different environments
(development, testing, production). Configuration is externalized to:
- Keep secrets out of code
- Enable different settings per environment
- Make deployment easier
- Support rapid experimentation

Configuration layers (precedence):

1. Default (in code)
   - Safest defaults
   - Works out-of-box
   - Example: timeout=30s, max_retries=3

2. Environment file (.env)
   - Overrides defaults
   - Not in git (secrets)
   - Per-developer or per-environment

3. Environment variables
   - Highest precedence
   - Used in containers
   - Supports secret injection (K8s, HashiCorp Vault)

4. Runtime arguments
   - CLI flags, API requests
   - Highest priority
   - Short-lived overrides

Configuration categories:

Database:
- DATABASE_URL: PostgreSQL connection string
- DB_POOL_SIZE: connection pool size
- DB_ECHO: log SQL queries (debug)
- DB_TIMEOUT: query timeout

Redis:
- REDIS_URL: connection string
- REDIS_POOL_SIZE: connection pool size
- REDIS_TTL_SECONDS: default key expiry

LLM API:
- OPENAI_API_KEY: OpenAI credentials
- ANTHROPIC_API_KEY: Claude credentials
- MODEL_TIMEOUTS: per-model timeouts
- TEMPERATURE: default LLM temperature

Queue:
- QUEUE_MAX_DEPTH: reject if exceeded
- QUEUE_TIMEOUT: job timeout
- QUEUE_MAX_RETRIES: retry limit
- QUEUE_DEAD_LETTER_QUEUE: DLQ settings

Logging:
- LOG_LEVEL: DEBUG, INFO, WARNING, ERROR
- LOG_FORMAT: json or text
- LOG_AGGREGATION_URL: centralized logging

Streaming:
- SSE_HEARTBEAT_INTERVAL: keep-alive interval
- SSE_CLIENT_TIMEOUT: disconnect inactive clients
- SSE_EVENT_BATCH_SIZE: batch events

Costs/Budgets:
- MAX_TOKENS_PER_CONVERSATION: limit
- MAX_COST_PER_CONVERSATION: limit
- COST_ALERT_THRESHOLD: notify if approaching limit

Timeouts:
- AGENT_PROCESSING_TIMEOUT: max agent time
- TOOL_EXECUTION_TIMEOUT: max tool time
- LLM_CALL_TIMEOUT: max LLM call time

Workers:
- AGENT_WORKER_COUNT: number of workers
- TOOL_WORKER_COUNT: number of workers
- EVAL_WORKER_COUNT: number of workers
- WORKER_CONCURRENCY: jobs per worker

Security:
- SECRET_KEY: for signing
- API_RATE_LIMIT: requests/minute
- ALLOWED_ORIGINS: CORS origins
- AUTH_PROVIDER: auth service endpoint

Features:
- ENABLE_STREAMING: SSE support
- ENABLE_EVALUATIONS: run evals
- ENABLE_PROMPT_VERSIONING: versioning system
- ENABLE_AGENT_DELEGATION: agent-to-agent calls

Evaluation:
- EVALUATOR_TYPE: which evaluator to use
- EVAL_METRICS: which metrics to compute
- EVAL_BUDGET: token budget for evals
- EVAL_BATCH_SIZE: batch multiple evals

Environment-specific configs:

Development (.env.dev):
- LOG_LEVEL: DEBUG
- DB_ECHO: true (log SQL)
- ENABLE_ALL_FEATURES: true
- DEBUG_MODE: true

Testing (.env.test):
- Use test database
- Disable external APIs (mocks)
- Fast timeouts
- Verbose logging

Production (.env.prod):
- LOG_LEVEL: WARNING
- DB_ECHO: false
- ENABLE_ONLY_STABLE: true
- MINIMUM_EVAL_THRESHOLD: 90.0
- HIGH_PERFORMANCE_MODE: true

Configuration loading:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()
```

Secret management:
- Don't store secrets in .env files
- Use environment variables (injected by container orchestrator)
- Use HashiCorp Vault or similar for production
- Rotate keys regularly
- Audit access

Configuration validation:
- Use Pydantic for type checking
- Validate URL formats, numeric ranges
- Fail fast on invalid config
- Provide helpful error messages

Example configurations to create:
- .env.example: template with all keys
- config/development.yaml: dev-specific
- config/production.yaml: prod-specific
- config/features.yaml: feature flags

No implementations yet - only structure and guidelines.
"""
