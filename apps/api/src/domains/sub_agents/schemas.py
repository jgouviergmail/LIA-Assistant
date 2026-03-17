"""
Sub-Agents Pydantic schemas.

Request/response validation for the sub-agents REST API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Request schemas
# ============================================================================


class SubAgentCreate(BaseModel):
    """Schema for creating a new sub-agent."""

    name: str = Field(..., min_length=1, max_length=100, description="Unique name per user")
    description: str = Field(..., min_length=1, max_length=500)
    system_prompt: str = Field(..., min_length=1, max_length=10000)
    personality_instruction: str | None = Field(default=None, max_length=5000)
    icon: str | None = Field(default=None, max_length=10)
    llm_provider: str | None = Field(default=None, max_length=50)
    llm_model: str | None = Field(default=None, max_length=100)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_iterations: int = Field(default=5, ge=1, le=15)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    skill_ids: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    context_instructions: str | None = Field(default=None, max_length=5000)


class SubAgentCreateFromTemplate(BaseModel):
    """Schema for creating a sub-agent from a pre-defined template."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Override template name (null = use template default)",
    )
    description: str | None = Field(default=None, max_length=500)
    system_prompt: str | None = Field(default=None, max_length=10000)
    icon: str | None = Field(default=None, max_length=10)
    llm_provider: str | None = Field(default=None, max_length=50)
    llm_model: str | None = Field(default=None, max_length=100)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    context_instructions: str | None = Field(default=None, max_length=5000)


class SubAgentUpdate(BaseModel):
    """Schema for partially updating a sub-agent. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=10000)
    personality_instruction: str | None = Field(default=None, max_length=5000)
    icon: str | None = Field(default=None, max_length=10)
    llm_provider: str | None = Field(default=None, max_length=50)
    llm_model: str | None = Field(default=None, max_length=100)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_iterations: int | None = Field(default=None, ge=1, le=15)
    timeout_seconds: int | None = Field(default=None, ge=10, le=600)
    skill_ids: list[str] | None = None
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    context_instructions: str | None = Field(default=None, max_length=5000)


class SubAgentExecutionRequest(BaseModel):
    """Schema for executing a sub-agent."""

    instruction: str = Field(..., min_length=1, max_length=10000)
    context: dict | None = Field(default=None, description="Additional context for the sub-agent")
    run_in_background: bool = Field(default=False)


# ============================================================================
# Response schemas
# ============================================================================


class SubAgentResponse(BaseModel):
    """Full sub-agent response with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str
    icon: str | None
    system_prompt: str
    personality_instruction: str | None
    context_instructions: str | None
    llm_provider: str | None
    llm_model: str | None
    llm_temperature: float | None
    max_iterations: int
    timeout_seconds: int
    skill_ids: list[str]
    allowed_tools: list[str]
    blocked_tools: list[str]
    is_enabled: bool
    status: str
    created_by: str
    template_id: str | None
    execution_count: int
    last_executed_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    last_execution_summary: str | None
    created_at: datetime
    updated_at: datetime


class SubAgentListResponse(BaseModel):
    """Paginated list of sub-agents."""

    items: list[SubAgentResponse]
    total: int


class SubAgentExecutionResponse(BaseModel):
    """Response from sub-agent execution."""

    success: bool
    result: str | None = None
    tokens_used: int = 0
    duration_seconds: float = 0.0
    task_id: str | None = Field(
        default=None,
        description="Background task ID (only for run_in_background=True)",
    )


class SubAgentTemplateResponse(BaseModel):
    """Pre-defined template for sub-agent creation."""

    id: str
    name: str
    description: str
    icon: str | None
    suggested_skill_ids: list[str]
    suggested_tools: list[str]
    default_blocked_tools: list[str]


class SubAgentTemplateListResponse(BaseModel):
    """List of available templates."""

    items: list[SubAgentTemplateResponse]
