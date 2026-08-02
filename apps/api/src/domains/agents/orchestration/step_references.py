"""The syntax of a cross-step reference: ``$steps.<step_id>.<field.path>``.

A plan step reads an earlier step's output through a ``$steps`` reference; this
module holds the one regex that says what such a reference looks like when the
FULL field path matters.

Deliberately NOT the only ``$steps`` regex in the repository, and the difference
is semantic rather than accidental. ``semantic_validator`` carries its own,
narrower pattern (``_STEPS_REFERENCE_PATTERN``) that captures only the leading
DOMAIN key: its ghost-dependency check compares ``contacts`` against the
producing step's ``result_key``, so it must stop at the first segment. Merging
the two would break one of them — measured::

    "$steps.s1.contacts[0].name"
      this module        -> ("s1", "contacts[0].name")
      semantic_validator -> ("s1", "contacts")

Kept as a module-level constant rather than a class attribute so that reading
the syntax costs nothing: ``capability_directives`` is a leaf the HTTP schemas
import, and it must not drag orchestration machinery in behind it.
"""

from __future__ import annotations

import re

#: Captures ``(step_id, field_path)`` from a ``$steps`` reference.
#:
#: The field-path group requires >= 2 characters, so a one-character terminal
#: field (``$steps.s.x``) is NOT matched. Real tool fields are multi-character
#: (``value``, ``resource_name``, ``summary``), so the gap never bites in
#: practice — it is pinned by tests to keep any future change deliberate.
STEPS_REFERENCE_PATTERN = re.compile(
    r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_\[\]\.\*]+)"
)
