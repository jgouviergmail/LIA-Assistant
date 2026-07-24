"""Unit tests for AppleContactsClient (CardDAV provider for the ``contacts`` category).

The module shipped with zero test coverage while serving the same
``ContactsClientProtocol`` as ``GooglePeopleClient`` and
``MicrosoftContactsClient``. Provider asymmetry is a documented recurring bug
source in this codebase, so these tests pin three families of behaviour:

1. **Pure CardDAV/XML parsing** — discovery, href extraction, multiget parsing
   and the local search predicate (iCloud server-side search is unreliable, so
   filtering happens here).
2. **Cache freshness truthfulness** — ``from_cache``/``cached_at`` must describe
   the CACHE WRITE time the way ``GooglePeopleClient``/``GoogleGmailClient`` do,
   because ``calculate_cache_age_seconds`` derives the age surfaced to the LLM
   from that field.
3. **HTTP failure handling** — a non-success iCloud response must never be fed
   to the vCard parser: ``normalize_vcard`` degrades an unparsable body into a
   contact named "Unknown", and ``merge_vcard_fields`` rebuilds a MINIMAL card,
   which an update would then PUT back over the real contact.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.apple_contacts_client import (
    AppleContactsClient,
    _contact_matches_query,
    _extract_addressbook_home_set,
    _extract_addressbook_url,
    _extract_contact_hrefs,
    _extract_principal_url,
    _parse_multiget_response,
)
from src.domains.connectors.clients.base_apple_client import AppleAuthenticationError
from src.domains.connectors.schemas import AppleCredentials

pytestmark = pytest.mark.unit


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials() -> AppleCredentials:
    """Apple credentials (Apple ID + app-specific password)."""
    return AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl-mnop")


@pytest.fixture
def client(credentials: AppleCredentials) -> AppleContactsClient:
    """Client with discovery short-circuited to a known addressbook URL."""
    instance = AppleContactsClient(
        user_id=uuid4(),
        credentials=credentials,
        connector_service=MagicMock(),
    )
    instance._addressbook_url = "https://contacts.icloud.com/1234/carddavhome/card/"
    return instance


def _response(status_code: int, text: str = "") -> MagicMock:
    """Minimal httpx.Response stand-in (only the attributes the client reads)."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def _fake_redis() -> AsyncMock:
    """Redis stand-in backed by an in-memory dict, honouring get/set/delete."""
    store: dict[str, str] = {}
    redis = AsyncMock()

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    async def _delete(key: str) -> None:
        store.pop(key, None)

    redis.get = AsyncMock(side_effect=_get)
    redis.set = AsyncMock(side_effect=_set)
    redis.delete = AsyncMock(side_effect=_delete)
    redis._store = store
    return redis


VCARD_JANE = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "FN:Jane Doe\r\n"
    "N:Doe;Jane;;;\r\n"
    "EMAIL;TYPE=WORK:jane.doe@example.com\r\n"
    "TEL;TYPE=CELL:+33612345678\r\n"
    "ORG:ACME Corp\r\n"
    "END:VCARD\r\n"
)


# ============================================================================
# PURE PARSING — DISCOVERY (RFC 6352 three-step PROPFIND dance)
# ============================================================================


class TestExtractPrincipalUrl:
    """``_extract_principal_url`` reads DAV:current-user-principal/DAV:href."""

    def test_returns_href_regardless_of_namespace_prefix(self) -> None:
        xml = """<?xml version="1.0"?>
        <x:multistatus xmlns:x="DAV:">
          <x:response><x:propstat><x:prop>
            <x:current-user-principal><x:href>/1234/principal/</x:href></x:current-user-principal>
          </x:prop></x:propstat></x:response>
        </x:multistatus>"""
        assert _extract_principal_url(xml) == "/1234/principal/"

    def test_missing_element_returns_none(self) -> None:
        assert (
            _extract_principal_url('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"/>') is None
        )

    def test_malformed_xml_returns_none_instead_of_raising(self) -> None:
        assert _extract_principal_url("<not-xml") is None

    def test_external_entity_is_not_resolved(self, tmp_path) -> None:
        """XXE guard: the parser must not read local files referenced by a DTD."""
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET", encoding="utf-8")
        xml = f"""<?xml version="1.0"?>
        <!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///{secret.as_posix()}">]>
        <d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop>
          <d:current-user-principal><d:href>&xxe;</d:href></d:current-user-principal>
        </d:prop></d:propstat></d:response></d:multistatus>"""

        assert _extract_principal_url(xml) != "TOP-SECRET"


class TestExtractAddressbookHomeSet:
    """``_extract_addressbook_home_set`` reads carddav:addressbook-home-set/DAV:href."""

    def test_returns_home_set_href(self) -> None:
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response><d:propstat><d:prop>
            <card:addressbook-home-set><d:href>/1234/carddavhome/</d:href></card:addressbook-home-set>
          </d:prop></d:propstat></d:response>
        </d:multistatus>"""
        assert _extract_addressbook_home_set(xml) == "/1234/carddavhome/"

    def test_empty_href_text_returns_none(self) -> None:
        """An empty href must degrade to None so the caller applies its fallback."""
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response><d:propstat><d:prop>
            <card:addressbook-home-set><d:href></d:href></card:addressbook-home-set>
          </d:prop></d:propstat></d:response>
        </d:multistatus>"""
        assert _extract_addressbook_home_set(xml) is None


class TestExtractAddressbookUrl:
    """``_extract_addressbook_url`` prefers a real addressbook resourcetype."""

    HOME_SET = "https://contacts.icloud.com/1234/carddavhome/"

    def test_prefers_collection_with_addressbook_resourcetype(self) -> None:
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response>
            <d:href>/1234/carddavhome/</d:href>
            <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
          </d:response>
          <d:response>
            <d:href>/1234/carddavhome/card/</d:href>
            <d:propstat><d:prop><d:resourcetype>
              <d:collection/><card:addressbook/>
            </d:resourcetype></d:prop></d:propstat>
          </d:response>
        </d:multistatus>"""
        result = _extract_addressbook_url(xml, self.HOME_SET)
        assert result is not None
        assert result.endswith("/1234/carddavhome/card/")
        assert result.startswith("http")

    def test_absolute_href_is_returned_unchanged(self) -> None:
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response>
            <d:href>https://p99-contacts.icloud.com/1234/carddavhome/card/</d:href>
            <d:propstat><d:prop><d:resourcetype><card:addressbook/></d:resourcetype></d:prop></d:propstat>
          </d:response>
        </d:multistatus>"""
        assert (
            _extract_addressbook_url(xml, self.HOME_SET)
            == "https://p99-contacts.icloud.com/1234/carddavhome/card/"
        )

    def test_fallback_skips_the_home_set_itself(self) -> None:
        """Without a typed addressbook, the fallback must return a CHILD collection."""
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response><d:href>/1234/carddavhome/</d:href></d:response>
          <d:response><d:href>/1234/carddavhome/card/</d:href></d:response>
        </d:multistatus>"""
        result = _extract_addressbook_url(xml, self.HOME_SET)
        assert result is not None
        assert result.endswith("/1234/carddavhome/card/")

    def test_no_candidate_returns_none(self) -> None:
        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"/>'
        assert _extract_addressbook_url(xml, self.HOME_SET) is None


class TestExtractContactHrefs:
    """``_extract_contact_hrefs`` keeps only ``.vcf`` resources."""

    def test_keeps_only_vcf_resources(self) -> None:
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response><d:href>/1234/carddavhome/card/</d:href></d:response>
          <d:response><d:href>/1234/carddavhome/card/aaa.vcf</d:href></d:response>
          <d:response><d:href>/1234/carddavhome/card/bbb.vcf</d:href></d:response>
        </d:multistatus>"""
        assert _extract_contact_hrefs(xml) == [
            "/1234/carddavhome/card/aaa.vcf",
            "/1234/carddavhome/card/bbb.vcf",
        ]

    def test_malformed_xml_returns_empty_list(self) -> None:
        assert _extract_contact_hrefs("<broken") == []


class TestParseMultigetResponse:
    """``_parse_multiget_response`` normalises vCards and attaches the etag."""

    def test_normalises_contacts_and_strips_etag_quotes(self) -> None:
        xml = f"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response>
            <d:href>/1234/carddavhome/card/jane.vcf</d:href>
            <d:propstat><d:prop>
              <d:getetag>"abc123"</d:getetag>
              <card:address-data>{VCARD_JANE}</card:address-data>
            </d:prop></d:propstat>
          </d:response>
        </d:multistatus>"""
        contacts = _parse_multiget_response(xml)

        assert len(contacts) == 1
        contact = contacts[0]
        assert contact["resourceName"] == "/1234/carddavhome/card/jane.vcf"
        assert contact["names"][0]["displayName"] == "Jane Doe"
        assert contact["emailAddresses"][0]["value"] == "jane.doe@example.com"
        assert contact["etag"] == "abc123"

    def test_response_without_address_data_is_skipped(self) -> None:
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response><d:href>/1234/carddavhome/card/</d:href>
            <d:propstat><d:prop><d:getetag>"x"</d:getetag></d:prop></d:propstat>
          </d:response>
        </d:multistatus>"""
        assert _parse_multiget_response(xml) == []

    def test_one_broken_vcard_does_not_drop_the_valid_ones(self) -> None:
        """A per-contact parse failure is isolated: siblings still come back."""
        xml = f"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
          <d:response>
            <d:href>/c/broken.vcf</d:href>
            <d:propstat><d:prop><card:address-data>NOT-A-VCARD</card:address-data></d:prop></d:propstat>
          </d:response>
          <d:response>
            <d:href>/c/jane.vcf</d:href>
            <d:propstat><d:prop><card:address-data>{VCARD_JANE}</card:address-data></d:prop></d:propstat>
          </d:response>
        </d:multistatus>"""
        contacts = _parse_multiget_response(xml)

        names = [c.get("names", [{}])[0].get("displayName") for c in contacts]
        assert "Jane Doe" in names


class TestContactMatchesQuery:
    """``_contact_matches_query`` is the local substitute for server-side search."""

    CONTACT = {
        "names": [{"displayName": "Jane Doe"}],
        "emailAddresses": [{"value": "Jane.Doe@Example.com"}],
        "phoneNumbers": [{"value": "+33612345678"}],
        "organizations": [{"name": "ACME Corp"}],
    }

    @pytest.mark.parametrize(
        "query",
        ["jane", "doe", "jane.doe@example.com", "612345678", "acme"],
        ids=["first-name", "last-name", "email", "phone-fragment", "organization"],
    )
    def test_matches_every_searchable_field_case_insensitively(self, query: str) -> None:
        assert _contact_matches_query(self.CONTACT, query) is True

    def test_unrelated_query_does_not_match(self) -> None:
        assert _contact_matches_query(self.CONTACT, "zzz") is False

    def test_contact_without_any_field_does_not_raise(self) -> None:
        assert _contact_matches_query({}, "jane") is False


# ============================================================================
# DISCOVERY FLOW
# ============================================================================


class TestDiscoverAddressbook:
    """The three-step PROPFIND discovery, its fallbacks and its auth guard."""

    @staticmethod
    def _client(credentials: AppleCredentials) -> AppleContactsClient:
        return AppleContactsClient(
            user_id=uuid4(), credentials=credentials, connector_service=MagicMock()
        )

    async def test_full_three_step_discovery(self, credentials: AppleCredentials) -> None:
        instance = self._client(credentials)
        http = AsyncMock()
        http.request = AsyncMock(
            side_effect=[
                _response(
                    207,
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:propstat>'
                    "<d:prop><d:current-user-principal><d:href>/1234/principal/</d:href>"
                    "</d:current-user-principal></d:prop></d:propstat></d:response></d:multistatus>",
                ),
                _response(
                    207,
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" '
                    'xmlns:card="urn:ietf:params:xml:ns:carddav"><d:response><d:propstat><d:prop>'
                    "<card:addressbook-home-set><d:href>/1234/carddavhome/</d:href>"
                    "</card:addressbook-home-set></d:prop></d:propstat></d:response></d:multistatus>",
                ),
                _response(
                    207,
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" '
                    'xmlns:card="urn:ietf:params:xml:ns:carddav"><d:response>'
                    "<d:href>/1234/carddavhome/card/</d:href><d:propstat><d:prop><d:resourcetype>"
                    "<d:collection/><card:addressbook/></d:resourcetype></d:prop></d:propstat>"
                    "</d:response></d:multistatus>",
                ),
            ]
        )

        with patch.object(instance, "_get_http_client", AsyncMock(return_value=http)):
            url = await instance._discover_addressbook()

        assert url.endswith("/1234/carddavhome/card/")
        assert http.request.await_count == 3

    async def test_discovery_result_is_memoised(self, credentials: AppleCredentials) -> None:
        instance = self._client(credentials)
        instance._addressbook_url = "https://contacts.icloud.com/1234/carddavhome/card/"
        http = AsyncMock()

        with patch.object(instance, "_get_http_client", AsyncMock(return_value=http)):
            url = await instance._discover_addressbook()

        assert url == "https://contacts.icloud.com/1234/carddavhome/card/"
        http.request.assert_not_awaited()

    async def test_missing_principal_raises(self, credentials: AppleCredentials) -> None:
        instance = self._client(credentials)
        http = AsyncMock()
        http.request = AsyncMock(return_value=_response(207, "<d:multistatus xmlns:d='DAV:'/>"))

        with (
            patch.object(instance, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(ValueError, match="principal"),
        ):
            await instance._discover_addressbook()

    async def test_http_401_raises_apple_authentication_error(
        self, credentials: AppleCredentials
    ) -> None:
        instance = self._client(credentials)
        http = AsyncMock()
        http.request = AsyncMock(return_value=_response(401, ""))

        with (
            patch.object(instance, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(AppleAuthenticationError),
        ):
            await instance._discover_addressbook()


# ============================================================================
# CACHE FRESHNESS CONTRACT (parity with GooglePeopleClient / GoogleGmailClient)
# ============================================================================


class TestContactsCacheFreshness:
    """``cached_at`` must describe the cache WRITE time, never "now"."""

    async def test_cache_miss_populates_cache_and_reports_no_cache(
        self, client: AppleContactsClient
    ) -> None:
        redis = _fake_redis()
        http = AsyncMock()
        http.request = AsyncMock(
            side_effect=[
                _response(
                    207,
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response>'
                    "<d:href>/c/jane.vcf</d:href></d:response></d:multistatus>",
                ),
                _response(
                    207,
                    f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" '
                    f'xmlns:card="urn:ietf:params:xml:ns:carddav"><d:response>'
                    f"<d:href>/c/jane.vcf</d:href><d:propstat><d:prop>"
                    f"<card:address-data>{VCARD_JANE}</card:address-data>"
                    f"</d:prop></d:propstat></d:response></d:multistatus>",
                ),
            ]
        )

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch(
                "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
                AsyncMock(return_value=redis),
            ),
        ):
            contacts, from_cache, cached_at = await client._get_all_contacts_cached(use_cache=True)

        assert from_cache is False
        assert cached_at is None
        assert [c["names"][0]["displayName"] for c in contacts] == ["Jane Doe"]
        assert redis.set.await_count == 1

    async def test_cache_hit_returns_the_write_timestamp_not_now(
        self, client: AppleContactsClient
    ) -> None:
        """Regression: reporting ``now`` made every cached payload look brand new."""
        redis = _fake_redis()
        written_at = "2020-01-01T00:00:00+00:00"
        redis._store[f"apple_contacts:{client.user_id}:all"] = json.dumps(
            {"contacts": [{"names": [{"displayName": "Jane Doe"}]}], "cached_at": written_at}
        )
        http = AsyncMock()

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch(
                "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
                AsyncMock(return_value=redis),
            ),
        ):
            contacts, from_cache, cached_at = await client._get_all_contacts_cached(use_cache=True)

        assert from_cache is True
        assert cached_at == written_at
        assert contacts[0]["names"][0]["displayName"] == "Jane Doe"
        http.request.assert_not_awaited()

    async def test_legacy_bare_list_cache_entry_is_still_readable(
        self, client: AppleContactsClient
    ) -> None:
        """Entries written before the envelope change must not break a running instance."""
        redis = _fake_redis()
        redis._store[f"apple_contacts:{client.user_id}:all"] = json.dumps(
            [{"names": [{"displayName": "Legacy Contact"}]}]
        )

        with patch(
            "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
            AsyncMock(return_value=redis),
        ):
            contacts, from_cache, cached_at = await client._get_all_contacts_cached(use_cache=True)

        assert from_cache is True
        assert cached_at is None
        assert contacts[0]["names"][0]["displayName"] == "Legacy Contact"

    async def test_search_propagates_the_real_cached_at(self, client: AppleContactsClient) -> None:
        written_at = "2020-01-01T00:00:00+00:00"
        with patch.object(
            client,
            "_get_all_contacts_cached",
            AsyncMock(return_value=([{"names": [{"displayName": "Jane Doe"}]}], True, written_at)),
        ):
            result = await client._search_contacts_impl("jane", 10, True, None)

        assert result["from_cache"] is True
        assert result["cached_at"] == written_at

    async def test_list_connections_propagates_the_real_cached_at(
        self, client: AppleContactsClient
    ) -> None:
        written_at = "2020-01-01T00:00:00+00:00"
        with patch.object(
            client,
            "_get_all_contacts_cached",
            AsyncMock(return_value=([{"names": [{"displayName": "Jane Doe"}]}], True, written_at)),
        ):
            result = await client._list_connections_impl(100, None, True, None)

        assert result["from_cache"] is True
        assert result["cached_at"] == written_at


# ============================================================================
# SEARCH / LIST SEMANTICS
# ============================================================================


class TestSearchAndList:
    """Local filtering, volumetry cap and token pagination."""

    CONTACTS = [
        {"names": [{"displayName": "Jane Doe"}]},
        {"names": [{"displayName": "John Smith"}]},
        {"names": [{"displayName": "Janet Roe"}]},
    ]

    async def test_search_wraps_matches_in_person_envelope(
        self, client: AppleContactsClient
    ) -> None:
        """Tools read ``results[i]["person"]`` — the Google People API shape."""
        with patch.object(
            client, "_get_all_contacts_cached", AsyncMock(return_value=(self.CONTACTS, False, None))
        ):
            result = await client._search_contacts_impl("jan", 10, True, None)

        assert result["totalItems"] == 2
        assert [r["person"]["names"][0]["displayName"] for r in result["results"]] == [
            "Jane Doe",
            "Janet Roe",
        ]

    async def test_search_stops_at_max_results(self, client: AppleContactsClient) -> None:
        with patch.object(
            client, "_get_all_contacts_cached", AsyncMock(return_value=(self.CONTACTS, False, None))
        ):
            result = await client._search_contacts_impl("jan", 1, True, None)

        assert result["totalItems"] == 1

    async def test_search_applies_the_global_volumetry_cap(
        self, client: AppleContactsClient
    ) -> None:
        """``apply_max_items_limit`` is the single ceiling shared by all providers."""
        from src.domains.connectors.clients.base_google_client import apply_max_items_limit

        cap = apply_max_items_limit(10_000)
        many = [{"names": [{"displayName": f"Jane {i}"}]} for i in range(cap + 5)]

        with patch.object(
            client, "_get_all_contacts_cached", AsyncMock(return_value=(many, False, None))
        ):
            result = await client._search_contacts_impl("jane", 10_000, True, None)

        assert result["totalItems"] == cap

    async def test_list_connections_paginates_with_offset_tokens(
        self, client: AppleContactsClient
    ) -> None:
        with patch.object(
            client, "_get_all_contacts_cached", AsyncMock(return_value=(self.CONTACTS, False, None))
        ):
            first = await client._list_connections_impl(2, None, True, None)
            second = await client._list_connections_impl(2, first["nextPageToken"], True, None)

        assert len(first["connections"]) == 2
        assert first["nextPageToken"] == "2"
        assert first["totalItems"] == 3
        assert len(second["connections"]) == 1
        assert second["nextPageToken"] is None

    async def test_list_connections_ignores_a_non_numeric_page_token(
        self, client: AppleContactsClient
    ) -> None:
        with patch.object(
            client, "_get_all_contacts_cached", AsyncMock(return_value=(self.CONTACTS, False, None))
        ):
            result = await client._list_connections_impl(2, "not-a-number", True, None)

        assert len(result["connections"]) == 2


# ============================================================================
# HTTP FAILURE HANDLING — never parse an error body as a vCard
# ============================================================================


class TestHttpFailureHandling:
    """A non-success iCloud response must surface as an error, not as data."""

    async def test_get_person_returns_the_normalised_contact(
        self, client: AppleContactsClient
    ) -> None:
        http = AsyncMock()
        http.get = AsyncMock(return_value=_response(200, VCARD_JANE))

        with patch.object(client, "_get_http_client", AsyncMock(return_value=http)):
            person = await client._get_person_impl("/c/jane.vcf", None, True)

        assert person["names"][0]["displayName"] == "Jane Doe"
        assert person["from_cache"] is False
        assert person["cached_at"] is None

    async def test_get_person_404_raises_value_error(self, client: AppleContactsClient) -> None:
        http = AsyncMock()
        http.get = AsyncMock(return_value=_response(404, "Not Found"))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(ValueError, match="not found"),
        ):
            await client._get_person_impl("/c/ghost.vcf", None, True)

    async def test_get_person_500_raises_instead_of_returning_unknown(
        self, client: AppleContactsClient
    ) -> None:
        """Regression: ``normalize_vcard`` turns an error page into a contact "Unknown"."""
        http = AsyncMock()
        http.get = AsyncMock(return_value=_response(500, "<html>iCloud is down</html>"))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(ConnectorAPIError),
        ):
            await client._get_person_impl("/c/jane.vcf", None, True)

    async def test_update_contact_500_on_read_never_writes_back(
        self, client: AppleContactsClient
    ) -> None:
        """Regression: merging an unparsable body rebuilds a MINIMAL card, and the
        follow-up PUT would overwrite every field of the real contact."""
        http = AsyncMock()
        http.get = AsyncMock(return_value=_response(503, "<html>Service Unavailable</html>"))
        http.put = AsyncMock(return_value=_response(204))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(ConnectorAPIError),
        ):
            await client._update_contact_impl(
                "/c/jane.vcf", None, "new@example.com", None, None, None, None
            )

        http.put.assert_not_awaited()

    async def test_update_contact_merges_and_invalidates_cache(
        self, client: AppleContactsClient
    ) -> None:
        redis = _fake_redis()
        redis._store[f"apple_contacts:{client.user_id}:all"] = "[]"
        http = AsyncMock()
        http.get = AsyncMock(return_value=_response(200, VCARD_JANE))
        http.put = AsyncMock(return_value=_response(204))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch(
                "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
                AsyncMock(return_value=redis),
            ),
        ):
            result = await client._update_contact_impl(
                "/c/jane.vcf", None, "new@example.com", None, None, None, None
            )

        put_body = http.put.await_args.kwargs["content"]
        assert "new@example.com" in put_body
        assert "Jane Doe" in put_body, "untouched fields must survive the merge"
        assert result["emailAddresses"][0]["value"] == "new@example.com"
        assert f"apple_contacts:{client.user_id}:all" not in redis._store

    async def test_create_contact_rejects_unexpected_status(
        self, client: AppleContactsClient
    ) -> None:
        http = AsyncMock()
        http.put = AsyncMock(return_value=_response(507, "Insufficient Storage"))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises((ValueError, ConnectorAPIError)),
        ):
            await client._create_contact_impl("Jane Doe", None, None, None, None)

    async def test_create_contact_returns_resource_name(self, client: AppleContactsClient) -> None:
        redis = _fake_redis()
        http = AsyncMock()
        http.put = AsyncMock(return_value=_response(201))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch(
                "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
                AsyncMock(return_value=redis),
            ),
        ):
            result = await client._create_contact_impl(
                "Jane Doe", "jane@example.com", None, None, None
            )

        assert result["resourceName"].endswith(".vcf")
        assert result["names"][0]["displayName"] == "Jane Doe"

    async def test_delete_contact_500_raises_instead_of_returning_false(
        self, client: AppleContactsClient
    ) -> None:
        """A silent ``False`` is indistinguishable from "the row was already gone"."""
        http = AsyncMock()
        http.delete = AsyncMock(return_value=_response(500, "boom"))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            pytest.raises(ConnectorAPIError),
        ):
            await client._delete_contact_impl("/c/jane.vcf")

    async def test_delete_contact_success_invalidates_cache(
        self, client: AppleContactsClient
    ) -> None:
        redis = _fake_redis()
        redis._store[f"apple_contacts:{client.user_id}:all"] = "[]"
        http = AsyncMock()
        http.delete = AsyncMock(return_value=_response(204))

        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch(
                "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
                AsyncMock(return_value=redis),
            ),
        ):
            assert await client._delete_contact_impl("/c/jane.vcf") is True

        assert f"apple_contacts:{client.user_id}:all" not in redis._store


# ============================================================================
# CLEANUP
# ============================================================================


class TestClose:
    """``close()`` releases the httpx client and forgets the discovered URL."""

    async def test_close_releases_client_and_resets_discovery(
        self, client: AppleContactsClient
    ) -> None:
        http = AsyncMock()
        client._http_client = http

        await client.close()

        http.aclose.assert_awaited_once()
        assert client._http_client is None
        assert client._addressbook_url is None

    async def test_close_without_client_is_a_noop(self, credentials: AppleCredentials) -> None:
        instance = AppleContactsClient(
            user_id=uuid4(), credentials=credentials, connector_service=MagicMock()
        )
        await instance.close()
        assert instance._http_client is None
