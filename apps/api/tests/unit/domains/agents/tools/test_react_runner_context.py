"""The ReAct sub-runner must not invent a language or a timezone.

CLAUDE.md forbids inline language literals anywhere in Python — fallbacks and
parameter defaults included — and requires defaults to come from settings or from
``core.constants``. The canonical chokepoint
(``services/orchestration/service.py``) already reads ``settings.default_language``
and ``DEFAULT_TIMEZONE``; this runner deviated with ``"fr"`` and ``"UTC"``
literals, so a sub-agent answered in French to a German user whenever the parent
configurable happened to lack the key.

The scan is exact-equality on string constants, deliberately: a docstring
mentioning ``e.g. "Europe/Paris"`` is legitimate documentation, a bare literal
used as a value is not. It mirrors the doctrine of
``test_no_hardcoded_timezone_guard.py``, scoped to the file that violated it.
"""

import ast
from pathlib import Path

import pytest

RUNNER = Path("src/domains/agents/tools/react_runner.py")

# Backend-canonical language codes plus the timezone literals a fallback might
# reach for. ``zh`` is included even though the backend canonical form is
# ``zh-CN``: both are wrong as an inline default.
FORBIDDEN_LITERALS: frozenset[str] = frozenset(
    {"fr", "en", "de", "es", "it", "zh", "zh-CN", "UTC", "Europe/Paris"}
)


@pytest.mark.unit
def test_no_hardcoded_language_or_timezone_literal_in_the_sub_runner() -> None:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in FORBIDDEN_LITERALS
    ]

    assert not offenders, (
        "Hardcoded language/timezone literal(s) in the ReAct sub-runner: "
        f"{offenders}. Read `settings.default_language` and `DEFAULT_TIMEZONE` "
        "instead — the canonical chokepoint already does."
    )


@pytest.mark.unit
def test_sub_agent_context_inherits_every_parent_field() -> None:
    """Deriving beats re-projecting: a new field must not need a code change here.

    The hand-written projection kept 6 of the parent's 17 keys and dropped 11
    (``browser_context``, ``user_message``, ``display_name``,
    ``is_automated_source``…). Latent today because the default sub-agent
    whitelist is ``perplexity_search_tool,brave_search_tool,fetch_web_page_tool``
    and none of them reads the dropped values — but the whitelist is
    ``.env``-configurable, so adding a location-aware tool would silently degrade
    geolocation. Deriving removes the bug class instead of adding eleven keys.
    """
    import dataclasses
    import uuid

    from src.domains.agents.context.runtime_context import (
        LiaRuntimeContext,
        derive_sub_agent_context,
    )

    parent = LiaRuntimeContext(
        user_id=uuid.uuid4(),
        thread_id="parent-thread",
        conversation_id="conv-1",
        language="de",
        timezone="Europe/Berlin",
        browser_context={"lat": 1.0, "lon": 2.0},
        user_message="original wording",
        display_name="Alice",
        is_automated_source=True,
    )

    child = derive_sub_agent_context(parent, thread_id="react_sub_1")

    assert child.thread_id == "react_sub_1"
    for field in dataclasses.fields(LiaRuntimeContext):
        if field.name == "thread_id":
            continue
        assert getattr(child, field.name) == getattr(
            parent, field.name
        ), f"field {field.name!r} was lost when deriving the sub-agent context"


@pytest.mark.unit
def test_sub_agent_context_keeps_live_object_identity() -> None:
    """The side channel and the dependency container must be the SAME objects."""
    import asyncio
    import uuid

    from src.domains.agents.context.runtime_context import (
        LiaRuntimeContext,
        derive_sub_agent_context,
    )

    queue: asyncio.Queue = asyncio.Queue()
    deps = object()
    parent = LiaRuntimeContext(
        user_id=uuid.uuid4(),
        thread_id="t",
        conversation_id="c",
        side_channel_queue=queue,
        deps=deps,
    )

    child = derive_sub_agent_context(parent, thread_id="sub")

    assert child.side_channel_queue is queue
    assert child.deps is deps


@pytest.mark.unit
def test_the_runner_no_longer_reprojects_the_context_by_hand() -> None:
    """Pin the removal: a hand-written key list is what lost fields silently."""
    source = RUNNER.read_text(encoding="utf-8")

    assert (
        "derive_sub_agent_context" in source
    ), "the sub-runner must derive its context from the parent"

    # The derived context is worthless unless it actually reaches the sub-run,
    # and unless the sub-agent declares the schema that types it.
    assert "context=nested_context" in source, (
        "the derived context must be passed to the sub-agent's ainvoke — deriving "
        "it and dropping it on the floor would be worse than not deriving at all"
    )
    assert "context_schema=LiaRuntimeContext" in source, (
        "the sub-agent must declare the context schema, or its nodes and tools "
        "read an untyped value"
    )


@pytest.mark.unit
def test_the_canonical_sources_are_actually_imported() -> None:
    """A guard on absence is weak; pin the presence of the replacement too."""
    source = RUNNER.read_text(encoding="utf-8")

    assert (
        "settings.default_language" in source
    ), "the sub-runner must read the default language from settings"
    assert (
        "DEFAULT_TIMEZONE" in source
    ), "the sub-runner must read the default timezone from core.constants"
