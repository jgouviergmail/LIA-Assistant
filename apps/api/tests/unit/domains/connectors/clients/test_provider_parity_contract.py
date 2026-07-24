"""Provider-parity contract for the connector client families.

Only ONE provider is active per functional category (email, calendar, contacts,
tasks): the tools call whichever client the user connected. ``protocols.py``
declares the interface that makes the swap transparent — but a ``Protocol`` is
structural typing, so nothing verified it at runtime and the module was never
even imported. A renamed parameter, a missing method, or a provider absent from
the client registry would only surface as a runtime ``TypeError`` in the hands
of the users of that one provider.

This module makes the contract executable, in the spirit of the boot-time
registry completeness asserts (ADR-085):

1. **Registry completeness** — every connector type of a Protocol-backed
   category resolves to a registered client class. ``ClientRegistry`` swallows
   ``ImportError`` at initialisation, so a broken import would otherwise empty
   the registry silently.
2. **Signature parity** — every client implements every Protocol method with
   the same parameter names, in the same order, with the same required/optional
   split. Keyword calls stay valid AND positional calls keep their meaning.
3. **Freshness contract** — the read operations of the email and contacts
   families answer with ``from_cache`` / ``cached_at``, the two fields
   ``calculate_cache_age_seconds`` needs to report data freshness. A provider
   that omits them, or that fabricates ``cached_at``, makes stale data look
   brand new.
"""

import inspect
from typing import Any

import pytest

from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients import protocols
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType

pytestmark = pytest.mark.unit


# Functional categories that declare a client Protocol. Categories without one
# (smart_home, telephony) are single-provider today and have no swap contract.
CATEGORY_PROTOCOLS: dict[str, type] = {
    "email": protocols.EmailClientProtocol,
    "calendar": protocols.CalendarClientProtocol,
    "contacts": protocols.ContactsClientProtocol,
    "tasks": protocols.TasksClientProtocol,
}


def _protocol_methods(protocol: type) -> list[str]:
    """Public coroutine members declared by a Protocol."""
    return sorted(
        name
        for name in dir(protocol)
        if not name.startswith("_") and callable(getattr(protocol, name, None))
    )


def _parameters(func: Any) -> list[tuple[str, bool]]:
    """(name, is_required) for every parameter but ``self``, in declaration order."""
    return [
        (name, param.default is inspect.Parameter.empty)
        for name, param in inspect.signature(func).parameters.items()
        if name != "self"
    ]


def _category_cases() -> list[tuple[str, ConnectorType, type]]:
    """(category, connector type, protocol) for every Protocol-backed provider."""
    cases: list[tuple[str, ConnectorType, type]] = []
    for category, protocol in CATEGORY_PROTOCOLS.items():
        for connector_type in sorted(
            CONNECTOR_FUNCTIONAL_CATEGORIES[category], key=lambda ct: ct.value
        ):
            cases.append((category, connector_type, protocol))
    return cases


CATEGORY_CASES = _category_cases()
CASE_IDS = [f"{category}:{ct.value}" for category, ct, _ in CATEGORY_CASES]


# ============================================================================
# 1. REGISTRY COMPLETENESS
# ============================================================================


class TestRegistryCompleteness:
    """Every swappable provider must resolve to a client class."""

    @pytest.mark.parametrize(
        ("category", "connector_type", "_protocol"), CATEGORY_CASES, ids=CASE_IDS
    )
    def test_every_provider_has_a_registered_client(
        self, category: str, connector_type: ConnectorType, _protocol: type
    ) -> None:
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None, (
            f"{connector_type.value} belongs to the '{category}' category but no client "
            "class is registered — ClientRegistry swallows ImportError, so a broken "
            "import empties the registry without failing the boot."
        )

    def test_no_protocol_backed_category_is_empty(self) -> None:
        for category in CATEGORY_PROTOCOLS:
            assert CONNECTOR_FUNCTIONAL_CATEGORIES[category], f"category '{category}' is empty"


# ============================================================================
# 2. SIGNATURE PARITY
# ============================================================================


class TestSignatureParity:
    """A provider swap must never change how a tool calls its client."""

    @pytest.mark.parametrize(
        ("category", "connector_type", "protocol"), CATEGORY_CASES, ids=CASE_IDS
    )
    def test_client_implements_every_protocol_method(
        self, category: str, connector_type: ConnectorType, protocol: type
    ) -> None:
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None

        missing = [m for m in _protocol_methods(protocol) if not hasattr(client_class, m)]
        assert not missing, (
            f"{client_class.__name__} ({category}) does not implement {missing} — "
            f"a tool switching to this provider would raise AttributeError."
        )

    @pytest.mark.parametrize(
        ("category", "connector_type", "protocol"), CATEGORY_CASES, ids=CASE_IDS
    )
    def test_parameter_names_and_order_match_the_protocol(
        self, category: str, connector_type: ConnectorType, protocol: type
    ) -> None:
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None

        mismatches: list[str] = []
        for method in _protocol_methods(protocol):
            expected = [name for name, _ in _parameters(getattr(protocol, method))]
            actual = [name for name, _ in _parameters(getattr(client_class, method))]
            if expected != actual:
                mismatches.append(f"{method}: {actual} != protocol {expected}")

        assert not mismatches, f"{client_class.__name__} ({category}) drifted: {mismatches}"

    @pytest.mark.parametrize(
        ("category", "connector_type", "protocol"), CATEGORY_CASES, ids=CASE_IDS
    )
    def test_required_parameters_match_the_protocol(
        self, category: str, connector_type: ConnectorType, protocol: type
    ) -> None:
        """A provider must not demand an argument the others make optional."""
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None

        mismatches: list[str] = []
        for method in _protocol_methods(protocol):
            expected = [
                name for name, required in _parameters(getattr(protocol, method)) if required
            ]
            actual = [
                name for name, required in _parameters(getattr(client_class, method)) if required
            ]
            if expected != actual:
                mismatches.append(f"{method}: required {actual} != protocol {expected}")

        assert not mismatches, f"{client_class.__name__} ({category}) drifted: {mismatches}"

    @pytest.mark.parametrize(
        ("category", "connector_type", "protocol"), CATEGORY_CASES, ids=CASE_IDS
    )
    def test_protocol_methods_are_coroutines_on_every_client(
        self, category: str, connector_type: ConnectorType, protocol: type
    ) -> None:
        """Tools always ``await`` these calls."""
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None

        not_async = [
            method
            for method in _protocol_methods(protocol)
            if not inspect.iscoroutinefunction(getattr(client_class, method))
        ]
        assert not not_async, f"{client_class.__name__} ({category}): {not_async} are not async"


# ============================================================================
# 3. FRESHNESS CONTRACT
# ============================================================================


class TestFreshnessContract:
    """``from_cache``/``cached_at`` must mean the same thing on every provider."""

    # Read operations whose payload feeds the freshness indicator.
    FRESHNESS_SOURCES: dict[str, tuple[str, ...]] = {
        "email": ("search_emails", "get_message"),
        "contacts": ("search_contacts", "list_connections"),
    }

    # Provider -> unit-test module that pins ITS freshness behaviour end to end.
    PROVIDER_TEST_MODULES: dict[ConnectorType, str] = {
        ConnectorType.GOOGLE_GMAIL: "tests/unit/connectors/test_google_gmail_client.py",
        ConnectorType.APPLE_EMAIL: (
            "tests/unit/domains/connectors/clients/test_apple_email_client.py"
        ),
        ConnectorType.MICROSOFT_OUTLOOK: (
            "tests/unit/domains/connectors/clients/test_microsoft_outlook_client.py"
        ),
        ConnectorType.GOOGLE_CONTACTS: "tests/unit/connectors/test_connector_service.py",
        ConnectorType.APPLE_CONTACTS: (
            "tests/unit/domains/connectors/clients/test_apple_contacts_client.py"
        ),
        ConnectorType.MICROSOFT_CONTACTS: (
            "tests/unit/domains/connectors/clients/test_microsoft_contacts_client.py"
        ),
    }

    @pytest.mark.parametrize("category", sorted(FRESHNESS_SOURCES))
    def test_every_provider_of_the_category_has_its_own_test_module(self, category: str) -> None:
        """Guards the guard: a new provider must not join without its own suite."""
        from tests._repo_paths import find_apps_api_root

        api_root = find_apps_api_root()
        for connector_type in sorted(
            CONNECTOR_FUNCTIONAL_CATEGORIES[category], key=lambda ct: ct.value
        ):
            relative = self.PROVIDER_TEST_MODULES.get(connector_type)
            assert relative is not None, (
                f"{connector_type.value} joined the '{category}' category without being "
                "declared here — add its client test module and this mapping entry."
            )
            assert (api_root / relative).is_file(), (
                f"{relative} is declared as the test module of {connector_type.value} "
                "but does not exist."
            )

    @pytest.mark.parametrize(
        ("category", "connector_type", "_protocol"),
        [case for case in CATEGORY_CASES if case[0] in ("email", "contacts")],
        ids=[cid for cid in CASE_IDS if cid.startswith(("email:", "contacts:"))],
    )
    def test_read_operations_declare_the_freshness_fields(
        self, category: str, connector_type: ConnectorType, _protocol: type
    ) -> None:
        """Every read path must mention both freshness fields in its own source.

        The two fields are what ``calculate_cache_age_seconds`` consumes; a
        provider that never sets them silently reports "unknown freshness" for
        every payload it returns.
        """
        client_class = ClientRegistry.get_client_class(connector_type)
        assert client_class is not None

        source = inspect.getsource(inspect.getmodule(client_class))
        declares_from_cache = "from_cache" in source
        declares_cached_at = FIELD_CACHED_AT in source or "FIELD_CACHED_AT" in source

        assert declares_from_cache, f"{client_class.__name__} never sets from_cache"
        assert declares_cached_at, f"{client_class.__name__} never sets {FIELD_CACHED_AT}"


class TestFabricatedCachedAtGuard:
    """``cached_at`` must be READ from the cache entry, never stamped on a hit.

    Stamping ``datetime.now()`` on a cache HIT makes every cached payload look
    freshly fetched: ``calculate_cache_age_seconds`` then reports an age of zero
    whatever the real age of the data. The regression this guards against
    shipped in the Apple contacts client.
    """

    # Matches ``<key>: datetime.now(UTC).isoformat() if from_cache`` whether the
    # key is the literal string or the FIELD_CACHED_AT constant.
    PATTERN = (
        rf"(?:FIELD_CACHED_AT|[\"']{FIELD_CACHED_AT}[\"'])\s*:\s*"
        r"datetime\.now\(UTC\)\.isoformat\(\)\s+if\s+"
    )

    def test_pattern_detects_the_historical_regression(self) -> None:
        """Oracle for the guard itself: it must flag the exact shipped defect."""
        import re

        shipped_defect = (
            "        return {\n"
            '            "results": results,\n'
            '            "from_cache": from_cache,\n'
            '            "cached_at": datetime.now(UTC).isoformat() if from_cache else None,\n'
            "        }\n"
        )
        constant_variant = (
            "            FIELD_CACHED_AT: datetime.now(UTC).isoformat() if from_cache else None,\n"
        )

        assert re.search(self.PATTERN, shipped_defect)
        assert re.search(self.PATTERN, constant_variant)

    def test_no_client_fabricates_a_cache_timestamp(self) -> None:
        import re

        from src.domains.connectors.clients import (
            apple_contacts_client,
            apple_email_client,
            google_gmail_client,
            google_people_client,
            microsoft_contacts_client,
            microsoft_outlook_client,
        )

        pattern = re.compile(self.PATTERN)
        offenders = [
            module.__name__
            for module in (
                google_gmail_client,
                google_people_client,
                apple_email_client,
                apple_contacts_client,
                microsoft_outlook_client,
                microsoft_contacts_client,
            )
            if pattern.search(inspect.getsource(module))
        ]

        assert not offenders, (
            f"{offenders} stamp {FIELD_CACHED_AT} with the current time on a cache hit; "
            "the write timestamp must travel with the cached payload."
        )
