"""Naming a consultation for a human, without inventing a vocabulary (ADR-263).

The design decision this file pins, and the measurement that produced it.

I first planned to reuse ``execution.steps`` — the ⚙ trace's per-tool wording.
Measured: it covers **81 of the 119** registered tools, and its style is a
progress sentence with an ellipsis (« Activating Hue scene... »). A register
that says what the assistant DID is not a progress bar, and 38 tools would have
shown a raw technical name. Authoring the missing wording meant 38 × 6 = 228
new strings, plus 6 more for every tool ever added.

So the readable label is the **domain**, which is already the codebase's single
source of truth for the vocabulary (``DOMAIN_REGISTRY``, 28 entries): 28 nouns
in 6 languages, and a new tool needs no new string at all. The tool name is
displayed next to it, so no detail is lost — it is the technical half, and the
technical half already has a home.

Resolution order, most authoritative first:

1. the tool's manifest, whose ``agent`` names its domain (96 of 119 tools);
2. the tool's NAME, matched against the same registry (the 23 with no manifest
   — the browser sub-tools and the legacy readers CLAUDE.md documents);
3. an explicit entry, for the handful whose name says nothing (``get_calls``);
4. ``unknown``, which a shrink-only guard refuses to let grow.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.treatment_labels import (
    TREATMENT_DOMAIN_OVERRIDES,
    UNKNOWN_DOMAIN,
    treatment_domain,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(scope="module")
def registry() -> object:
    """One catalogue, loaded once — for the per-capability expectations below.

    The COMPLETENESS check does not use this: it must see the catalogue a
    deployment registers, which no in-process fixture can reproduce (see
    ``_measured``).
    """
    from src.domains.agents.effects.treatment_labels import reset_domain_cache
    from src.domains.agents.registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue
    from src.domains.agents.tools.tool_registry import _import_tool_modules

    _import_tool_modules()
    loaded = AgentRegistry()
    initialize_catalogue(loaded)
    # The resolution is memoised on the write path; a fixture handing out a
    # DIFFERENT registry must not read another one's answers.
    reset_domain_cache()
    return loaded


#: Families the test environment leaves OFF and a deployment turns ON. Measured
#: 2026-09-04: the suite saw 119 tools, the container registered 128, and the
#: four self-diagnostics tools it could not name refused the boot of a build
#: whose every gate was green. A completeness guard measured on the narrow
#: catalogue passes on anything a flag hides.
DEPLOYMENT_FLAGS: dict[str, str] = {
    "DIAGNOSTICS_ENABLED": "true",
    "TELEPHONY_ENABLED": "true",
    "PEERS_ENABLED": "true",
    "DEVOPS_ENABLED": "true",
    "PYTHON_SANDBOX_TOOL_ENABLED": "true",
    "HEALTH_METRICS_ENABLED": "true",
    "SKILLS_ENABLED": "true",
    "SUB_AGENTS_ENABLED": "true",
    "IMAGE_GENERATION_ENABLED": "true",
    "DOCUMENT_GENERATION_ENABLED": "true",
}

#: Measured in a FRESH interpreter, because the conditional tool imports happen
#: at PACKAGE import time: by the time any fixture runs, the families the test
#: environment disabled are already absent and no amount of settings flipping
#: brings them back. A subprocess is also what keeps this guard independent of
#: test ordering — the tool registry is a module-level singleton other suites
#: write probe tools into.
_MEASURE = """
import json
from src.core.i18n import DEFAULT_LANGUAGE
from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS
from src.domains.agents.effects.treatment_labels import treatment_domain
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools import tool_registry

tool_registry.ensure_tools_loaded()
registry = AgentRegistry()
initialize_catalogue(registry)

known = set(TREATMENT_DOMAIN_LABELS.get(DEFAULT_LANGUAGE, TREATMENT_DOMAIN_LABELS["en"]))
names = sorted(tool_registry.get_all_tools())
resolved = {name: treatment_domain(name, registry) for name in names}
print("@@" + json.dumps({
    "tools": names,
    "unreadable": sorted(n for n, d in resolved.items() if d not in known),
    "domains": sorted(set(resolved.values())),
}))
"""


@functools.lru_cache(maxsize=1)
def _measured() -> dict[str, Any]:
    """Run the deployment-catalogue measurement once, in a subprocess."""
    api_root = Path(__file__).resolve().parents[5]
    environment = {**os.environ, **DEPLOYMENT_FLAGS}
    completed = subprocess.run(  # noqa: S603 - our own interpreter, fixed script
        [sys.executable, "-c", _MEASURE],
        cwd=api_root,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0, (
        "the measurement failed: " + completed.stdout[-2000:] + completed.stderr[-2000:]
    )
    marker = [line for line in completed.stdout.splitlines() if line.startswith("@@")]
    assert marker, "no measurement in output: " + completed.stdout[-2000:]
    return dict(json.loads(marker[-1][2:]))


class TestTheManifestIsTheAuthority:
    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("get_emails_tool", "email"),
            ("send_email_tool", "email"),
            ("get_contacts_tool", "contact"),
            ("create_event_tool", "event"),
            ("get_current_weather_tool", "weather"),
            ("control_hue_light_tool", "hue"),
            ("get_health_overview_tool", "health"),
            ("generate_image", "image_generation"),
            ("run_python_tool", "python_sandbox"),
        ],
    )
    def test_a_tool_with_a_manifest_takes_its_agents_domain(
        self, tool_name: str, expected: str, registry: object
    ) -> None:
        assert treatment_domain(tool_name, registry) == expected


class TestTheNameAnswersWhenTheManifestIsSilent:
    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("search_emails_tool", "email"),
            ("get_email_details_tool", "email"),
            ("list_contacts_tool", "contact"),
            ("search_contacts_tool", "contact"),
            ("get_contact_details_tool", "contact"),
            ("search_events_tool", "event"),
            ("get_event_details_tool", "event"),
            ("delete_file_tool", "file"),
            ("list_files_tool", "file"),
            ("search_files_tool", "file"),
            ("get_file_details_tool", "file"),
            ("list_places_tool", "place"),
            ("search_places_tool", "place"),
            ("get_place_details_tool", "place"),
            ("list_tasks_tool", "task"),
            ("get_task_details_tool", "task"),
            ("browser_click_tool", "browser"),
            ("browser_snapshot_tool", "browser"),
            ("get_peer_messages_tool", "peer"),
        ],
    )
    def test_the_registry_recognises_the_name(
        self, tool_name: str, expected: str, registry: object
    ) -> None:
        assert treatment_domain(tool_name, registry) == expected

    def test_an_explicit_entry_covers_a_name_that_says_nothing(self) -> None:
        """« calls » is not a domain; telephony is."""
        assert TREATMENT_DOMAIN_OVERRIDES["get_calls_tool"] == "telephony"
        assert treatment_domain("get_calls_tool") == "telephony"


class TestTheResolutionIsMemoised:
    """The write path resolves the domain of EVERY row it persists.

    A manifest read takes the registry's lock, so a runaway batch would take it
    once per row. Same doctrine as ``resolve_policy``: cache the authoritative
    answers, never a miss taken before the catalogue was loaded — freezing that
    would outrank a manifest landing a moment later, which is the precedence
    the resolver declares.
    """

    def test_a_declared_domain_is_read_once(self, registry: object) -> None:
        from src.domains.agents.effects import treatment_labels

        treatment_labels.reset_domain_cache()
        reads: list[str] = []
        original = treatment_labels._from_manifest

        def _counting(name: str, given: object) -> object:
            reads.append(name)
            return original(name, given)  # type: ignore[arg-type]

        with patch.object(treatment_labels, "_from_manifest", _counting):
            for _ in range(5):
                assert treatment_labels.treatment_domain("get_emails_tool", registry) == "email"

        assert reads == ["get_emails_tool"], f"the manifest was read {len(reads)} times"

    def test_a_MISS_is_not_frozen(self, registry: object) -> None:
        """A tool resolved before its catalogue loads must not stay unknown."""
        from src.domains.agents.effects import treatment_labels

        treatment_labels.reset_domain_cache()
        with patch.object(treatment_labels, "_from_manifest", lambda *_a: None):
            assert treatment_labels.treatment_domain("get_emails_tool", registry) == "email"

        # The manifest is available now; the earlier miss must not shadow it.
        assert treatment_labels.treatment_domain("generate_image", registry) == "image_generation"

    def test_the_cache_is_resettable(self, registry: object) -> None:
        from src.domains.agents.effects import treatment_labels

        treatment_labels.treatment_domain("get_emails_tool", registry)
        treatment_labels.reset_domain_cache()

        assert treatment_labels._domain_cache == {}


class TestAThirdPartyToolIsNotGuessedAt:
    def test_an_mcp_tool_is_its_own_domain(self) -> None:
        """A server names and shapes its own tools; we do not read meaning in."""
        from src.core.constants import MCP_TOOL_NAME_PREFIX

        assert treatment_domain(f"{MCP_TOOL_NAME_PREFIX}github__create_issue") == "mcp"

    def test_a_draft_executor_keeps_its_family(self) -> None:
        assert treatment_domain("draft:email") == "email"


class TestTheFallbackIsNeverASilentHole:
    def test_an_unknown_name_resolves_to_the_declared_unknown(self) -> None:
        assert treatment_domain("totally_made_up_thing") == UNKNOWN_DOMAIN

    def test_the_unknown_domain_is_itself_a_translatable_key(self) -> None:
        """A page must never show a technical name — not even for a surprise."""
        from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS

        assert UNKNOWN_DOMAIN in TREATMENT_DOMAIN_LABELS["fr"]


def _spoken_domains(registry: object) -> set[str]:
    """Every domain a register row can name.

    Three sources, and all three are authoritative for a different reason: the
    taxonomy routes domains, an agent may own a family the taxonomy does not
    route (the Python sandbox is reachable only from the ReAct loop), and an
    explicit override names a domain no tool name spells (``skill``).

    Args:
        registry: A registry with its catalogue loaded.

    Returns:
        The domains the label table must cover, and may not exceed.
    """
    from src.domains.agents.effects.treatment_labels import TREATMENT_DOMAIN_OVERRIDES
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    # What the RESOLVER produces, never a naive strip of the agent name: an
    # agent may qualify its family (``devops_diagnostics_agent``), and the
    # resolver maps that to ``devops``. Reading the raw name here would demand
    # a wording for a domain no row can ever carry.
    resolved = {
        treatment_domain(manifest.name, registry)  # type: ignore[arg-type]
        for manifest in registry.list_tool_manifests()  # type: ignore[attr-defined]
    }
    return (
        set(DOMAIN_REGISTRY)
        | resolved
        | set(TREATMENT_DOMAIN_OVERRIDES.values())
        | set(_measured()["domains"])
    )


class TestEveryDomainCanBeRead:
    def test_every_domain_has_a_label_in_every_language(self, registry: object) -> None:
        from src.core.i18n import SUPPORTED_LANGUAGES
        from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS

        for language in SUPPORTED_LANGUAGES:
            table = TREATMENT_DOMAIN_LABELS.get(language)
            assert table is not None, f"no wording table for {language}"
            for domain in _spoken_domains(registry):
                assert table.get(domain), f"{domain} is unreadable in {language}"

    def test_no_label_exists_for_a_domain_that_does_not(self, registry: object) -> None:
        """The table may not drift ahead of the vocabulary either."""
        from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS

        for language, table in TREATMENT_DOMAIN_LABELS.items():
            extra = set(table) - _spoken_domains(registry) - {UNKNOWN_DOMAIN}
            assert (
                extra == set()
            ), f"{language}: labels for domains that no longer exist: {sorted(extra)}"

    def test_rendering_never_raises(self) -> None:
        from src.core.i18n_treatments import render_treatment_domain

        assert render_treatment_domain("email", "fr")
        assert render_treatment_domain("email", "xx-YY")
        assert render_treatment_domain("nonexistent", "fr")


class TestEveryRegisteredToolResolves:
    def test_the_catalogue_measured_is_the_DEPLOYED_one(self) -> None:
        """The guard must not be narrower than what a container registers.

        The count is a floor, not an equality: a new tool must not have to edit
        this test. What it refuses is the regression that shipped — a guard
        measured only over the families the test environment happens to enable.
        """
        names = set(_measured()["tools"])

        assert len(names) >= 128, f"the catalogue narrowed to {len(names)} tools"
        assert {
            "platform_health_tool",
            "platform_metrics_tool",
            "platform_logs_tool",
            "platform_incidents_tool",
        } <= names, "the flag-gated self-diagnostics tools are not being measured"

    def test_no_registered_tool_falls_through_to_unknown(self) -> None:
        """The boot guard's property, over the DEPLOYED catalogue.

        This is the test that would have caught the API refusing to start.
        """
        unreadable = _measured()["unreadable"]

        assert unreadable == [], (
            f"{len(unreadable)} capability(ies) have no readable domain: {unreadable}. "
            "The boot guard refuses to start on this."
        )
