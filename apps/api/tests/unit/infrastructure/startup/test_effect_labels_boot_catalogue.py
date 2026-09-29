"""Boot must validate the catalogue it is building, never an empty singleton."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.infrastructure.startup.agents import _assert_effect_completeness
from src.infrastructure.startup.errors import StartupCompletenessError

pytestmark = pytest.mark.unit


def test_boot_refuses_an_unlabelled_act_even_when_global_catalogue_is_empty() -> None:
    manifest = SimpleNamespace(name="audit_unlabelled_tool", mutation_policy="reversible")
    catalogue = SimpleNamespace(list_tool_manifests=lambda: [manifest])
    empty = SimpleNamespace(list_tool_manifests=lambda: [])
    with (
        patch("src.domains.agents.effects.runtime.assert_effect_gate_completeness"),
        patch("src.domains.agents.registry.get_global_registry", return_value=empty),
        pytest.raises(StartupCompletenessError, match="Effect labels incomplete"),
    ):
        _assert_effect_completeness(catalogue)
