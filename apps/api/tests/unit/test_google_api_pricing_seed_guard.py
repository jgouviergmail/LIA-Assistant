"""Guard: the Google API pricing seed matches the SKUs the code actually triggers.

The 2026-08 opportunity audit found the Places field masks request `reviews`
and `editorialSummary`, which bill the *Enterprise + Atmosphere* SKUs
(Text Search $40, Nearby $40, Details $25 per 1000) — while the seed billed
the *Pro* SKUs ($32/$32/$17). A cost shown to the user is a claim: it is
exact, or it does not exist (CLAUDE.md, "Constraints & verdicts").

This guard pins two invariants:

1. The seed prices for the Places operations match the SKU tier the field
   masks actually trigger (verified against the official price list 2026-08).
2. Every ``track_google_api_call("<api>", "<endpoint>")`` literal in ``src/``
   has a matching seed row — a tracked call with no pricing row is silently
   billed at zero (`get_cost_per_request` returns 0 on a cache miss), which
   under-reports user costs without any error.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _API_ROOT / "src"
_SEED_FILE = (
    _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "google_api_pricing_seed.sql"
)

_SEED_ROW_RE = re.compile(
    r"\(gen_random_uuid\(\),\s*'(?P<api>[^']+)',\s*'(?P<endpoint>[^']+)',\s*"
    r"'(?P<sku>[^']+)',\s*(?P<price>[0-9]+\.[0-9]+)"
)

_TRACK_CALL_RE = re.compile(
    r"track_google_api_call\(\s*\"(?P<api>[^\"]+)\",\s*\"(?P<endpoint>[^\"]+)\""
)

# Prices per 1000 requests, verified on the official Google Maps Platform
# price list (2026-08). The Places field masks include `reviews` and
# `editorialSummary` -> Enterprise + Atmosphere tier. The `:lite` variants
# use a Pro-only field mask -> Pro tier.
_EXPECTED_PLACES_ROWS: dict[tuple[str, str], tuple[str, float]] = {
    ("places", "/places:searchText"): ("Text Search Enterprise + Atmosphere", 40.0),
    ("places", "/places:searchNearby"): ("Nearby Search Enterprise + Atmosphere", 40.0),
    ("places", "/places/{id}"): ("Place Details Enterprise + Atmosphere", 25.0),
    ("places", "/places:searchText:lite"): ("Text Search Pro", 32.0),
    ("places", "/places:searchNearby:lite"): ("Nearby Search Pro", 32.0),
}


def _load_seed_rows() -> dict[tuple[str, str], tuple[str, float]]:
    content = _SEED_FILE.read_text(encoding="utf-8")
    rows: dict[tuple[str, str], tuple[str, float]] = {}
    for match in _SEED_ROW_RE.finditer(content):
        rows[(match.group("api"), match.group("endpoint"))] = (
            match.group("sku"),
            float(match.group("price")),
        )
    return rows


def test_seed_file_parses_to_rows() -> None:
    """The regex actually extracts rows (protects the guard against format drift)."""
    rows = _load_seed_rows()
    assert len(rows) >= 9, f"Seed parsing broke: only {len(rows)} rows extracted"


@pytest.mark.parametrize(("key", "expected"), sorted(_EXPECTED_PLACES_ROWS.items()))
def test_places_seed_row_matches_triggered_sku(
    key: tuple[str, str], expected: tuple[str, float]
) -> None:
    """Each Places operation is billed at the SKU tier its field mask triggers."""
    rows = _load_seed_rows()
    assert key in rows, f"Missing seed row for {key}"
    sku_name, price = rows[key]
    expected_sku, expected_price = expected
    assert price == expected_price, (
        f"{key}: seed bills ${price}/1000 but the field mask triggers "
        f"'{expected_sku}' at ${expected_price}/1000"
    )
    assert sku_name == expected_sku, f"{key}: SKU name '{sku_name}' != '{expected_sku}'"


def test_every_tracked_endpoint_has_a_seed_row() -> None:
    """A tracked (api, endpoint) literal without a seed row is billed $0 silently."""
    rows = _load_seed_rows()
    missing: set[tuple[str, str]] = set()
    for py_file in _SRC_DIR.rglob("*.py"):
        for match in _TRACK_CALL_RE.finditer(py_file.read_text(encoding="utf-8")):
            key = (match.group("api"), match.group("endpoint"))
            if key not in rows:
                missing.add(key)
    assert not missing, (
        "track_google_api_call sites without a google_api_pricing seed row "
        f"(silently billed at $0): {sorted(missing)}"
    )
