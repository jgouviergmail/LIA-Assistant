"""Read a field off a value that may be an object OR a mapping.

Both shapes are legitimate in this domain, so neither access form can be
assumed. Two independent reasons produce the mapping form:

* ``clarification_node`` deliberately rebuilds the semantic verdict through
  ``dataclasses.asdict`` and writes a mapping back into the state — the common
  case by far, and the one that bit;
* a checkpointed object that no longer passes its own validation comes back as a
  plain ``dict``: the serializer rebuilds through the constructor, so a failing
  member degrades in silence rather than raising (measured and pinned in
  ``tests/unit/domains/conversations/test_checkpoint_allowlist_guard.py``).

A VALID nested model does come back typed — this helper exists for the two cases
above, not because every resumed object is degraded.

Attribute access alone therefore fails HALF the time, and fails SILENTLY:
``getattr(mapping, "issues", None)`` returns None rather than raising, so the
branch is skipped instead of erroring. That is how the FOR_EACH directive
stopped being injected after a clarification.

This lived as three identical private copies (``_issue_field``, ``_issue_attr``,
``_step_attr``) before being pulled here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def read_field(value: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` off an object or a mapping.

    Args:
        value: The record to read from, in either shape.
        name: Field name.
        default: Returned when the field is absent or holds None.

    Returns:
        The field value, or ``default``. Note that a field explicitly set to
        None is indistinguishable from an absent one — callers needing that
        distinction must not use this helper.
    """
    # Mapping FIRST, deliberately: a dict carries attributes of its own, so
    # trying getattr before .get would answer `read_field(d, "items")` with the
    # built-in method instead of the value stored under "items".
    if isinstance(value, Mapping):
        found = value.get(name)
    else:
        found = getattr(value, name, None)

    return default if found is None else found
