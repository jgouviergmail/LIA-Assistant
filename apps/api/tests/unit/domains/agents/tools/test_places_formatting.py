"""Normalization of Google Places payloads for the LLM / registry / cards.

The 2026-08 audit found the platform pays the Enterprise + Atmosphere SKU for
~20 attribute booleans (dineIn, servesWine, allowsDogs, ...) that no layer ever
surfaced: the place card renders ``data["features"]`` but nothing produced that
key (dead branch), and ``accessibilityOptions`` / ``paymentOptions`` /
``parkingOptions`` were dropped by the details formatter. These tests pin the
producer side: paid data must reach the card.
"""

from __future__ import annotations

import pytest

from src.core.constants import PLACES_FEATURE_FIELD_TO_I18N_KEY
from src.core.i18n_v3 import _DISPLAY_PLACE_FEATURES
from src.domains.agents.tools.places_formatting import _format_place, format_place_details

pytestmark = pytest.mark.unit

_LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


def _details_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "place-1",
        "displayName": {"text": "Chez Test"},
        "formattedAddress": "1 rue du Test, 75001 Paris",
        "location": {"latitude": 48.85, "longitude": 2.35},
        "types": ["restaurant"],
        "googleMapsUri": "https://maps.google.com/?cid=1",
    }
    base.update(overrides)
    return base


class TestFeatureMappingRegistry:
    def test_every_mapped_feature_key_is_translated_in_all_languages(self) -> None:
        """Registry completeness (ADR-085 doctrine): a mapped feature with no
        i18n entry would silently render an empty badge."""
        for api_field, i18n_key in PLACES_FEATURE_FIELD_TO_I18N_KEY.items():
            labels = _DISPLAY_PLACE_FEATURES.get(i18n_key)
            assert labels, f"{api_field} maps to '{i18n_key}' which has no i18n entry"
            for lang in _LANGUAGES:
                assert labels.get(lang), f"'{i18n_key}' misses language '{lang}'"

    def test_mapping_covers_all_atmosphere_booleans_of_the_details_mask(self) -> None:
        for api_field in (
            "dineIn",
            "takeout",
            "delivery",
            "curbsidePickup",
            "reservable",
            "outdoorSeating",
            "liveMusic",
            "restroom",
            "allowsDogs",
            "goodForChildren",
            "goodForGroups",
            "goodForWatchingSports",
            "menuForChildren",
            "servesBeer",
            "servesBreakfast",
            "servesBrunch",
            "servesCocktails",
            "servesCoffee",
            "servesDessert",
            "servesDinner",
            "servesLunch",
            "servesVegetarianFood",
            "servesWine",
        ):
            assert api_field in PLACES_FEATURE_FIELD_TO_I18N_KEY, f"{api_field} not mapped"


class TestFormatPlaceStatusFields:
    def test_non_operational_business_status_is_surfaced(self) -> None:
        formatted = _format_place(
            _details_payload(businessStatus="CLOSED_PERMANENTLY"), language="fr"
        )
        assert formatted["business_status"] == "CLOSED_PERMANENTLY"

    def test_operational_status_stays_silent(self) -> None:
        """OPERATIONAL is the normal case: no key, no card badge, no LLM noise."""
        formatted = _format_place(_details_payload(businessStatus="OPERATIONAL"), language="fr")
        assert "business_status" not in formatted

    def test_primary_type_display_name_is_surfaced(self) -> None:
        formatted = _format_place(
            _details_payload(primaryTypeDisplayName={"text": "Pizzéria"}), language="fr"
        )
        assert formatted["primary_type"] == "Pizzéria"


class TestFormatPlaceDetails:
    def test_true_booleans_become_feature_keys_false_and_absent_do_not(self) -> None:
        details = format_place_details(
            _details_payload(
                dineIn=True,
                servesVegetarianFood=True,
                takeout=False,
            ),
            language="fr",
        )
        assert details["features"] == ["dine_in", "serves_vegetarian_food"]

    def test_no_true_boolean_means_no_features_key(self) -> None:
        details = format_place_details(_details_payload(takeout=False), language="fr")
        assert "features" not in details

    def test_structured_option_groups_are_passed_through(self) -> None:
        details = format_place_details(
            _details_payload(
                accessibilityOptions={"wheelchairAccessibleEntrance": True},
                paymentOptions={"acceptsCreditCards": True},
                parkingOptions={"freeParkingLot": True, "valetParking": False},
            ),
            language="fr",
        )
        assert details["accessibilityOptions"] == {"wheelchairAccessibleEntrance": True}
        assert details["paymentOptions"] == {"acceptsCreditCards": True}
        assert details["parkingOptions"] == {"freeParkingLot": True, "valetParking": False}

    def test_price_range_is_normalized(self) -> None:
        details = format_place_details(
            _details_payload(
                priceRange={
                    "startPrice": {"currencyCode": "EUR", "units": "10"},
                    "endPrice": {"currencyCode": "EUR", "units": "25"},
                }
            ),
            language="fr",
        )
        assert details["price_range"] == {"start": 10, "end": 25, "currency": "EUR"}

    def test_open_ended_price_range_keeps_only_known_bound(self) -> None:
        details = format_place_details(
            _details_payload(priceRange={"startPrice": {"currencyCode": "EUR", "units": "100"}}),
            language="fr",
        )
        assert details["price_range"] == {"start": 100, "end": None, "currency": "EUR"}

    def test_status_identity_and_short_address_are_surfaced(self) -> None:
        details = format_place_details(
            _details_payload(
                businessStatus="CLOSED_TEMPORARILY",
                primaryTypeDisplayName={"text": "Ristorante"},
                shortFormattedAddress="1 rue du Test, Paris",
            ),
            language="fr",
        )
        assert details["business_status"] == "CLOSED_TEMPORARILY"
        assert details["primary_type"] == "Ristorante"
        assert details["short_address"] == "1 rue du Test, Paris"

    def test_core_fields_preserved_by_the_extraction(self) -> None:
        """The helper replaces inline logic in the details tool: the existing
        normalized keys must survive the move (regression pin)."""
        details = format_place_details(
            _details_payload(
                nationalPhoneNumber="01 23 45 67 89",
                internationalPhoneNumber="+33 1 23 45 67 89",
                websiteUri="https://chez.test",
                rating=4.5,
                userRatingCount=120,
                priceLevel="PRICE_LEVEL_MODERATE",
                regularOpeningHours={"weekdayDescriptions": ["Lundi: 09:00 – 18:00"]},
                currentOpeningHours={"openNow": True},
                editorialSummary={"text": "Un classique."},
                reviews=[
                    {
                        "rating": 5,
                        "text": {"text": "Excellent"},
                        "relativePublishTimeDescription": "il y a 2 jours",
                        "publishTime": "2026-08-19T10:00:00Z",
                    }
                ],
            ),
            language="fr",
        )
        assert details["name"] == "Chez Test"
        assert details["address"] == "1 rue du Test, 75001 Paris"
        assert details["phone"] == "01 23 45 67 89"
        assert details["phone_international"] == "+33 1 23 45 67 89"
        assert details["website"] == "https://chez.test"
        assert details["rating"] == 4.5
        assert details["rating_count"] == 120
        assert details["open_now"] is True
        assert details["opening_hours"] == ["Lundi: 09:00 – 18:00"]
        assert details["description"] == "Un classique."
        assert details["reviews"][0]["text"] == "Excellent"
