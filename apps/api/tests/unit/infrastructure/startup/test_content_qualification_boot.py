"""The CRM native port is bound before serving; repeat boot replaces its owner."""

import ast
import inspect
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.services.qualification import publication
from src.domains.shared import content_qualification as port
from src.infrastructure.startup.registries import init_content_qualification

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_boot_installs_the_actual_native_reader(monkeypatch):
    previous = port._qualifier
    native = AsyncMock(return_value={})
    monkeypatch.setattr(publication, "classify_selected", native)
    try:
        init_content_qualification()
        await port.qualify_selected(
            records=[{"id": "one"}],
            kind="email",
            user_id=uuid4(),
            provider="gmail",
            binding="actual",
            timezone="UTC",
        )
        native.assert_awaited_once()
    finally:
        port.configure_content_qualifier(previous)


def test_lifespan_calls_bootstrap_before_requests():
    from src.main import lifespan

    tree = ast.parse(inspect.getsource(lifespan))
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "init_content_qualification"
        for node in ast.walk(tree)
    )
