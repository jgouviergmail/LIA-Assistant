"""Pin the one mechanism that lets tests exercise the typed run context.

``tests/helpers/runtime_context.py`` installs a ``LiaRuntimeContext`` outside a
graph run by writing LangGraph's runtime into the RunnableConfig ContextVar under
a PRIVATE key (``CONF`` / ``CONFIG_KEY_RUNTIME``) — there is no public writer.
That is a deliberate, contained bet: one helper knows it, and this file makes a
LangGraph upgrade that moves the key fail here, by name, instead of surfacing as
dozens of unrelated tests suddenly seeing ``context=None``.

Without these tests the helper could silently stop installing anything and every
test using it would keep passing against a ``None`` context — the exact silent
degradation ADR-231 exists to remove.
"""

import uuid

import pytest

from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    runtime_context_if_running,
)
from tests.helpers.runtime_context import (
    installed_runtime_context,
    make_contextless_tool_runtime,
    make_runtime_context,
    make_tool_runtime,
    no_runtime_context,
)


@pytest.mark.unit
def test_no_context_is_visible_outside_the_block() -> None:
    """The baseline the helper must change — and restore."""
    assert runtime_context_if_running() is None


@pytest.mark.unit
async def test_a_runnable_config_without_a_langgraph_runtime_reads_as_no_run() -> None:
    """The case that broke every tool invoked outside the graph.

    ``get_runtime()`` reads its slot with ``.get()``, so when a RunnableConfig
    exists but LangGraph never filled it — precisely what ``tool.ainvoke()`` does
    outside a run — it returns ``None`` rather than raising. Reading ``.context``
    on that None raised an AttributeError inside every migrated tool; the registry
    smoke test caught it. "No LangGraph runtime" must read as "no run".
    """
    from langchain_core.runnables.config import var_child_runnable_config

    token = var_child_runnable_config.set({"configurable": {"thread_id": "t"}})
    try:
        assert runtime_context_if_running() is None
    finally:
        var_child_runnable_config.reset(token)


@pytest.mark.unit
def test_the_installed_context_is_the_very_object_the_code_reads() -> None:
    """Identity, not equality: a copy would hide a live-dependency bug."""
    with installed_runtime_context(language="de") as installed:
        assert runtime_context_if_running() is installed
        assert runtime_context_if_running().language == "de"


@pytest.mark.unit
def test_the_context_is_removed_on_exit() -> None:
    """A leaked context would make a suite pass only in a given order."""
    with installed_runtime_context():
        assert runtime_context_if_running() is not None

    assert runtime_context_if_running() is None


@pytest.mark.unit
def test_the_context_is_removed_even_when_the_body_raises() -> None:
    """The failure path is the one that leaks, so it is the one to pin."""
    with pytest.raises(ValueError, match="boom"), installed_runtime_context():
        raise ValueError("boom")

    assert runtime_context_if_running() is None


@pytest.mark.unit
def test_nested_installs_restore_the_outer_context() -> None:
    """A sub-agent test installs a derived context inside its parent's."""
    with installed_runtime_context(language="fr") as outer:
        with installed_runtime_context(language="it") as inner:
            assert runtime_context_if_running() is inner
        assert runtime_context_if_running() is outer


@pytest.mark.unit
def test_make_runtime_context_defaults_are_valid_and_reproducible() -> None:
    first, second = make_runtime_context(), make_runtime_context()

    assert isinstance(first, LiaRuntimeContext)
    assert isinstance(first.user_id, uuid.UUID)
    assert first.user_id == second.user_id, "a random identity would make Store keys unstable"


@pytest.mark.unit
def test_make_tool_runtime_carries_a_real_context() -> None:
    """The six hand-rolled runtimes it replaces all passed ``context=None``."""
    runtime = make_tool_runtime(language="es")

    assert isinstance(runtime.context, LiaRuntimeContext)
    assert runtime.context.language == "es"


@pytest.mark.unit
def test_make_tool_runtime_keeps_both_planes_in_agreement() -> None:
    """In production the bag and the context hold the same thread and user."""
    runtime = make_tool_runtime()
    configurable = runtime.config["configurable"]

    assert configurable["thread_id"] == runtime.context.thread_id
    assert configurable["user_id"] == str(runtime.context.user_id)


@pytest.mark.unit
def test_make_tool_runtime_lets_a_test_add_configurable_entries() -> None:
    """Keys that legitimately stay in the bag (LangGraph plumbing) still work."""
    runtime = make_tool_runtime(configurable={"__parent_thread_id": "parent-1"})

    assert runtime.config["configurable"]["__parent_thread_id"] == "parent-1"
    assert runtime.config["configurable"]["thread_id"] == runtime.context.thread_id


@pytest.mark.unit
def test_make_contextless_tool_runtime_is_the_only_way_to_have_no_identity() -> None:
    """ "No acting user" is now expressible only as "no run" (ADR-231).

    If this ever returned a context, every short-circuit test that asserts a tool
    refuses to act without an identity would silently start exercising the
    nominal path instead.
    """
    runtime = make_contextless_tool_runtime()

    assert runtime.context is None
    assert make_tool_runtime().context is not None


@pytest.mark.unit
def test_no_runtime_context_hides_an_installed_one_and_restores_it() -> None:
    """Some suites install a context for every test, then need one without.

    If this leaked, the neighbouring tests would silently run with no context and
    exercise the degraded path while claiming to test the nominal one.
    """
    with installed_runtime_context() as installed:
        with no_runtime_context():
            assert runtime_context_if_running() is None
        assert runtime_context_if_running() is installed
