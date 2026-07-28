"""Completeness and semantics of the registry content-trust classification.

The classification decides whether a registry payload reaches the LLM marked as
third-party data. Two properties matter and are pinned here:

- **exhaustivity** — a new ``RegistryItemType`` without a classification must
  break the build, not silently default to trusted (ADR-085 doctrine, the same
  guard the draft display registry carries);
- **fail-closed resolution** — an unknown or missing type resolves to EXTERNAL,
  because a payload whose provenance cannot be established must not reach the
  model unmarked.

The per-type expectations below are deliberately explicit rather than derived
from the table: a test that recomputes the table it checks proves nothing. Each
EXTERNAL entry names the field an attacker can write.
"""

from __future__ import annotations

import pytest

from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.data_registry.trust import (
    TRUST_BY_REGISTRY_TYPE,
    ContentTrust,
    assert_trust_registry_completeness,
    is_external,
)

pytestmark = [pytest.mark.unit]


# Types whose payload can carry free text written by someone other than the
# user or LIA, with the attacker-writable field named.
EXPECTED_EXTERNAL: dict[RegistryItemType, str] = {
    RegistryItemType.EMAIL: "body/subject/sender name",
    RegistryItemType.EVENT: "summary/description authored by the organiser",
    RegistryItemType.CONTACT: "notes/organisation from directory sync",
    RegistryItemType.CALENDAR: "name/description of a shared calendar",
    RegistryItemType.TASK: "title/notes of a shared task list",
    RegistryItemType.FILE: "name/snippet of a file shared with the user",
    RegistryItemType.PLACE: "editorial summary and reviews",
    RegistryItemType.WIKIPEDIA_ARTICLE: "article extract",
    RegistryItemType.SEARCH_RESULT: "search synthesis",
    RegistryItemType.WEB_SEARCH: "aggregated snippets",
    RegistryItemType.WEB_PAGE: "fetched page content",
    RegistryItemType.BROWSER_PAGE: "accessibility tree of an arbitrary page",
    RegistryItemType.MCP_RESULT: "third-party MCP server output",
    RegistryItemType.MCP_APP: "third-party MCP widget payload",
    RegistryItemType.SKILL_APP: "rich output of a URL-imported skill",
}

# Types that are machine-generated or authored by the user / LIA itself.
EXPECTED_INTERNAL: frozenset[RegistryItemType] = frozenset(
    {
        RegistryItemType.LOCATION,
        RegistryItemType.WEATHER,
        RegistryItemType.ROUTE,
        RegistryItemType.HUE_LIGHT,
        RegistryItemType.DRAFT,
        RegistryItemType.CHART,
        RegistryItemType.REMINDER,
        RegistryItemType.NOTE,
        RegistryItemType.CALENDAR_SLOT,
    }
)


def test_every_registry_type_is_classified() -> None:
    """A new RegistryItemType without a trust entry must refuse to boot."""
    assert_trust_registry_completeness()
    assert set(TRUST_BY_REGISTRY_TYPE) == set(RegistryItemType)


def test_the_two_expectation_sets_cover_every_type() -> None:
    """Guards the test itself: adding a type forces updating one of the sets."""
    covered = set(EXPECTED_EXTERNAL) | EXPECTED_INTERNAL
    missing = set(RegistryItemType) - covered
    assert not missing, (
        f"New RegistryItemType(s) {sorted(t.value for t in missing)} are not listed in "
        "EXPECTED_EXTERNAL (with the attacker-writable field) or EXPECTED_INTERNAL."
    )
    assert not (set(EXPECTED_EXTERNAL) & EXPECTED_INTERNAL)


@pytest.mark.parametrize(
    ("item_type", "reason"), sorted(EXPECTED_EXTERNAL.items(), key=lambda kv: kv[0].value)
)
def test_third_party_authored_types_are_external(item_type: RegistryItemType, reason: str) -> None:
    """Each type whose payload has an attacker-writable field is EXTERNAL."""
    assert TRUST_BY_REGISTRY_TYPE[item_type] is ContentTrust.EXTERNAL, (
        f"{item_type.value} carries third-party text ({reason}) — it must be EXTERNAL "
        "so the LLM sees it marked as data."
    )
    assert is_external(item_type) is True


@pytest.mark.parametrize("item_type", sorted(EXPECTED_INTERNAL, key=lambda t: t.value))
def test_machine_or_user_authored_types_are_internal(item_type: RegistryItemType) -> None:
    """Machine/user-authored types stay unmarked: marking them is pure token cost."""
    assert TRUST_BY_REGISTRY_TYPE[item_type] is ContentTrust.INTERNAL
    assert is_external(item_type) is False


def test_assert_reports_the_missing_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure message must name what to add, not just that something is missing."""
    truncated = dict(TRUST_BY_REGISTRY_TYPE)
    truncated.pop(RegistryItemType.EMAIL)
    monkeypatch.setattr("src.domains.agents.data_registry.trust.TRUST_BY_REGISTRY_TYPE", truncated)
    with pytest.raises(AssertionError, match="EMAIL"):
        assert_trust_registry_completeness()


class TestFailClosedResolution:
    """Provenance that cannot be established resolves to EXTERNAL."""

    def test_none_is_external(self) -> None:
        assert is_external(None) is True

    def test_unknown_string_is_external(self) -> None:
        assert is_external("SOMETHING_NEW_FROM_A_FUTURE_RELEASE") is True

    def test_empty_string_is_external(self) -> None:
        assert is_external("") is True

    def test_raw_string_value_resolves_like_the_enum(self) -> None:
        """Checkpoint round-trips hand back plain strings, not enum members."""
        assert is_external("EMAIL") is is_external(RegistryItemType.EMAIL) is True
        assert is_external("WEATHER") is is_external(RegistryItemType.WEATHER) is False
