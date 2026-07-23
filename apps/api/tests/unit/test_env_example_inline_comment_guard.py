"""CI guard: no inline comment on EMPTY-valued variables in the .env examples.

Docker compose does NOT strip inline comments when the value before ``#`` is
empty: ``KEY=   # comment`` reaches the process with ``# comment`` AS THE
VALUE. Task's ``dotenv:`` loader behaves the same way. This broke three
variables in the field before this guard existed (2026-07): the dev WebAuthn
rpId became a comment string (security program Lot 1), then ``DOCKER_HOST``
poisoned every ``task``-launched docker command with ``tcp://127.0.0.1:2375``.

The ``MFASettings`` validator catches the WEBAUTHN_* pair at boot; this guard
closes the CLASS for every variable by scanning the example files themselves.
Comments for empty-valued variables belong on their own line ABOVE the
variable.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

ENV_EXAMPLE_FILES = [".env.example", ".env.prod.example", ".env.min.prod"]

# KEY= followed only by whitespace then a comment — the poisoned shape.
_EMPTY_VALUE_INLINE_COMMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=[ \t]*#")


@pytest.mark.unit
@pytest.mark.parametrize("filename", ENV_EXAMPLE_FILES)
def test_no_inline_comment_on_empty_valued_variables(filename: str) -> None:
    """Every ``KEY=   # comment`` line is a future runtime value leak."""
    path = REPO_ROOT / filename
    if not path.exists():
        pytest.skip(f"{filename} not present in this checkout")

    offenders = [
        f"{filename}:{lineno}: {line.rstrip()}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _EMPTY_VALUE_INLINE_COMMENT.match(line)
    ]

    assert offenders == [], (
        "Inline comment on an EMPTY-valued variable — docker compose and Task "
        "dotenv pass the comment AS the value. Move the comment to its own "
        "line above the variable:\n" + "\n".join(offenders)
    )
