"""Every Maps price the seed bundle adds after the 2026-09-23 audit has a migration.

An upgraded instance never replays the bundle: it deletes and rewrites the
whole ``google_api_pricing`` table, which would erase a price an administrator
set. So a price only reaches production through a migration. ADR-332's Dynamic
Maps row was added to the bundle alone, and production kept the interactive map
switched off (``map_load_config`` refuses an unpriced load) -- measured on the
v2.5.0 deployment, 2026-10-04. This guard reads every migration that declares
``GOOGLE_PRICES`` and requires each recent bundle row to be one of them, at the
same SKU and price.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path
from types import ModuleType

_API_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _API_ROOT / "alembic" / "versions"
_SEED_FILE = (
    _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "google_api_pricing_seed.sql"
)
#: Rows dated before the audit migration (d5f8b2a6c9e3) reached instances when
#: the bundle was still replayed; every later one must travel by migration.
_AUDIT = datetime.fromisoformat("2026-09-23T00:00:00+00:00")
_SEED_ROW = re.compile(
    r"\(gen_random_uuid\(\), '(?P<api>[^']+)', '(?P<endpoint>[^']+)', "
    r"'(?P<sku>[^']+)', (?P<price>[0-9.]+), '(?P<effective>[^']+)'"
)


def _seed_rows() -> dict[tuple[str, str], tuple[str, float, datetime]]:
    rows = {}
    for match in _SEED_ROW.finditer(_SEED_FILE.read_text(encoding="utf-8")):
        rows[(match["api"], match["endpoint"])] = (
            match["sku"],
            float(match["price"]),
            datetime.fromisoformat(match["effective"]),
        )
    return rows


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_google_prices_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migrated_prices() -> dict[tuple[str, str], tuple[str, float]]:
    prices = {}
    for path in sorted(_VERSIONS.glob("*.py")):
        if "GOOGLE_PRICES" not in path.read_text(encoding="utf-8"):
            continue
        for row in _load(path).GOOGLE_PRICES:
            prices[(row.api_name, row.endpoint)] = (row.sku_name, float(row.price))
    return prices


def test_the_seed_parses_to_dated_rows() -> None:
    """The pattern reads the bundle (protects the guard against format drift)."""
    rows = _seed_rows()
    assert len(rows) >= 20, f"only {len(rows)} rows read from the seed bundle"
    assert ("maps_javascript", "/dynamicmap") in rows


def test_every_recent_seed_price_travels_by_migration() -> None:
    """A price dated after the audit is written by a migration, identically."""
    migrated = _migrated_prices()
    missing = {
        key: (sku, price)
        for key, (sku, price, effective) in _seed_rows().items()
        if effective >= _AUDIT and migrated.get(key) != (sku, price)
    }
    assert not missing, (
        "Seed rows no upgraded instance will ever receive -- add them to a "
        f"migration's GOOGLE_PRICES (see ef46f93d7745): {missing}"
    )
