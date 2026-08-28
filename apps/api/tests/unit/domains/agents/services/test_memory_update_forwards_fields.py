"""An automated update must be able to revise every field it may revise.

Measured in production on 2026-08-28: two standing instructions — imperative,
addressed to the assistant, textbook `procedural` — were stored as `personal`.
The extraction then kept *updating* them, and the category never moved, because
``supersede_with_update`` accepts a ``category`` and the extractor was the only
field it did not forward. A misclassification was therefore permanent: no model
proposal, and no amount of re-stating the rule, could ever correct it.

The guard below is structural on purpose: it compares what the service is
willing to revise with what the caller actually sends, so the next field added
to the service cannot be silently dropped on the way in.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.domains.memories.schemas import ExtractedMemory
from src.domains.memories.service import MemoryService


def _supersede_call_kwargs() -> set[str]:
    """Keyword names passed to ``supersede_with_update`` by the extractor."""
    source = Path(
        inspect.getsourcefile(  # type: ignore[arg-type]
            __import__(
                "src.domains.agents.services.memory_extractor",
                fromlist=["memory_extractor"],
            )
        )
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "supersede_with_update":
            return {kw.arg for kw in node.keywords if kw.arg}
    raise AssertionError("the extractor no longer calls supersede_with_update")


@pytest.mark.unit
class TestUpdateForwardsEveryRevisableField:
    def test_the_category_is_forwarded(self) -> None:
        """The regression that froze two rules in the wrong category."""
        assert "category" in _supersede_call_kwargs()

    def test_every_field_both_sides_agree_on_is_forwarded(self) -> None:
        """What the model may propose AND the service may revise must travel."""
        service_fields = set(inspect.signature(MemoryService.supersede_with_update).parameters)
        service_fields -= {"self", "memory"}
        model_fields = set(ExtractedMemory.model_fields)
        revisable = service_fields & model_fields

        forwarded = _supersede_call_kwargs() - {"memory"}
        missing = revisable - forwarded

        assert not missing, (
            f"the extractor drops {sorted(missing)} on update — the service accepts "
            "them and the model can propose them, so they are silently lost"
        )
