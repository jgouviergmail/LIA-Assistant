"""Stable cross-runtime card fixtures: backend output, never hand-written HTML."""

from typing import TypedDict

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.config import DisplayConfig
from src.domains.agents.display.html_renderer import HtmlRenderer
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.places_formatting import format_place_details
from src.domains.agents.tools.routes_tools import (
    _create_route_registry_item,
    _format_route_response,
)
from src.domains.agents.tools.weather_formatting import _format_hourly_response
from src.domains.agents.tools.weather_tools import _get_hourly_forecast_tool_impl
from src.domains.agents.utils.polyline import encode_polyline
from src.domains.connectors.clients.google_routes_client import TravelMode
from tests.helpers.card_microsoft_reference import microsoft_reference_domains
from tests.helpers.card_native_reference import native_detail_domains


class CardReference(TypedDict):
    id: str
    language: str
    domains: dict[str, dict[str, object]]
    html: str


class ReferencePlacesOutput(ToolOutputMixin):
    tool_name = "reference_place_details"
    operation = "details"


def mcp_detail_domain() -> dict[str, dict[str, object]]:
    from src.domains.agents.data_registry.mcp_metadata import mcp_item_payload
    from src.domains.agents.data_registry.models import RegistryItemMeta, RegistryItemType

    payload = mcp_item_payload(
        {
            "name": "Received MCP item",
            "title": "Alternate received title",
            "description": "Received sentence. " * 60 + "MCP_LAST_DESCRIPTION",
            "url": "https://resource.example.test/item",
            "id": "received-id",
            "enabled": False,
            "count": 0,
            "accessToken": "SECRET_NOT_DISPLAYED",
            "nested": {"last_fact": "MCP_LAST_NESTED", "api_key": "SECRET_NOT_DISPLAYED"},
            **{f"field_{i}": f"Received field {i}" for i in range(9)},
        },
        "Actual MCP server",
        "list_items",
    )
    item = RegistryItem(
        id="mcp_reference_details",
        type=RegistryItemType.MCP_RESULT,
        payload=payload,
        meta=RegistryItemMeta(source="mcp_reference", domain="mcp", tool_name="list_items"),
    )
    return {
        "mcps": {"mcps": [card_payload(RegistryItem.model_validate_json(item.model_dump_json()))]}
    }


def research_detail_domains() -> dict[str, dict[str, object]]:
    from src.domains.agents.data_registry.models import RegistryItemMeta, RegistryItemType
    from src.domains.agents.tools.brave_tools import _brave_news_tool_impl
    from src.domains.agents.tools.perplexity_tools import _perplexity_ask_tool_impl

    citations = [f"https://source{i}.example.test/received-article-{i}" for i in range(9)]
    answer = _perplexity_ask_tool_impl.format_registry_response(
        {
            "success": True,
            "data": {
                "question": "RECEIVED_QUESTION",
                "answer": "A received fact [9].\n\n" + "Sentence. " * 100 + "RESEARCH_LAST_FACT",
                "citations": citations,
            },
        }
    )
    news = _brave_news_tool_impl.format_registry_response(
        {
            "success": True,
            "data": {
                "query": "Research",
                "endpoint": "news",
                "results": [
                    {
                        "title": "Received news",
                        "url": "https://news.example.test/article",
                        "description": "First sentence. " * 30 + "LAST_NEWS_FACT",
                        "age": "2 hours ago",
                    }
                ],
            },
        }
    )
    article = RegistryItem(
        id="wikipedia_reference",
        type=RegistryItemType.WIKIPEDIA_ARTICLE,
        payload={
            "title": "Received article",
            "url": "https://fr.wikipedia.org/wiki/Article",
            "content": "Article paragraph. " * 100 + "\n\nLAST_ARTICLE_FACT",
            "language": "fr",
            "page_id": 0,
            "sections": [{"title": "Last supplied section", "level": 2, "index": "1"}],
            "categories": [f"Category {i}" for i in range(7)],
        },
        meta=RegistryItemMeta(
            source="wikipedia", domain="wikipedia", tool_name="get_wikipedia_article"
        ),
    )
    unified = {
        "query": "Research",
        "sources_used": ["brave", "wikipedia", "perplexity"],
        "synthesis": "Combined fact [9].",
        "citations": citations,
        "related_questions": [f"Related question {i}" for i in range(7)],
        "results": [
            {
                "title": f"Result {i}",
                "url": f"https://result{i}.example.test",
                "snippet": "Description. " * 30 + f" LAST_UNIFIED_FACT_{i}",
                "source": "brave",
            }
            for i in range(8)
        ],
    }

    def archived(items: list[RegistryItem]) -> list[dict[str, object]]:
        return [
            card_payload(RegistryItem.model_validate_json(item.model_dump_json())) for item in items
        ]

    return {
        "wikipedia": {"articles": archived([article])},
        "perplexity": {"results": archived(list(answer.registry_updates.values()))},
        "braves": {"results": archived(list(news.registry_updates.values()))},
        "web_search": {"results": [unified]},
    }


def weather_detail_domain() -> dict[str, dict[str, object]]:
    from datetime import UTC, datetime

    raw = {
        "city": {"name": "Lyon", "country": "FR"},
        "list": [
            {
                "dt": int(datetime(2026, 10, 3, hour, tzinfo=UTC).timestamp()),
                "main": {"temp": 0, "feels_like": -2.5, "humidity": 0, "pressure": 1008},
                "weather": [{"description": "clear sky", "icon": "01d"}],
                "wind": {"speed": 0, "deg": 0, "gust": 2.4},
                "visibility": 0,
                "clouds": {"all": 0},
                "pop": 0,
                "rain": {"3h": 0},
                "snow": {"3h": 1.5},
            }
            for hour in (18, 21, 0)
        ],
    }
    result = _format_hourly_response(raw, "Lyon", "FR", 3, "metric", user_timezone="Europe/Paris")
    result["data"]["date"] = "2026-10-03"
    output = _get_hourly_forecast_tool_impl.format_registry_response(result)
    payloads = [
        card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
        for item in output.registry_updates.values()
    ]
    return {"weathers": {"weathers": payloads}}


def route_detail_domain(language: str) -> dict[str, dict[str, object]]:
    walking = {
        "travelMode": "WALK",
        "distanceMeters": 350,
        "staticDuration": "240s",
        "navigationInstruction": {
            "instructions": "Rejoignez la station Bellecour",
            "maneuver": "TURN_LEFT",
        },
    }
    transit = {
        "travelMode": "TRANSIT",
        "distanceMeters": 4500,
        "staticDuration": "420s",
        "transitDetails": {
            "transitLine": {
                "nameShort": "M D",
                "color": "#00AA55",
                "vehicle": {"type": "SUBWAY", "name": {"text": "Métro"}},
            },
            "headsign": "Gare de Vaise",
            "stopDetails": {
                "departureStop": {"name": "Bellecour"},
                "arrivalStop": {"name": "Gare de Vaise"},
            },
            "stopCount": 5,
        },
    }
    source = {
        "routes": [
            {
                "duration": "780s",
                "distanceMeters": 4850,
                "polyline": {
                    "encodedPolyline": encode_polyline([(45.7578, 4.8320), (45.7804, 4.8043)])
                },
                "legs": [
                    {"duration": "240s", "distanceMeters": 350, "steps": [walking]},
                    {"duration": "540s", "distanceMeters": 4500, "steps": [transit]},
                ],
            },
            {
                "duration": "1200s",
                "distanceMeters": 5200,
                "legs": [
                    {
                        "duration": "1200s",
                        "distanceMeters": 5200,
                        "steps": [
                            {
                                "navigationInstruction": {"instructions": "OTHER_RECEIVED_JOURNEY"},
                                "distanceMeters": 5200,
                            }
                        ],
                    }
                ],
            },
        ]
    }
    formatted = _format_route_response(
        source,
        "Place Bellecour",
        "Gare de Vaise",
        TravelMode.TRANSIT,
        language,
        "Europe/Paris",
        departure_time="2026-10-05T07:30:00Z",
    )
    _, item = _create_route_registry_item(
        formatted, "Place Bellecour", "Gare de Vaise", TravelMode.TRANSIT
    )
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    return {"routes": {"routes": [card_payload(restored)]}}


def place_detail_domain(language: str) -> dict[str, dict[str, object]]:
    source = {
        "id": "reference-place",
        "displayName": {"text": "Le Jardin des Saveurs"},
        "formattedAddress": "12 rue du Jardin, Lyon",
        "rating": 4.5,
        "userRatingCount": 128,
        "timeZone": {"id": "Europe/Paris"},
        "utcOffsetMinutes": 120,
        "currentOpeningHours": {
            "openNow": False,
            "nextOpenTime": "2026-10-05T07:30:00Z",
            "weekdayDescriptions": ["Dimanche: fermé", "Lundi: 09:30–18:00"],
            "specialDays": [{"date": {"year": 2026, "month": 12, "day": 25}}],
        },
        "regularOpeningHours": {
            "weekdayDescriptions": ["Lundi: 09:00–18:00", "Dimanche: 09:00–14:00"]
        },
        "delivery": False,
        "takeout": True,
        "accessibilityOptions": {
            "wheelchairAccessibleEntrance": False,
            "wheelchairAccessibleSeating": True,
        },
        "parkingOptions": {"freeParkingLot": True, "valetParking": False},
        "paymentOptions": {"acceptsDebitCards": True, "acceptsCashOnly": False},
        "reviews": [
            {
                "rating": 4.5,
                "text": {"text": "Un accueil chaleureux.\nLa terrasse est très agréable."},
                "originalText": {"text": "A warm welcome.\nThe terrace is very pleasant."},
                "publishTime": "2026-10-01T12:00:00Z",
                "visitDate": {"year": 2026, "month": 9, "day": 0},
                "googleMapsUri": "https://example.test/review",
                "flagContentUri": "https://example.test/report",
                "authorAttribution": {
                    "displayName": "Camille",
                    "uri": "https://example.test/author",
                    "photoUri": "/api/v1/connectors/google-places/photo/places/demo/photos/avatar",
                },
            }
        ],
    }
    output = ReferencePlacesOutput().build_places_output(
        [format_place_details(source, language=language)]
    )
    item = next(iter(output.registry_updates.values()))
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    data = card_payload(restored)
    if data is None:
        raise ValueError("Reference place payload is missing")
    return {"places": {"places": [data]}}


REFERENCE_DOMAINS: dict[str, dict[str, object]] = {
    "emails": {
        "emails": [
            {
                "subject": "Votre voyage à Lyon est confirmé",
                "from": "Camille Martin <camille@example.test>",
                "to": ["Alex <alex@example.test>"],
                "date": "2025-03-18T09:30:00Z",
                "labelIds": ["UNREAD", "IMPORTANT"],
                "snippet": "Retrouvez les informations utiles pour votre arrivée et votre réservation.",
                "body": "Bonjour Alex,\nVotre réservation est confirmée.\nArrivée à partir de 15 h.\nBonne journée,\nCamille",
                "attachments": [
                    {"filename": "Confirmation.pdf", "mimeType": "application/pdf", "size": 24576}
                ],
            }
        ],
    },
    "places": {
        "places": [
            {
                "name": "Le Jardin des Saveurs",
                "address": "18 rue des Tables Claudiennes, Lyon",
                "rating": 4.7,
                "userRatingCount": 128,
                "phone_international": "+33 4 00 00 00 00",
                "website": "https://restaurant.example.test",
                "open_now": True,
                "types": ["restaurant"],
                "editorial_summary": "Une cuisine de saison dans un jardin calme au cœur de la ville.",
                "reviews": [
                    {
                        "author_name": "Marie",
                        "rating": 5,
                        "relative_time": "Il y a une semaine",
                        "text": "Une belle adresse, accessible et accueillante. Les produits de saison sont excellents.",
                    }
                ],
            }
        ],
    },
    "routes": {
        "routes": [
            {
                "origin": "Gare de Lyon Part-Dieu",
                "destination": "Le Jardin des Saveurs",
                "travel_mode": "WALK",
                "distance_km": 2.8,
                "duration_minutes": 35,
                "duration_formatted": "35 min",
                "steps": [
                    {
                        "instruction": "Rejoignez le cours Lafayette",
                        "distance": "450 m",
                        "duration": "6 min",
                    },
                    {
                        "instruction": "Traversez le Rhône par le pont Morand",
                        "distance": "1.1 km",
                        "duration": "14 min",
                    },
                ],
            }
        ],
    },
    "weathers": {
        "weather": [
            {
                "type": "current",
                "location": "Lyon",
                "description": "Ciel dégagé",
                "temperature": "18°C",
                "feels_like": "17°C",
                "humidity": "62%",
                "wind_speed": "8 km/h",
                "uv_index": 3,
                "visibility": "10 km",
                "clouds": 0,
            }
        ],
    },
}

DETAIL_REFERENCE_DOMAINS: dict[str, dict[str, object]] = {
    "tasks": {
        "tasks": [
            {
                "title": "Préparer le séjour",
                "notes": "Prévoir les documents utiles.\n" * 8
                + "Dernière note : billets et confirmation.",
                "subtasks": [
                    {"title": f"Étape {i + 1}", "status": "completed" if i < 6 else "needsAction"}
                    for i in range(13)
                ],
            }
        ]
    },
    "contacts": {
        "contacts": [
            {
                "displayName": "Camille Martin",
                "names": [{"displayName": "Camille Martin"}, {"displayName": "Camille Dupont"}],
                "organizations": [
                    {"name": "Atelier du Nord", "title": "Ingénieure", "department": "Robotique"},
                    {
                        "name": "Laboratoire du Sud",
                        "title": "Conseillère",
                        "department": "Accessibilité",
                    },
                ],
                "emailAddresses": [
                    {"value": f"camille{i}@example.test", "type": "work"} for i in range(5)
                ],
                "phoneNumbers": [{"value": f"+3340000000{i}", "type": "work"} for i in range(4)],
                "biographies": [
                    {
                        "value": "Accueil et réservations.\n" * 8
                        + "Contact disponible pour toute question sur votre arrivée."
                    }
                ],
            }
        ]
    },
    "events": {
        "events": [
            {
                "summary": "Accueil à Lyon",
                "start": {"dateTime": "2025-03-20T14:00:00+01:00"},
                "end": {"dateTime": "2025-03-20T15:00:00+01:00"},
                "description": "Présentation du programme. " * 15
                + "Dernier point : accès au jardin.",
                "attendees": [
                    {"email": f"participant{i}@example.test", "responseStatus": "accepted"}
                    for i in range(14)
                ],
            }
        ]
    },
    "files": {
        "files": [
            {
                "name": "Informations pratiques.txt",
                "owners": [{"displayName": "Camille"}, {"displayName": "Robin"}],
                "permissions": [
                    {"type": "anyone", "role": "reader"},
                    {
                        "type": "group",
                        "displayName": "Équipe design",
                        "emailAddress": "design@example.test",
                        "role": "writer",
                    },
                ],
                "version": "0",
                "size": 0,
                "shared": True,
                "starred": False,
                "trashed": False,
                "mimeType": "text/plain",
                "description": "Informations pour votre visite. " * 8
                + "Description complète disponible.",
                "content": "Transport, accès et horaires.\n" * 12
                + "Dernière ligne : rendez-vous à l'accueil.",
            }
        ]
    },
    "calendars": {
        "calendars": [
            {
                "summary": "Voyage à Lyon",
                "description": "Les rendez-vous du séjour.",
                "timeZone": "Europe/Paris",
                "accessRole": "reader",
            }
        ]
    },
}


SNAPSHOT_REFERENCE_DOMAINS: dict[str, dict[str, object]] = {
    "hues": {"hues": [{"name": "Lampe du bureau", "is_on": True, "brightness": 0}]},
    "tickets": {
        "tickets": [
            {
                "title": "Préparer la visite",
                "status": "waiting",
                "priority": "urgent",
                "assignee_kind": "lia",
                "due_at": "2026-10-05T18:00:00Z",
            }
        ]
    },
}

GALLERY_REFERENCE: dict[str, dict[str, object]] = {
    "places": {
        "places": [
            {
                "name": "Le Jardin des Saveurs",
                "address": "12 rue du Jardin, Lyon",
                "photo_gallery": [
                    {
                        "url": f"/api/v1/connectors/google-places/photo/places/demo/photos/photo{i}?max_width_px=800",
                        "authors": [
                            {
                                "name": f"Photographe {i + 1}",
                                "url": f"https://example.test/author{i}",
                            }
                        ],
                        "source_url": f"https://example.test/photo{i}",
                    }
                    for i in range(3)
                ],
            }
        ],
    },
}


def card_references() -> list[CardReference]:
    renderer = HtmlRenderer()
    cases: list[CardReference] = []
    for language in ("fr", "en", "de", "es", "it", "zh-CN"):
        config = DisplayConfig(language=language, timezone="Europe/Paris")
        mcp = mcp_detail_domain()
        cases.append(
            {
                "id": "mcp_details",
                "language": language,
                "domains": mcp,
                "html": renderer.render_multi(mcp, config),
            }
        )
        research = research_detail_domains()
        cases.append(
            {
                "id": "research_details",
                "language": language,
                "domains": research,
                "html": renderer.render_multi(research, config),
            }
        )
        weather_details = weather_detail_domain()
        cases.append(
            {
                "id": "weather_details",
                "language": language,
                "domains": weather_details,
                "html": renderer.render_multi(weather_details, config),
            }
        )
        route_details = route_detail_domain(language)
        cases.append(
            {
                "id": "route_details",
                "language": language,
                "domains": route_details,
                "html": renderer.render_multi(route_details, config),
            }
        )
        place_details = place_detail_domain(language)
        cases.append(
            {
                "id": "place_details",
                "language": language,
                "domains": place_details,
                "html": renderer.render_multi(place_details, config),
            }
        )
        cases.append(
            {
                "id": "gallery",
                "language": language,
                "domains": GALLERY_REFERENCE,
                "html": renderer.render_multi(GALLERY_REFERENCE, config),
            }
        )
        for domain, data in {
            **REFERENCE_DOMAINS,
            **DETAIL_REFERENCE_DOMAINS,
            **SNAPSHOT_REFERENCE_DOMAINS,
        }.items():
            cases.append(
                {
                    "id": domain,
                    "language": language,
                    "domains": {domain: data},
                    "html": renderer.render(domain, data, config),
                }
            )
        cases.append(
            {
                "id": "snapshots",
                "language": language,
                "domains": SNAPSHOT_REFERENCE_DOMAINS,
                "html": renderer.render_multi(SNAPSHOT_REFERENCE_DOMAINS, config),
            }
        )
        cases.append(
            {
                "id": "details",
                "language": language,
                "domains": DETAIL_REFERENCE_DOMAINS,
                "html": renderer.render_multi(DETAIL_REFERENCE_DOMAINS, config),
            }
        )
        native = native_detail_domains(language)
        cases.append(
            {
                "id": "native_details",
                "language": language,
                "domains": native,
                "html": renderer.render_multi(native, config),
            }
        )
        microsoft = microsoft_reference_domains(language)
        cases.append(
            {
                "id": "microsoft",
                "language": language,
                "domains": microsoft,
                "html": renderer.render_multi(microsoft, config),
            }
        )
        cases.append(
            {
                "id": "mixed",
                "language": language,
                "domains": REFERENCE_DOMAINS,
                "html": renderer.render_multi(REFERENCE_DOMAINS, config),
            }
        )
    return cases
