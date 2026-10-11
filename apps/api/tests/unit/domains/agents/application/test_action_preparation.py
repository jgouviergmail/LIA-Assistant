"""An action envelope cannot silently accept a read or a future unhandled schema."""

from dataclasses import replace
from uuid import uuid4

import pytest

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.schemas import PreferencePatch

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", ["read", "schema"])
def test_action_envelope_refuses_incompatible_catalogue_contracts(fault: str) -> None:
    spec = APPLICATION_OPERATIONS.get("preferences.update")
    changed = (
        replace(spec, kind=OperationKind.READ)
        if fault == "read"
        else replace(spec, version=spec.version + 1)
    )
    with pytest.raises(ValueError):
        build_action_content(
            uuid4(), changed, PreferencePatch(font_size=17), {"font_size": 16}, {"font_size": 17}
        )
