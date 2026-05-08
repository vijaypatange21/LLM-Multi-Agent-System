"""
Prompt versioning and configuration schemas.

WHY: Prompts are the "code" of LLM-based systems. Like all code, they:
- Change frequently (tweaking for better outputs)
- Need version control (rollback if a new version regresses)
- Require testing before deployment (prompt A/B testing)
- Benefit from traceability (which prompt version produced this output?)

Prompt versioning enables:
- Reproducibility (rerun with the exact same prompt)
- A/B testing (prompt variant comparison)
- Rollback (revert to previous prompt if new one fails)
- Experimentation (track which tweaks help)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PromptVariableType(str, Enum):
    """Types of variables that can be interpolated in prompts."""
    STRING = "string"
    NUMBER = "number"
    JSON = "json"
    LIST = "list"
    DATETIME = "datetime"


class PromptVariable(BaseModel):
    """
    Placeholder/template variable in a prompt.
    
    WHY: Prompts aren't static; they must adapt to different contexts.
    Variables enable:
    - Reusable prompt templates
    - Context-specific specialization
    - Type checking (is this a number or string?)
    - Documentation (what does this variable do?)
    """
    
    name: str = Field(description="Variable name in template (e.g., 'user_query')")
    variable_type: PromptVariableType = Field(description="Data type of this variable")
    description: str = Field(description="What this variable represents")
    required: bool = Field(default=True, description="Is this variable required?")
    default_value: Optional[Any] = Field(
        default=None,
        description="Default if not provided"
    )


class PromptConfig(BaseModel):
    """
    LLM generation parameters associated with a prompt.
    
    WHY: The same prompt can produce very different outputs depending on
    generation parameters. Storing these with the prompt ensures reproducibility:
    - temperature: Controls randomness
    - max_tokens: Limits output length
    - top_p/top_k: Sampling strategies
    - stop_sequences: When to stop generating
    
    This enables A/B testing and rollback of both prompts AND their configs.
    """
    
    model: str = Field(description="LLM model ID (e.g., 'gpt-4', 'claude-3-opus')")
    model_version: Optional[str] = Field(
        default=None,
        description="Specific model version for reproducibility"
    )
    
    # Generation parameters
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Randomness (0=deterministic, 2=maximum randomness)"
    )
    max_tokens: int = Field(
        default=2048,
        ge=1,
        description="Maximum output length"
    )
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter"
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        description="Top-K sampling"
    )
    frequency_penalty: Optional[float] = Field(
        default=None,
        description="Penalize repetition"
    )
    presence_penalty: Optional[float] = Field(
        default=None,
        description="Encourage new topics"
    )
    
    # Stopping
    stop_sequences: List[str] = Field(
        default_factory=list,
        description="Stop generating when these strings appear"
    )


class PromptVersion(BaseModel):
    """
    Single version of a prompt template.
    
    WHY: Prompts evolve. Each version is immutable, enabling:
    - Reproducibility: Trace an output back to the exact prompt
    - Rollback: Revert to previous prompt if new version fails
    - A/B testing: Compare prompt versions
    - Analysis: Which prompt versions work best?
    
    Design considerations:
    - prompt_id: All versions share the same logical prompt_id. Related
      versions are discoverable.
    - version_number: Semantic versioning (1.0.0) or sequential (1, 2, 3).
      Enables querying "latest version" or "specific version".
    - content: The actual prompt template with variables.
    - variables: Metadata about template variables for validation.
    - config: LLM parameters for reproducible generation.
    - active: Only one version is "active" at a time. Enables gradual rollout.
    - change_description: Why did we change the prompt? (for audit trail).
    """
    
    id: UUID = Field(default_factory=lambda: UUID(int=0), description="Unique version ID")
    prompt_id: str = Field(
        description="Logical prompt identifier (e.g., 'search_query_analyzer')"
    )
    version_number: str = Field(
        description="Version string (e.g., 'v1.0.0') or sequential number"
    )
    
    # Content
    content: str = Field(
        description="Prompt template (may contain {variable} placeholders)"
    )
    
    # Template variables
    variables: List[PromptVariable] = Field(
        default_factory=list,
        description="Template variables that must be interpolated"
    )
    
    # Generation config
    config: PromptConfig = Field(
        description="LLM parameters for this prompt version"
    )
    
    # Metadata
    description: str = Field(description="What does this prompt do?")
    change_description: Optional[str] = Field(
        default=None,
        description="What changed from previous version (for audit trail)"
    )
    
    # Lifecycle
    is_active: bool = Field(
        default=False,
        description="Is this the active version? (used by default)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(description="Who created this version")
    
    # Performance metadata
    usage_count: int = Field(default=0, description="How many times used?")
    average_rating: Optional[float] = Field(
        default=None,
        description="Average user/eval rating (0-100)"
    )
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "prompt_id": "search_analyzer",
                    "version_number": "v1.2.0",
                    "content": "You are an expert search query analyzer. Given a query: {user_query}\n\nAnalyze the intent and return structured results.",
                    "variables": [
                        {
                            "name": "user_query",
                            "variable_type": "string",
                            "description": "The search query to analyze",
                            "required": True,
                            "default_value": None
                        }
                    ],
                    "config": {
                        "model": "gpt-4",
                        "model_version": "gpt-4-0613",
                        "temperature": 0.3,
                        "max_tokens": 1000,
                        "top_p": 0.95,
                        "stop_sequences": ["END"]
                    },
                    "description": "Analyzes search queries to extract intent",
                    "change_description": "Reduced temperature for more consistent results",
                    "is_active": True,
                    "created_at": "2026-05-09T10:00:00Z",
                    "created_by": "prompt_engineer_alice",
                    "usage_count": 1523,
                    "average_rating": 92.5
                }
            ]
        }
