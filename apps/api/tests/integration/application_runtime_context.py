"""Publish a real turn collector for native application integration flows."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.treatments import is_collecting, treatment_collector
from tests.helpers.runtime_context import installed_runtime_context as _installed_runtime_context


@contextmanager
def installed_runtime_context(
    context: LiaRuntimeContext | None = None, **overrides: Any
) -> Iterator[LiaRuntimeContext]:
    """Install the real runtime and collect its consultations within this flow.

    An enclosing collector keeps its own rows and run identity. Otherwise the
    synchronous collector uses the runtime's normal correlation fallback and
    restores its prior state on both normal and exceptional exits.
    """
    with _installed_runtime_context(context, **overrides) as installed:
        if is_collecting():
            yield installed
        else:
            with treatment_collector():
                yield installed
