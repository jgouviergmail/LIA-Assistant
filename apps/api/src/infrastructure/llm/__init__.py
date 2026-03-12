"""
LLM Infrastructure.
Factory and providers for Large Language Models (OpenAI, etc.).

Phase 6 - LLM Observability:
    - get_llm(): Factory with automatic Langfuse callback attachment
    - invoke_helpers: Generic utilities for instrumented LLM calls
    - instrumentation: Config-based Langfuse integration

Note: instrument_node/instrument_tool decorators removed (unused, 2025-11-07)
"""

# Phase 3.1.3 - Evaluation Pipeline
from src.infrastructure.llm.evaluation_pipeline import (
    EvaluationPipeline,
    EvaluationResult,
    evaluation_pipeline,
)
from src.infrastructure.llm.factory import get_llm

# Phase 6 - LLM Observability exports
from src.infrastructure.llm.instrumentation import (
    create_instrumented_config,
    enrich_config_with_callbacks,
    extract_session_user_from_state,
)
from src.infrastructure.llm.invoke_helpers import (
    create_instrumented_config_from_node,
    invoke_sync_with_instrumentation,
    invoke_with_instrumentation,
)
from src.infrastructure.llm.openai_provider import OpenAIProvider

__all__ = [
    # Core factory
    "get_llm",
    "OpenAIProvider",
    # Phase 6 - Instrumentation utilities
    "create_instrumented_config",
    "enrich_config_with_callbacks",
    "extract_session_user_from_state",
    "create_instrumented_config_from_node",
    "invoke_with_instrumentation",
    "invoke_sync_with_instrumentation",
    # Phase 3.1.3 - Evaluation
    "EvaluationPipeline",
    "EvaluationResult",
    "evaluation_pipeline",
]
