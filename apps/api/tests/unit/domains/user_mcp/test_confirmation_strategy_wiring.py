"""The account's strategy and a server's ReAct shape reach what a run builds (spec 2026-10-30).

D1: a personal server left on « like my strategy » follows the ACCOUNT, and only an
account that never chose follows the instance; a tool's own choice comes first (D6),
read once per run with the account's strategy. D4: an iterative server's ReAct shape
is resolved once, by the task manifest's builder, and the selector reads the manifest.
D2: the page is handed the defaults; D3: a received copy keeps none of these choices.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.registry.confirmation_rule import requires_confirmation
from src.domains.user_mcp.defaults import published_defaults
from src.domains.user_mcp.schemas import UserMCPServerUpdate
from src.domains.users.schemas import UserUpdate
from src.infrastructure.mcp.confirmation import (
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest
from src.infrastructure.mcp.user_context import cleanup_user_mcp_tools, setup_user_mcp_tools

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_vector_cache() -> Iterator[None]:
    from src.domains.agents.services.tool_vectors import reset_server_vector_cache

    reset_server_vector_cache()
    yield
    reset_server_vector_cache()


@pytest.fixture(autouse=True)
def _short_sessions() -> Iterator[None]:
    @asynccontextmanager
    async def _session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    with patch("src.infrastructure.database.session.get_db_context", _session):
        yield


def _server(*, hitl: bool | None, iterative: bool = False, shape: bool | None = None) -> Any:
    """A server row double shaped like test_user_context's (the preparation reads more)."""
    server = MagicMock()
    server.id = uuid4()
    server.name = "Notes"
    server.url = "https://notes.example/mcp"
    server.timeout_seconds = 30
    server.hitl_required = hitl
    server.iterative_mode = iterative
    server.react_expand_iterative = shape
    server.domain_description = "Personal notes"
    server.tool_embeddings_cache = None
    server.auth_type = "none"
    return server


_READ: dict[str, Any] = {
    "name": "read_note",
    "description": "Read a note",
    "input_schema": {},
    "annotations": {"read_only_hint": True},
}
_DELETE: dict[str, Any] = {
    "name": "delete_note",
    "description": "Delete a note",
    "input_schema": {"type": "object"},
    "annotations": {"destructive_hint": True},
}


async def _registered(
    server: Any,
    *,
    account: bool | None,
    tools: list[dict[str, Any]] | None = None,
    choices: dict[str, StoredToolChoice] | None = None,
) -> UserMCPToolsContext:
    """Run the real request path over one fake server; return the turn's context."""
    repository = AsyncMock()
    repository.get_enabled_active_for_user = AsyncMock(return_value=[server])
    repository.account_confirmation = AsyncMock(return_value=account)
    repository.tool_choices = AsyncMock(return_value={server.id: choices or {}})
    entry = MagicMock()
    entry.tools = tools or [_READ]
    entry.reference_content = None
    pool = AsyncMock()
    pool.get_or_connect = AsyncMock(return_value=entry)
    with (
        patch.object(settings, "mcp_user_enabled", True),
        patch("src.domains.user_mcp.repository.UserMCPServerRepository", return_value=repository),
        patch("src.infrastructure.mcp.user_context.get_user_mcp_pool", return_value=pool),
        patch("src.infrastructure.mcp.user_context.build_auth_for_server", return_value=None),
    ):
        token = await setup_user_mcp_tools(uuid4())
    assert token is not None
    ctx = user_mcp_tools_ctx.get()
    assert ctx is not None
    cleanup_user_mcp_tools(token)
    return ctx


class TestTheAccountStrategyReachesTheManifests:
    async def test_a_server_like_my_strategy_follows_the_account(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", False)

        ctx = await _registered(_server(hitl=None), account=True)

        (manifest,) = ctx.tool_manifests
        assert requires_confirmation(manifest)  # a read, asked because the ACCOUNT says so

    async def test_the_server_s_own_choice_wins_over_the_account(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", True)

        ctx = await _registered(_server(hitl=False), account=True)

        (manifest,) = ctx.tool_manifests
        assert not requires_confirmation(manifest)  # declared read-only, followed

    async def test_an_account_that_never_chose_follows_the_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", True)

        ctx = await _registered(_server(hitl=None), account=None)

        (manifest,) = ctx.tool_manifests
        assert requires_confirmation(manifest)


def _never(tool: dict[str, Any]) -> StoredToolChoice:
    return StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(tool))


class TestAToolsOwnChoiceReachesItsManifest:
    async def test_never_on_a_declared_destruction_is_approved_in_advance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", False)

        ctx = await _registered(
            _server(hitl=None),
            account=True,
            tools=[_DELETE],
            choices={"delete_note": _never(_DELETE)},
        )

        (manifest,) = ctx.tool_manifests
        assert manifest.approved_in_advance is True
        assert not requires_confirmation(manifest), "never wins over the account's always"

    async def test_always_on_a_declared_read_asks_on_a_server_following_declarations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", False)
        always = StoredToolChoice(ToolChoice.ALWAYS, declaration_fingerprint(_READ))

        ctx = await _registered(_server(hitl=False), account=None, choices={"read_note": always})

        (manifest,) = ctx.tool_manifests
        assert requires_confirmation(manifest)

    async def test_a_never_chosen_against_another_declaration_does_not_apply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", False)
        stale = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_READ))

        ctx = await _registered(
            _server(hitl=True), account=None, tools=[_DELETE], choices={"delete_note": stale}
        )

        (manifest,) = ctx.tool_manifests
        assert manifest.approved_in_advance is False
        assert requires_confirmation(manifest), "suspended: the server's always decides"

    async def test_an_iterative_server_s_individuals_carry_their_choices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "mcp_react_enabled", True)
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)

        ctx = await _registered(
            _server(hitl=True, iterative=True),
            account=None,
            tools=[_DELETE],
            choices={"delete_note": _never(_DELETE)},
        )

        (task,) = ctx.tool_manifests
        # Owner decision 2026-10-31: the task asks when one of its tools would — a
        # « never ask » tool does not, even under the server's « always ask ».
        assert not requires_confirmation(task)
        (individual,) = ctx.reactive_tool_manifests.values()
        assert individual.approved_in_advance is True

    async def test_an_unreadable_choices_read_falls_back_to_the_levels_below(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reads are forgiving: a run never fails on what it cannot read."""
        monkeypatch.setattr(settings, "mcp_hitl_required", True)
        server = _server(hitl=None)

        ctx = await _registered(server, account=None, choices={"read_note": "never"})  # type: ignore[dict-item]

        (manifest,) = ctx.tool_manifests
        assert requires_confirmation(manifest)


class TestADedicatedAgentIsAskedBeforeItsTask:
    """Owner decision 2026-10-31: one question before the task whenever a tool would ask.

    That answer covers the agent's calls and the task runs to completion — under « follow
    its declarations » too, where the first sensitive inner call used to become a card and
    lose the rest of the task (lot 0, H1 and H3).
    """

    @pytest.fixture(autouse=True)
    def _dedicated_agents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "mcp_react_enabled", True)
        monkeypatch.setattr(settings, "mcp_hitl_required", False)

    async def test_a_server_following_its_declarations_asks_when_a_tool_would(self) -> None:
        ctx = await _registered(
            _server(hitl=False, iterative=True), account=None, tools=[_READ, _DELETE]
        )

        (task,) = ctx.tool_manifests
        assert requires_confirmation(task)

    async def test_tools_that_ask_nothing_leave_the_task_unasked(self) -> None:
        ctx = await _registered(_server(hitl=False, iterative=True), account=None, tools=[_READ])

        (task,) = ctx.tool_manifests
        assert not requires_confirmation(task)

    async def test_an_always_ask_tool_makes_the_task_ask(self) -> None:
        always = {"read_note": StoredToolChoice(ToolChoice.ALWAYS, "any")}

        ctx = await _registered(
            _server(hitl=False, iterative=True), account=None, tools=[_READ], choices=always
        )

        (task,) = ctx.tool_manifests
        assert requires_confirmation(task)


class TestTheReactShapeTravelsOnTheTaskManifest:
    @pytest.mark.parametrize(
        ("shape", "instance", "expected"),
        [
            (False, True, False),
            (True, False, True),
            (None, True, True),
            (None, False, False),
        ],
    )
    async def test_the_server_s_shape_else_the_instance(
        self,
        monkeypatch: pytest.MonkeyPatch,
        shape: bool | None,
        instance: bool,
        expected: bool,
    ) -> None:
        monkeypatch.setattr(settings, "mcp_react_enabled", True)
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", instance)

        ctx = await _registered(_server(hitl=False, iterative=True, shape=shape), account=None)

        (task,) = ctx.tool_manifests
        assert task.delegates_execution
        assert task.react_expand is expected

    def test_the_administrator_task_follows_the_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", False)

        manifest = build_mcp_react_task_manifest(
            "mcp_admin_task", "mcp_admin_agent", "admin", "d", [], [], False, mcp_origin="admin"
        )

        assert manifest.react_expand is False


class TestThePageIsHandedTheDefaults:
    @pytest.mark.parametrize(
        ("account", "instance", "effective"),
        [
            (None, True, True),
            (None, False, False),
            (True, False, True),
            (False, True, False),
        ],
    )
    def test_the_confirmation_defaults(
        self,
        monkeypatch: pytest.MonkeyPatch,
        account: bool | None,
        instance: bool,
        effective: bool,
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", instance)

        defaults = published_defaults(account)

        assert defaults.confirmation_instance is instance
        assert defaults.confirmation_account is account
        assert defaults.confirmation_effective is effective

    def test_the_shape_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", False)
        monkeypatch.setattr(settings, "mcp_react_enabled", False)

        defaults = published_defaults(None)

        assert defaults.react_direct_tools_default is False
        assert defaults.dedicated_agents_available is False


class TestWritesAreStrict:
    def test_the_account_strategy_takes_booleans_only(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(mcp_hitl_required="true")  # type: ignore[arg-type]

    def test_an_explicit_null_returns_the_account_to_the_default(self) -> None:
        patch_ = UserUpdate(mcp_hitl_required=None)

        assert patch_.model_dump(exclude_unset=True) == {"mcp_hitl_required": None}

    def test_an_explicit_null_returns_a_server_s_shape_to_the_default(self) -> None:
        patch_ = UserMCPServerUpdate(react_expand_iterative=None)

        assert patch_.model_dump(exclude_unset=True) == {"react_expand_iterative": None}


class TestAReceivedCopyKeepsNoneOfTheseChoices:
    async def test_an_offline_install_writes_no_shape_and_no_confirmation(self) -> None:
        from src.domains.user_mcp.models import UserMCPAuthType
        from src.domains.user_mcp.schemas import UserMCPServerCreate
        from src.domains.user_mcp.service import UserMCPServerService

        created: dict[str, Any] = {}
        service = UserMCPServerService(MagicMock())
        service.repository = MagicMock()
        service.repository.lock_owner_for_creation = AsyncMock()

        async def _create(values: dict[str, Any]) -> Any:
            created.update(values)
            return SimpleNamespace(id=uuid4(), **values)

        service.repository.create = _create
        service._check_creation_constraints = AsyncMock()  # type: ignore[method-assign]
        service._validate_creation_endpoint = AsyncMock()  # type: ignore[method-assign]
        data = UserMCPServerCreate(
            name="Shared",
            url="https://shared.example/mcp",
            auth_type="none",
            hitl_required=False,
            iterative_mode=True,
            react_expand_iterative=False,
        )
        offline = SimpleNamespace(
            auth_type=UserMCPAuthType.NONE,
            status="inactive",
            oauth_scopes=None,
            credential_header=None,
        )

        await service.create_server(UUID(int=1), data, offline_install=offline)  # type: ignore[arg-type]

        assert created["hitl_required"] is None
        assert created["react_expand_iterative"] is None
        assert created["iterative_mode"] is True  # the sender's knowledge of the server
        assert created["is_enabled"] is False  # activated on the page, synthesis in view
