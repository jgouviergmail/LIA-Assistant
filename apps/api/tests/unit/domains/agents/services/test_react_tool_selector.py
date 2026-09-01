"""Tests for ReactToolSelector — user MCP tool inclusion and HITL parity.

Regression guard for the ReAct/pipeline asymmetry: user MCP tools live only in
``user_mcp_tools_ctx`` (not the global registry), so the selector must resolve
them via the shared resolver and must read their HITL flag from the in-hand
manifest (the agent_registry does not know user MCP tools).
"""

from types import SimpleNamespace
from uuid import UUID

from src.core.config import settings
from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX, MCP_USER_TOOL_NAME_PREFIX
from src.core.context import (
    UserMCPToolsContext,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

_SERVER_ID = UUID("770baa3e-1111-2222-3333-444455556666")
_SERVER_PREFIX = str(_SERVER_ID)[:8]
_TASK_TOOL_NAME = f"{MCP_USER_TOOL_NAME_PREFIX}_{_SERVER_PREFIX}{MCP_ITERATIVE_TASK_SUFFIX}"


def _make_user_adapter(
    tool_name: str, *, app_resource_uri: str | None = None
) -> UserMCPToolAdapter:
    return UserMCPToolAdapter.from_discovered_tool(
        server_id=_SERVER_ID,
        user_id=UUID(int=1),
        server_name="atars",
        tool_name=tool_name,
        description=f"User MCP tool {tool_name}",
        input_schema={"type": "object", "properties": {}},
        app_resource_uri=app_resource_uri,
    )


def _manifest(name: str, *, hitl: bool) -> SimpleNamespace:
    return SimpleNamespace(name=name, permissions=SimpleNamespace(hitl_required=hitl))


class TestReactToolSelectorUserMCP:
    """User MCP tools must be selectable in ReAct mode (pipeline parity)."""

    def test_user_mcp_tool_is_selected_not_skipped(self) -> None:
        """A user MCP tool present only in the ContextVar must be wrapped, not dropped."""
        adapter = _make_user_adapter("get_indicator")
        manifest = _manifest(adapter.name, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [manifest]

        man_token = request_tool_manifests_ctx.set([manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert adapter.name in {t.name for t in wrapped}
        assert adapter.name in hitl_map

    def test_user_mcp_hitl_read_from_manifest(self) -> None:
        """HITL flag must come from the manifest (agent_registry has no user MCP)."""
        adapter = _make_user_adapter("delete_data")
        manifest = _manifest(adapter.name, hitl=True)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [manifest]

        man_token = request_tool_manifests_ctx.set([manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert hitl_map.get(adapter.name) is True
        wrapper = next(t for t in wrapped if t.name == adapter.name)
        assert wrapper.hitl_required is True


class TestReactIterativeExpansion:
    """In ReAct, iterative user MCP servers expose individual tools (option B).

    Exception: MCP App servers (tools with app_resource_uri) keep the opaque
    task tool, because they need the dedicated MCP-app prompt + model.
    """

    def test_iterative_data_server_expanded_to_individual_tools(self) -> None:
        """A non-App iterative server: task tool is replaced by its individual tools."""
        ind1 = _make_user_adapter("get_indicator")
        ind2 = _make_user_adapter("get_signal_summary")
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = SimpleNamespace(name=_TASK_TOOL_NAME)
        ctx.tool_instances[ind1.name] = ind1
        ctx.tool_instances[ind2.name] = ind2
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert ind1.name in names
        assert ind2.name in names
        assert _TASK_TOOL_NAME not in names  # opaque task tool replaced

    def test_iterative_app_server_keeps_task_tool(self) -> None:
        """An MCP App iterative server keeps the task tool, individual tools hidden."""
        from src.domains.agents.tools.mcp_react_tools import mcp_user_server_task_tool

        app_tool = _make_user_adapter("create_view", app_resource_uri="ui://widget")
        task_instance = mcp_user_server_task_tool.model_copy(update={"name": _TASK_TOOL_NAME})
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = task_instance
        ctx.tool_instances[app_tool.name] = app_tool
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert _TASK_TOOL_NAME in names  # app server keeps the task tool
        assert app_tool.name not in names  # individual app tools stay hidden

    def test_expansion_disabled_keeps_task_tool(self, monkeypatch) -> None:
        """With the feature flag off, the iterative task tool is kept (no expansion)."""
        from src.domains.agents.tools.mcp_react_tools import mcp_user_server_task_tool

        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", False)

        ind1 = _make_user_adapter("get_indicator")
        task_instance = mcp_user_server_task_tool.model_copy(update={"name": _TASK_TOOL_NAME})
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=False)

        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = task_instance
        ctx.tool_instances[ind1.name] = ind1
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, _hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = {t.name for t in wrapped}
        assert _TASK_TOOL_NAME in names  # flag off → task tool kept
        assert ind1.name not in names  # individual tools NOT exposed


class TestReactToolSelectorCapPriority:
    """The max_tools cap must sacrifice generic tools, never the detected domains' tools.

    Regression guard for the blind positional truncation that silently dropped
    e.g. calendar tools on a calendar query when user-MCP expansion pushed the
    resolved count over ``react_agent_max_tools`` (observed 2026-07-08: 102
    resolved → 100 kept, dropped names unlogged, model hallucinated events).
    """

    @staticmethod
    def _setup_three_tools() -> tuple[list[SimpleNamespace], UserMCPToolsContext]:
        """Three resolvable tools; the DOMAIN tool (event_agent) is LAST."""
        generic_1 = _make_user_adapter("generic_alpha")
        generic_2 = _make_user_adapter("generic_beta")
        event_tool = _make_user_adapter("calendar_get_events")

        manifests = [
            SimpleNamespace(
                name=generic_1.name,
                agent="web_search_agent",
                permissions=SimpleNamespace(hitl_required=False),
            ),
            SimpleNamespace(
                name=generic_2.name,
                agent="wikipedia_agent",
                permissions=SimpleNamespace(hitl_required=True),
            ),
            SimpleNamespace(
                name=event_tool.name,
                agent="event_agent",
                permissions=SimpleNamespace(hitl_required=False),
            ),
        ]
        ctx = UserMCPToolsContext()
        for adapter in (generic_1, generic_2, event_tool):
            ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = manifests
        return manifests, ctx

    def test_cap_preserves_detected_domain_tools(self, monkeypatch) -> None:
        """Over the cap, the detected domain's tool survives even when listed last."""
        monkeypatch.setattr(settings, "react_agent_max_tools", 2)
        manifests, ctx = self._setup_three_tools()
        intelligence = SimpleNamespace(domains=["event"])

        man_token = request_tool_manifests_ctx.set(manifests)
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, hitl_map = ReactToolSelector().select(intelligence=intelligence)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        names = [t.name for t in wrapped]
        assert len(names) == 2
        assert manifests[2].name in names  # event_agent tool survived the cap
        assert manifests[1].name not in names  # last generic tool sacrificed
        assert set(hitl_map) == set(names)  # hitl_map stays consistent post-cap

    def test_under_cap_keeps_all_tools_in_original_order(self, monkeypatch) -> None:
        """Under the cap, nothing is dropped and the original order is untouched."""
        monkeypatch.setattr(settings, "react_agent_max_tools", 10)
        manifests, ctx = self._setup_three_tools()
        intelligence = SimpleNamespace(domains=["event"])

        man_token = request_tool_manifests_ctx.set(manifests)
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, _hitl_map = ReactToolSelector().select(intelligence=intelligence)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert [t.name for t in wrapped] == [m.name for m in manifests]

    def test_cap_without_intelligence_still_truncates(self, monkeypatch) -> None:
        """No intelligence → no priority set; the cap still applies (legacy behavior)."""
        monkeypatch.setattr(settings, "react_agent_max_tools", 2)
        manifests, ctx = self._setup_three_tools()

        man_token = request_tool_manifests_ctx.set(manifests)
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            wrapped, _hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)

        assert [t.name for t in wrapped] == [manifests[0].name, manifests[1].name]


class TestDestructiveHintForcesConfirmation:
    """In iterative mode every tool of a server shares ONE HITL flag.

    ``_expand_iterative_user_mcp`` returns ``server_hitl`` for all of them, so a
    user who turned confirmation off for a mostly read-only server — a
    reasonable thing to do for a finance server one mostly queries — would have
    ``knowledge__forget``, ``billing__cancel_subscription`` and
    ``connections__disconnect_institution`` execute with no confirmation at all.

    A tool the server itself declares destructive gets one regardless. This is
    tightening only: the spec requires annotations to be treated as untrusted,
    and the worst a lying server buys is a confirmation nobody needed.
    """

    @staticmethod
    def _adapter(tool_name: str, annotations: dict | None) -> UserMCPToolAdapter:
        return UserMCPToolAdapter.from_discovered_tool(
            server_id=_SERVER_ID,
            user_id=UUID(int=1),
            server_name="era",
            tool_name=tool_name,
            description=f"User MCP tool {tool_name}",
            input_schema={"type": "object", "properties": {}},
            annotations=annotations,
        )

    def _select(self, adapters: list[UserMCPToolAdapter], *, server_hitl: bool) -> dict[str, bool]:
        task_manifest = _manifest(_TASK_TOOL_NAME, hitl=server_hitl)
        ctx = UserMCPToolsContext()
        ctx.tool_instances[_TASK_TOOL_NAME] = SimpleNamespace(name=_TASK_TOOL_NAME)
        for adapter in adapters:
            ctx.tool_instances[adapter.name] = adapter
        ctx.tool_manifests = [task_manifest]

        man_token = request_tool_manifests_ctx.set([task_manifest])
        ctx_token = user_mcp_tools_ctx.set(ctx)
        try:
            _wrapped, hitl_map = ReactToolSelector().select(intelligence=None)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)
        return hitl_map

    def test_a_declared_destructive_tool_is_confirmed_even_when_the_server_is_not(self):
        forget = self._adapter("knowledge__forget", {"destructive_hint": True})
        listing = self._adapter("accounts__list_financial_accounts", None)

        hitl_map = self._select([forget, listing], server_hitl=False)

        assert hitl_map[forget.name] is True, "a destructive tool must be confirmed"
        assert hitl_map[listing.name] is False, "its siblings keep the server setting"

    def test_a_not_read_only_hint_alone_does_not_force_confirmation(self):
        """Only a DESTRUCTIVE declaration forces it; an additive update would
        otherwise put a prompt in front of every ordinary write."""
        remember = self._adapter(
            "knowledge__remember", {"read_only_hint": False, "destructive_hint": False}
        )
        assert self._select([remember], server_hitl=False)[remember.name] is False

    def test_a_read_only_claim_never_removes_a_confirmation(self):
        """The untrusted direction: a server cannot talk its way out of HITL."""
        tool = self._adapter("accounts__manage_account", {"read_only_hint": True})
        assert self._select([tool], server_hitl=True)[tool.name] is True

    def test_a_server_with_confirmation_on_is_unchanged(self):
        tool = self._adapter("knowledge__forget", {"destructive_hint": True})
        assert self._select([tool], server_hitl=True)[tool.name] is True

    def test_a_tool_without_hints_follows_the_server(self):
        tool = self._adapter("accounts__list_financial_accounts", None)
        assert self._select([tool], server_hitl=False)[tool.name] is False
