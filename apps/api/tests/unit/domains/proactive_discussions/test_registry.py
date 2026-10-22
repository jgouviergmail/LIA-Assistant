"""The public source catalogue cannot omit an installed source or its port."""

import pytest

from src.domains.proactive_discussions.registry import SOURCE_REGISTRY, assert_registry_complete
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit


def test_every_source_is_described() -> None:
    assert_registry_complete(SOURCE_REGISTRY, installed=frozenset(SourceKey))
    assert SOURCE_REGISTRY[SourceKey.PORTRAIT].dependencies == ()


def test_missing_source_stops_boot() -> None:
    incomplete = dict(SOURCE_REGISTRY)
    del incomplete[SourceKey.SMS]
    with pytest.raises(RuntimeError, match="source"):
        assert_registry_complete(incomplete)


def test_missing_port_stops_boot() -> None:
    with pytest.raises(RuntimeError, match="port"):
        assert_registry_complete(SOURCE_REGISTRY, installed=frozenset({SourceKey.CALENDAR}))
