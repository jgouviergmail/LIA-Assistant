"""Cross-component rendering contract for the HTML card layer.

Every card component turns tool payloads — data that comes from the user's
mailbox, contacts, the web, or an MCP server — into HTML that is injected into
the assistant's answer. Two failure modes are silent by construction:

1. **Escaping** — an unescaped field lets remote content (an email subject, a
   place name, a web snippet) inject markup into the response. Nothing raises;
   the card simply renders attacker-controlled HTML.
2. **Robustness** — a card that raises on a missing key does not "fail", it
   makes the whole widget vanish from the answer. Payload shapes vary by
   provider (Google vs Apple vs Microsoft) and by tool version, so every card
   must survive an empty, partial, or wrongly-typed payload.

The suite is parameterised over the renderer's OWN component registry, so a
newly registered card is covered the day it is wired — no per-card opt-in.
"""

from html.parser import HTMLParser
from typing import Any

import pytest

from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    Viewport,
)
from src.domains.agents.display.html_renderer import HtmlRenderer

pytestmark = pytest.mark.unit


# ============================================================================
# COMPONENT REGISTRY (deduplicated: several domains share one card class)
# ============================================================================


def _registered_components() -> list[tuple[str, BaseComponent]]:
    """One entry per component CLASS, labelled by its first domain key."""
    seen: set[type] = set()
    components: list[tuple[str, BaseComponent]] = []
    for domain, component in HtmlRenderer()._components.items():
        if type(component) in seen:
            continue
        seen.add(type(component))
        components.append((domain, component))
    return components


COMPONENTS = _registered_components()
COMPONENT_IDS = [type(component).__name__ for _domain, component in COMPONENTS]


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(viewport=Viewport.DESKTOP, language="fr")


# Markup-bearing payloads: the same hostile string is planted in every plausible
# field name so each card picks it up wherever it reads from.
XSS_PAYLOAD = '<script>alert("xss")</script>'
ATTR_BREAKOUT = '" onerror="alert(1)'

_HOSTILE_SCALARS: dict[str, Any] = dict.fromkeys(
    (
        "name",
        "title",
        "subject",
        "summary",
        "displayName",
        "description",
        "snippet",
        "content",
        "body",
        "text",
        "label",
        "address",
        "formattedAddress",
        "location",
        "author",
        "source",
        "domain",
        "message",
        "note",
        "notes",
        "vicinity",
        "extract",
        "city",
        "condition",
        "status",
        "filename",
        "mimeType",
        "phone",
        "email",
    ),
    XSS_PAYLOAD,
)


def _hostile_payload() -> dict[str, Any]:
    """A payload whose every plausible field carries markup."""
    payload: dict[str, Any] = dict(_HOSTILE_SCALARS)
    payload.update(
        {
            "names": [{"displayName": XSS_PAYLOAD, "givenName": XSS_PAYLOAD}],
            "emailAddresses": [{"value": f"a@b.com{ATTR_BREAKOUT}", "type": "work"}],
            "phoneNumbers": [{"value": f"+33{ATTR_BREAKOUT}", "type": "mobile"}],
            "organizations": [{"name": XSS_PAYLOAD, "title": XSS_PAYLOAD}],
            "addresses": [{"formattedValue": XSS_PAYLOAD, "type": "home"}],
            "url": f"https://example.com/{ATTR_BREAKOUT}",
            "webLink": f"https://example.com/{ATTR_BREAKOUT}",
            "link": f"https://example.com/{ATTR_BREAKOUT}",
            "photo": f"https://example.com/p.png{ATTR_BREAKOUT}",
            "photos": [{"url": f"https://example.com/p.png{ATTR_BREAKOUT}"}],
            "attachments": [{"filename": XSS_PAYLOAD, "mimeType": "application/pdf"}],
            "labels": [XSS_PAYLOAD],
            "labelIds": [XSS_PAYLOAD],
            "results": [{"title": XSS_PAYLOAD, "url": "https://example.com"}],
            "steps": [
                {
                    "instruction": XSS_PAYLOAD,
                    "distance_meters": 800,
                    # Transit colors flow into an inline style attribute (route card).
                    "transit": {
                        "line_name": XSS_PAYLOAD,
                        "line_color": f"#fff{ATTR_BREAKOUT}",
                        "line_text_color": f"#000{ATTR_BREAKOUT}",
                        "vehicle_type": "SUBWAY",
                        "departure_stop": XSS_PAYLOAD,
                        "arrival_stop": XSS_PAYLOAD,
                    },
                }
            ],
            "reviews": [{"author_name": XSS_PAYLOAD, "text": XSS_PAYLOAD, "rating": 4}],
        }
    )
    return payload


# Payload shapes a card can legitimately receive from a degraded upstream.
# Every shape below is one PRODUCERS ACTUALLY EMIT: providers null out fields,
# the registry flattens multi-valued fields to a scalar (``payload.names`` is a
# string there), and JSON/MCP sources send numbers as strings.
DEGENERATE_PAYLOADS: list[tuple[str, dict[str, Any]]] = [
    ("empty", {}),
    ("all-none", dict.fromkeys(_HOSTILE_SCALARS)),
    (
        "scalars-instead-of-collections",
        {
            "names": "Jane Doe",
            "emailAddresses": "jane@example.com",
            "phoneNumbers": "+33612345678",
            "organizations": "ACME",
            "photos": [None],
        },
    ),
    (
        "numbers-as-strings",
        {"name": "Le Bistrot", "rating": "4.5", "userRatingCount": "128", "size": "2048"},
    ),
    ("empty-collections", {"names": [], "emailAddresses": [], "attachments": [], "results": []}),
]


# ============================================================================
# 1. ESCAPING
# ============================================================================


class _MarkupInspector(HTMLParser):
    """Collects the TAGS and ATTRIBUTE NAMES actually parsed out of a fragment.

    Substring matching is not an oracle here: correctly escaped content still
    contains the characters ``onerror=`` as inert text. Only a parser can tell
    an attribute apart from an attribute-looking string.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attributes: list[str] = []
        self.uri_attribute_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        for name, value in attrs:
            self.attributes.append(name.lower())
            if name.lower() in ("href", "src") and value:
                self.uri_attribute_values.append(value.strip().lower())

    handle_startendtag = handle_starttag


def _inspect(html: str) -> _MarkupInspector:
    inspector = _MarkupInspector()
    inspector.feed(html)
    inspector.close()
    return inspector


class TestEscapingContract:
    """Remote content must never reach the response as live markup."""

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_no_script_element_is_produced(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        inspector = _inspect(component.render(_hostile_payload(), ctx))

        assert (
            "script" not in inspector.tags
        ), f"{type(component).__name__} rendered a live <script> element from payload data"

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_no_event_handler_attribute_is_injected(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        """``" onerror="`` inside a value must not close the enclosing attribute."""
        inspector = _inspect(component.render(_hostile_payload(), ctx))

        handlers = [attr for attr in inspector.attributes if attr.startswith("on")]
        assert not handlers, (
            f"{type(component).__name__} injected {handlers} from payload data — "
            "a value escaped its attribute."
        )

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_no_javascript_uri_reaches_href_or_src(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        payload = _hostile_payload()
        payload.update(
            {
                "url": "javascript:alert(1)",
                "webLink": "javascript:alert(1)",
                "link": "javascript:alert(1)",
                "website": "javascript:alert(1)",
                "websiteUri": "javascript:alert(1)",
            }
        )
        inspector = _inspect(component.render(payload, ctx))

        dangerous = [
            value for value in inspector.uri_attribute_values if value.startswith("javascript:")
        ]
        assert not dangerous, f"{type(component).__name__} emitted a javascript: URI: {dangerous}"

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_rendered_list_is_escaped_too(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        inspector = _inspect(component.render_list([_hostile_payload(), _hostile_payload()], ctx))

        assert "script" not in inspector.tags
        assert not [attr for attr in inspector.attributes if attr.startswith("on")]


# ============================================================================
# 2. ROBUSTNESS
# ============================================================================


class TestRobustnessContract:
    """A degraded payload must degrade the card, never remove the widget."""

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    @pytest.mark.parametrize(
        ("shape", "payload"), DEGENERATE_PAYLOADS, ids=[s for s, _ in DEGENERATE_PAYLOADS]
    )
    def test_render_never_raises(
        self,
        domain: str,
        component: BaseComponent,
        shape: str,
        payload: dict[str, Any],
        ctx: RenderContext,
    ) -> None:
        result = component.render(dict(payload), ctx)

        assert isinstance(result, str), f"{type(component).__name__} returned a non-string"

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_render_list_of_empty_items_never_raises(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        assert isinstance(component.render_list([{}, {}], ctx), str)

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    def test_empty_list_renders_nothing(
        self, domain: str, component: BaseComponent, ctx: RenderContext
    ) -> None:
        assert component.render_list([], ctx) == ""

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_every_supported_language_renders(
        self, domain: str, component: BaseComponent, language: str
    ) -> None:
        """Backend canonical Chinese is ``zh-CN``; no locale may crash a card."""
        context = RenderContext(language=language)

        assert isinstance(component.render(_hostile_payload(), context), str)

    @pytest.mark.parametrize(("domain", "component"), COMPONENTS, ids=COMPONENT_IDS)
    @pytest.mark.parametrize("viewport", list(Viewport))
    def test_every_viewport_renders(
        self, domain: str, component: BaseComponent, viewport: Viewport
    ) -> None:
        context = RenderContext(viewport=viewport)

        assert isinstance(component.render(_hostile_payload(), context), str)


# ============================================================================
# 3. LIST SEMANTICS
# ============================================================================


class TestRenderListSemantics:
    """``render_list`` bounds volume and drops cards that validated to nothing."""

    class _Counting(BaseComponent):
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def render(self, data: dict[str, Any], ctx: RenderContext, **_kwargs: Any) -> str:
            self.calls.append(data)
            return f"<div>{data.get('n', '')}</div>"

    class _EmptyForOdd(BaseComponent):
        def render(self, data: dict[str, Any], ctx: RenderContext, **_kwargs: Any) -> str:
            return "" if data["n"] % 2 else f"<div>{data['n']}</div>"

    def test_max_items_caps_the_number_of_rendered_cards(self) -> None:
        component = self._Counting()

        component.render_list([{"n": i} for i in range(10)], RenderContext(max_items=3))

        assert [call["n"] for call in component.calls] == [0, 1, 2]

    def test_position_flags_are_passed_to_each_card(self) -> None:
        seen: list[tuple[bool, bool]] = []

        class _Flags(BaseComponent):
            def render(
                self,
                data: dict[str, Any],
                ctx: RenderContext,
                is_first_item: bool = False,
                is_last_item: bool = False,
            ) -> str:
                seen.append((is_first_item, is_last_item))
                return "<div></div>"

        _Flags().render_list([{"n": 0}, {"n": 1}, {"n": 2}], RenderContext())

        assert seen == [(True, False), (False, False), (False, True)]

    def test_cards_that_render_empty_are_dropped(self) -> None:
        html = self._EmptyForOdd().render_list([{"n": i} for i in range(4)], RenderContext())

        assert html == "<div>0</div>\n<div>2</div>"

    def test_output_is_compacted_for_markdown_injection(self) -> None:
        class _Spaced(BaseComponent):
            def render(self, data: dict[str, Any], ctx: RenderContext, **_kwargs: Any) -> str:
                return "<div>\n   <span>x</span>\n</div>"

        html = _Spaced().render_list([{"n": 0}], RenderContext())

        assert html == "<div><span>x</span></div>"

    def test_nested_level_is_clamped_to_three(self) -> None:
        assert BaseComponent._nested_class(RenderContext(nested_level=0)) == ""
        assert BaseComponent._nested_class(RenderContext(nested_level=2)) == "lia--nested-2"
        assert BaseComponent._nested_class(RenderContext(nested_level=99)) == "lia--nested-3"
