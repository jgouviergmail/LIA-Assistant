"""Startup errors that must STOP the boot, not be logged and forgotten.

Measured 2026-09-03 (ADR-263): three completeness guards in
``startup/agents.py`` — capability directives (ADR-191), tool categories
(ADR-256) and capability agents (ADR-085) — each raised ``RuntimeError`` with
a docstring promising the application "refuses to boot". The step's own
``except (RuntimeError, ImportError, ValueError)`` caught every one of them and
only logged: the boot continued, ``set_global_registry`` was never reached, and
``get_global_registry()`` lazily built an EMPTY registry. The instance came up
with no catalogue at all, announced by a single ERROR line.

So the promise and the code disagreed — the bug is the contradiction, not the
docstring (CLAUDE.md, Observability & honesty). A guard whose failure is
swallowed is a comment.

``StartupCompletenessError`` restores the promise WITHOUT losing the
resilience the broad handler was there for: a completeness failure is a
declaration defect the developer must fix and it propagates; an unrelated
``RuntimeError`` (a transport that will not open, an optional import) is still
caught and logged, exactly as before.
"""

from __future__ import annotations


class StartupCompletenessError(RuntimeError):
    """A registry/catalogue declaration is incomplete: the boot must stop.

    Raised by the boot-time completeness asserts. Subclasses ``RuntimeError``
    so existing ``except RuntimeError`` handlers keep their shape — they must
    re-raise this type explicitly, which is the point: swallowing it has to be
    a deliberate act, never a default.
    """
