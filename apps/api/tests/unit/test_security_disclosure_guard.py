"""SEC-023 guard — the security disclosure channel must stay real and current.

Regressions this pins:
- `/.well-known/security.txt` returned 404 (no file shipped).
- `SECURITY.md` advertised a dead contact domain (`lia-assistant.dev`, no
  DNS/MX) and fictitious supported versions (`6.x.x` / `5.5.x`) for a `1.x` app.

The tests assert an RFC 9116 `security.txt` exists with a *future* `Expires`,
that the contact points at a live channel (GitHub Security Advisories), and that
neither the dead domain nor the fictitious version branches reappear.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

# apps/api/tests/unit/<file> → repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SECURITY_TXT = _REPO_ROOT / "apps" / "web" / "public" / ".well-known" / "security.txt"
_SECURITY_MD = _REPO_ROOT / "SECURITY.md"

_DEAD_DOMAIN = "lia-assistant.dev"
_FICTITIOUS_VERSIONS = ("6.x.x", "5.5.x")


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file missing: {path}"
    return path.read_text(encoding="utf-8")


def _fields(security_txt: str) -> dict[str, list[str]]:
    """Parse RFC 9116 `Field: value` lines (comments/blank lines ignored)."""
    fields: dict[str, list[str]] = {}
    for line in security_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, _, value = line.partition(":")
        fields.setdefault(name.strip().lower(), []).append(value.strip())
    return fields


def test_security_txt_exists_and_has_required_fields() -> None:
    """RFC 9116 mandates at least Contact and Expires."""
    fields = _fields(_read(_SECURITY_TXT))
    assert fields.get("contact"), "security.txt must declare at least one Contact"
    assert fields.get("expires"), "security.txt must declare Expires (RFC 9116)"


def test_security_txt_expires_is_in_the_future() -> None:
    """A stale (past) Expires makes the file non-compliant — fail early so it is
    renewed before it lapses."""
    expires_raw = _fields(_read(_SECURITY_TXT))["expires"][0]
    expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    assert expires > datetime.now(
        UTC
    ), f"security.txt Expires={expires_raw} is in the past — renew it"


def test_security_txt_contact_is_reachable_channel() -> None:
    """Contact must be a live channel, not the dead placeholder domain."""
    contacts = _fields(_read(_SECURITY_TXT))["contact"]
    joined = " ".join(contacts)
    assert _DEAD_DOMAIN not in joined, "dead contact domain reintroduced in security.txt"
    assert any(
        c.startswith("https://") or c.startswith("mailto:") for c in contacts
    ), "Contact must be a URL or mailto"


@pytest.mark.parametrize("needle", (_DEAD_DOMAIN, *_FICTITIOUS_VERSIONS))
def test_security_md_has_no_dead_domain_or_fictitious_versions(needle: str) -> None:
    """SECURITY.md must not resurrect the dead domain or the 6.x/5.5.x branches."""
    assert needle not in _read(_SECURITY_MD), f"SECURITY.md must not reference {needle!r}"


def test_security_md_points_to_the_disclosure_channel() -> None:
    """The policy must link the actual reporting entry point."""
    content = _read(_SECURITY_MD)
    assert "security/advisories/new" in content, "SECURITY.md must link GitHub advisory reporting"
