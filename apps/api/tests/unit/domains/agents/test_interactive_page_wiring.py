"""Wiring: taxonomy, manifests, switch, timeouts, widget registries (ADR-370)."""

from typing import get_args

import pytest

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import AGENT_INTERACTIVE_PAGE
from src.domains.agents.data_registry.message_widgets import PERSISTED_WIDGET_TYPES
from src.domains.agents.data_registry.models import INTERACTIVE_WIDGET_TYPES, RegistryItemType
from src.domains.agents.data_registry.trust import is_external
from src.domains.agents.display.sentinel_filter import strip_widget_sentinels
from src.domains.agents.interactive_page.catalogue_manifests import (
    PageModeName,
    generate_interactive_page_catalogue_manifest,
    interactive_page_agent_manifest,
)
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.utils.type_domain_mapping import TYPE_TO_DOMAIN_MAP
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability
from src.domains.interactive_pages.schemas import PageMode
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY

pytestmark = pytest.mark.unit


class TestDomain:
    def test_is_routable_with_a_derived_result_key(self) -> None:
        domain = DOMAIN_REGISTRY["interactive_page"]
        assert domain.result_key == "interactive_pages"
        assert domain.is_routable is True
        assert domain.agent_names == [AGENT_INTERACTIVE_PAGE]

    def test_tells_the_thing_from_its_code(self) -> None:
        """The whole routing rests on this sentence: « the game » is not « its code »."""
        description = DOMAIN_REGISTRY["interactive_page"].description
        assert "NOT" in description
        assert "source code" in description

    def test_the_neighbour_sends_a_page_here(self) -> None:
        assert "interactive_page" in DOMAIN_REGISTRY["document_generation"].description


class TestManifests:
    def test_the_agent_wraps_the_tool(self) -> None:
        assert interactive_page_agent_manifest.name == AGENT_INTERACTIVE_PAGE
        assert interactive_page_agent_manifest.tools == ["generate_interactive_page"]

    def test_publishes_the_exact_modes_the_tool_validates(self) -> None:
        """An enforced constraint is published (ADR-184), from ONE list."""
        parameters = generate_interactive_page_catalogue_manifest.parameters
        mode = next(p for p in parameters if p.name == "mode")
        (constraint,) = [c for c in mode.constraints if c.kind == "enum"]
        assert set(constraint.value) == {m.value for m in PageMode}
        assert set(get_args(PageModeName)) == {m.value for m in PageMode}

    def test_declares_what_it_owes_the_person(self) -> None:
        assert generate_interactive_page_catalogue_manifest.mutation_policy == "artefact"

    def test_is_never_offered_to_the_initiative(self) -> None:
        """A proactive page would be a paid surprise."""
        from src.domains.agents.registry.catalogue import is_initiative_eligible

        assert is_initiative_eligible(generate_interactive_page_catalogue_manifest) is False


class TestSwitch:
    def test_owns_its_agent_so_a_switch_removes_it_from_every_turn(self) -> None:
        spec = CAPABILITY_SPECS[PlatformCapability.INTERACTIVE_PAGES]
        assert spec.agents == (AGENT_INTERACTIVE_PAGE,)
        assert spec.env_flag == "interactive_page_enabled"
        assert spec.service_enforced is True
        assert spec.family == "media"


class TestTimeoutFamily:
    def test_a_page_waits_for_its_writer_as_a_document_does(self) -> None:
        """Measured 2026-11-05: a stylized page takes longer than a document's floor."""
        from src.domains.agents.orchestration.step_timeouts import (
            TOOL_LLM_SLOTS,
            compute_step_timeout,
        )

        assert TOOL_LLM_SLOTS["generate_interactive_page"] == ("interactive_page",)
        assert compute_step_timeout("generate_interactive_page", None) == compute_step_timeout(
            "generate_document", None
        )


class TestItsOwnSlot:
    def test_declared_like_the_slot_it_left(self) -> None:
        page = LLM_TYPES_REGISTRY["interactive_page"]
        document = LLM_TYPES_REGISTRY["document_generation"]

        assert page.category == document.category
        assert page.required_capabilities == document.required_capabilities
        assert page.required_kind == document.required_kind
        assert page.power_tier == document.power_tier
        assert page.description_key == "settings.admin.llmConfig.types.interactive_page"

    def test_with_no_row_a_page_runs_as_it_did_on_the_document_slot(self) -> None:
        assert LLM_DEFAULTS["interactive_page"] == LLM_DEFAULTS["document_generation"]


class TestWidgetRegistries:
    def test_rendered_and_persisted_as_a_widget(self) -> None:
        assert RegistryItemType.PAGE_APP in INTERACTIVE_WIDGET_TYPES
        assert RegistryItemType.PAGE_APP.value in PERSISTED_WIDGET_TYPES

    def test_is_treated_as_untrusted(self) -> None:
        """Its title was written by a model that may have read a third party's mail."""
        assert is_external(RegistryItemType.PAGE_APP) is True

    def test_files_its_payload_under_its_own_key(self) -> None:
        assert TYPE_TO_DOMAIN_MAP["PAGE_APP"] == ("page_app", "page_apps")

    def test_a_sentinel_the_model_wrote_is_stripped(self) -> None:
        """Only the host emits one: a forged id would mount another page."""
        content = 'Voici.<div class="lia-page-app" data-registry-id="page_app_x"></div>'
        cleaned, count = strip_widget_sentinels(content)
        assert count == 1
        assert "lia-page-app" not in cleaned


class TestSentinel:
    def test_holds_no_text_for_a_copy_a_voice_or_an_export_to_read(self) -> None:
        from src.domains.agents.display.components.base import RenderContext
        from src.domains.agents.display.components.page_app_sentinel import PageAppSentinel

        html = PageAppSentinel().render(
            {FIELD_REGISTRY_ID: 'page_app_"x'}, RenderContext(language="fr")
        )
        assert html == '<div class="lia-page-app" data-registry-id="page_app_&quot;x"></div>'
