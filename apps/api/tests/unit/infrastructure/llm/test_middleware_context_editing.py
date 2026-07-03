"""Guard for ContextEditingMiddleware construction (regression of a dormant bug).

The previous implementation fell back to dict-based edits when the (removed)
``TruncateToolResult`` class was missing — those dicts have no ``.apply()``
method, so EVERY model call of every agent built with the middleware crashed
with ``AttributeError: 'dict' object has no attribute 'apply'`` (masked by
ModelRetryMiddleware into a "Model call failed after 4 attempts" reply).
"""

from __future__ import annotations

from src.infrastructure.llm.middleware_config import _create_context_editing_middleware


def test_context_editing_edits_are_real_context_edit_objects() -> None:
    """Every configured edit must implement the ContextEdit protocol."""
    middleware = _create_context_editing_middleware()

    assert middleware is not None, "ContextEditingMiddleware could not be built"
    edits = list(middleware.edits)
    assert edits, "middleware built without any edit rule"
    for edit in edits:
        assert not isinstance(
            edit, dict
        ), "dict-based edit config crashes every model call (no .apply())"
        assert callable(
            getattr(edit, "apply", None)
        ), f"edit {type(edit).__name__} lacks the ContextEdit .apply() method"


def test_context_editing_uses_settings_driven_thresholds() -> None:
    """Trigger/keep come from settings (no hardcoded thresholds)."""
    from src.core.config import settings

    middleware = _create_context_editing_middleware()
    assert middleware is not None

    edit = list(middleware.edits)[0]
    assert edit.trigger == settings.context_edit_clear_trigger_tokens
    assert edit.keep == settings.context_edit_clear_keep_tool_results
