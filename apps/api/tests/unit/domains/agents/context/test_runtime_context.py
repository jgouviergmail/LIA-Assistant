"""Contract tests for the typed runtime context (ADR-231).

The context replaces an untyped 17-key ``config["configurable"]`` bag whose
``user_id`` arrived as a ``uuid.UUID`` from the chokepoint and a ``str`` from the
parallel executor — the ambiguity ``parse_user_id(str | UUID)`` exists only to
absorb. Freezing the identity type is the point of the migration, so it is tested
first.

Two measured properties shape the design and are pinned here:

- LangGraph never copies the context (object identity is preserved through node,
  subgraph and tool), so live run dependencies such as an ``asyncio.Queue`` are
  safe as fields.
- The context is never checkpointed, so nothing that must survive an interrupt
  resume may live here — that belongs in ``MessagesState``.
"""

import asyncio
import dataclasses
import uuid

import pytest

from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    assert_runtime_context,
)


def _ctx(**overrides) -> LiaRuntimeContext:
    """A minimal valid context; overrides let each test say what it is about."""
    base = {
        "user_id": uuid.uuid4(),
        "thread_id": "thread-1",
        "conversation_id": "conv-1",
    }
    return LiaRuntimeContext(**{**base, **overrides})


@pytest.mark.unit
def test_context_is_frozen() -> None:
    """Run-scoped context is read-only: a node must never rebind a field."""
    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_id = uuid.uuid4()  # type: ignore[misc]


@pytest.mark.unit
def test_user_id_is_a_uuid_not_a_string() -> None:
    """One identity, one type — the whole point of the migration."""
    uid = uuid.uuid4()
    ctx = _ctx(user_id=uid)

    assert ctx.user_id == uid
    assert isinstance(ctx.user_id, uuid.UUID)


@pytest.mark.unit
def test_required_fields_have_no_default() -> None:
    """A context missing an identity must fail at construction, loudly."""
    with pytest.raises(TypeError):
        LiaRuntimeContext()  # type: ignore[call-arg]


@pytest.mark.unit
def test_there_is_no_langgraph_user_id_duplicate() -> None:
    """``langgraph_user_id`` duplicated ``user_id`` as a str across 25 read sites,
    justified by a LangMem integration that is not installed."""
    names = {f.name for f in dataclasses.fields(LiaRuntimeContext)}

    assert "langgraph_user_id" not in names
    assert "user_id" in names


@pytest.mark.unit
def test_every_private_configurable_key_became_a_named_field() -> None:
    """The four ``__``-prefixed keys were an enforced but unpublished contract."""
    names = {f.name for f in dataclasses.fields(LiaRuntimeContext)}

    for field_name in ("deps", "browser_context", "user_message", "side_channel_queue"):
        assert field_name in names, f"missing named field for the former __{field_name}"

    assert not any(
        n.startswith("_") for n in names
    ), "no field may keep a private-key shape — the contract is published now"


@pytest.mark.unit
def test_assert_runtime_context_rejects_none() -> None:
    """Measured: an absent context yields None silently. This is the net."""
    with pytest.raises(RuntimeError, match="runtime context"):
        assert_runtime_context(None)


@pytest.mark.unit
def test_assert_runtime_context_rejects_a_raw_dict() -> None:
    """The pre-migration shape was an untyped dict; it must not pass silently."""
    with pytest.raises(RuntimeError, match="runtime context"):
        assert_runtime_context({"user_id": "u"})


@pytest.mark.unit
def test_assert_runtime_context_returns_a_valid_context_unchanged() -> None:
    ctx = _ctx()
    assert assert_runtime_context(ctx) is ctx


@pytest.mark.unit
def test_live_dependencies_keep_their_identity() -> None:
    """LangGraph does not copy the context, so live objects are safe as fields."""
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()
    ctx = _ctx(side_channel_queue=queue, deps=sentinel)

    assert ctx.side_channel_queue is queue
    assert ctx.deps is sentinel


@pytest.mark.unit
def test_defaults_come_from_settings_not_from_literals() -> None:
    """CLAUDE.md forbids an inline language or timezone default anywhere."""
    from src.core.config import settings
    from src.core.constants import DEFAULT_TIMEZONE

    ctx = _ctx()

    assert ctx.language == settings.default_language
    assert ctx.timezone == DEFAULT_TIMEZONE


@pytest.mark.unit
def test_no_hardcoded_language_or_timezone_literal_in_the_module() -> None:
    """Guard the module itself, not only the value it happens to produce."""
    import ast
    from pathlib import Path

    source = Path("src/domains/agents/context/runtime_context.py").read_text(encoding="utf-8")
    forbidden = {"fr", "en", "de", "es", "it", "zh", "zh-CN", "UTC", "Europe/Paris"}
    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in forbidden
    ]

    assert not offenders, f"hardcoded language/timezone literal(s): {offenders}"


@pytest.mark.unit
def test_for_conversation_makes_the_thread_mirror_the_conversation() -> None:
    """LangGraph's thread_id IS the conversation id for a normal run."""
    cid = uuid.uuid4()
    ctx = LiaRuntimeContext.for_conversation(user_id=uuid.uuid4(), conversation_id=cid)

    assert ctx.thread_id == str(cid)
    assert ctx.conversation_id == str(cid)


@pytest.mark.unit
def test_for_conversation_forwards_overrides_and_live_objects() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    ctx = LiaRuntimeContext.for_conversation(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="de",
        timezone="Europe/Berlin",
        side_channel_queue=queue,
        deps=sentinel,
    )

    assert ctx.language == "de"
    assert ctx.timezone == "Europe/Berlin"
    assert ctx.side_channel_queue is queue
    assert ctx.deps is sentinel


@pytest.mark.unit
def test_deriving_a_sub_thread_keeps_the_conversation() -> None:
    """Why conversation_id is a field of its own, not a synonym of thread_id.

    A sub-agent derives a synthetic thread; without a separate conversation_id a
    side effect fired from that sub-run could no longer attribute itself to the
    real conversation.
    """
    cid = uuid.uuid4()
    parent = LiaRuntimeContext.for_conversation(user_id=uuid.uuid4(), conversation_id=cid)

    child = dataclasses.replace(parent, thread_id="react_sub_1")

    assert child.thread_id == "react_sub_1"
    assert child.conversation_id == str(cid)


@pytest.mark.unit
def test_the_context_carries_every_value_the_chokepoint_builds() -> None:
    """Completeness against the 17 keys of the configurable bag it replaces.

    Doctrine ADR-085: a mapping that can silently lose an entry gets an assert. If
    a key is added to the chokepoint without a field here, the migration would
    drop it — exactly the class of defect this work removes.
    """
    names = {f.name for f in dataclasses.fields(LiaRuntimeContext)}
    expected = {
        "thread_id",
        "user_id",
        "conversation_id",
        "store",
        "memory_enabled",
        "journals_enabled",
        "psyche_enabled",
        "display_mode",
        "execution_mode",
        "is_automated_source",
        "deps",
        "browser_context",
        "user_message",
        "side_channel_queue",
        "timezone",
        "language",
        "display_name",
    }

    assert names == expected, (
        "the context drifted from the chokepoint it replaces.\n"
        f"missing: {sorted(expected - names)}\nunexpected: {sorted(names - expected)}"
    )
