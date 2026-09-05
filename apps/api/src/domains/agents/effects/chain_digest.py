"""How a register row becomes bytes, once and for all (ADR-263, lot 5).

Everything the tamper-evident chain claims rests on this file: a digest that
two different rows can share is forgeable, and a digest that one row can
produce two of — across a driver upgrade, say — turns every chain in production
red on a day nobody touched the data.

The design's first draft had both defects, demonstrated before any code:

- ``sha256("a" + "|" + "b|c")`` equals ``sha256("a|b" + "|" + "c")``: two
  different rows, one digest;
- ``str(datetime)`` is variable-width, so the same instant renders differently
  depending on whether it carries microseconds.

So the encoding here is:

- **length-prefixed** — ``<len>:<key>=<len>:<token>`` makes a field boundary
  impossible to move;
- **typed** — ``n`` absent, ``b`` boolean, ``i`` integer, ``t`` instant,
  ``u`` identifier, ``s`` text — so ``None``, ``"None"``, ``""``, ``1`` and
  ``"1"`` are five distinct things;
- **fixed-width where a renderer has a choice** — instants are UTC with six
  digits of microseconds, always;
- **sorted by key**, so the order columns happen to be declared in is not part
  of the meaning;
- **versioned** — the version is written INSIDE the bytes, so a digest can
  never be re-read under a rule it was not computed with.

A type this module does not know is REFUSED, never stringified: ``str()`` on an
unknown type is a rendering nobody pinned, and it would be discovered the day
it silently changed.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final

#: The encoding's rule number, written into every digest. Changing ANYTHING
#: about the rendering below means incrementing this — never editing a frozen
#: vector, which would silently invalidate every chain already written.
DIGEST_VERSION: Final[int] = 1

#: Fixed-width instant rendering. ``%f`` is always six digits, so a value with
#: no microseconds does not render shorter than one that has them.
_INSTANT_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S.%fZ"


def _token(value: Any) -> str:
    """One typed, self-delimiting rendering of a single value.

    Args:
        value: The column value, as SQLAlchemy handed it back.

    Returns:
        A token whose first two characters name the type.

    Raises:
        ValueError: A naive datetime — guessing its zone would make the digest
            depend on the server that computed it.
        TypeError: A type this encoding does not know. Refusing is the point:
            ``str()`` on an unknown type is a rendering nobody pinned.
    """
    if value is None:
        return "n:"
    # An Enum is unwrapped FIRST: a stored enum must digest as the value the
    # database holds, never as its member name (the convention the ledger's
    # ``values_callable`` already pays for).
    if isinstance(value, Enum):
        return _token(value.value)
    # Before int: ``isinstance(True, int)`` is True, and a boolean that
    # digested as 1 would collide with the integer 1.
    if isinstance(value, bool):
        return f"b:{'true' if value else 'false'}"
    if isinstance(value, int):
        return f"i:{value:d}"
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                "a naive datetime cannot be digested: its instant depends on the "
                "server's zone, so the same row would digest differently elsewhere"
            )
        return "t:" + value.astimezone(UTC).strftime(_INSTANT_FORMAT)
    if isinstance(value, uuid.UUID):
        return f"u:{str(value).lower()}"
    if isinstance(value, bytes):
        return f"y:{value.hex()}"
    if isinstance(value, str):
        return f"s:{value}"
    raise TypeError(
        f"{type(value).__name__} has no pinned rendering in digest v{DIGEST_VERSION}; "
        "add one deliberately and increment the version rather than letting "
        "str() decide"
    )


def canonical_bytes(fields: Mapping[str, Any]) -> bytes:
    """The exact bytes a digest is taken over.

    Exposed for the tests that read the encoding rather than only its hash —
    a frozen vector proves equality, this proves SHAPE.

    Args:
        fields: Column name -> value.

    Returns:
        The canonical encoding, version first.
    """
    parts = [f"v{DIGEST_VERSION};"]
    for key in sorted(fields):
        token = _token(fields[key])
        parts.append(f"{len(key)}:{key}={len(token)}:{token}")
    return "".join(parts).encode("utf-8")


def row_digest(fields: Mapping[str, Any]) -> str:
    """The digest of one register row's business columns.

    Args:
        fields: Column name -> value, already narrowed to the columns the
            chain covers (an explicit allowlist lives with each register).

    Returns:
        Lowercase hexadecimal SHA-256.
    """
    return hashlib.sha256(canonical_bytes(fields)).hexdigest()
