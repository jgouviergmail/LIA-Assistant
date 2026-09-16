"""Re-export of :mod:`src.core.reasoning_profiles` (the rules moved to ``core``).

The profile rules were read by ``core.llm_config_helper`` from here, an
inversion of the layer direction that closed an import cycle. The rules now
live in ``core``; this module keeps the path every reader knows.
"""

from src.core.reasoning_profiles import (
    DEEPSEEK_THINKING_PREFIXES,
    FAMILIES,
    ReasoningProfile,
    is_deepseek_thinking_model,
    ollama_declared_ladder,
    resolve_reasoning_profile,
)

__all__ = [
    "DEEPSEEK_THINKING_PREFIXES",
    "FAMILIES",
    "ReasoningProfile",
    "is_deepseek_thinking_model",
    "ollama_declared_ladder",
    "resolve_reasoning_profile",
]
