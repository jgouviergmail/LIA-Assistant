"""
Apple iCloud Contacts client (CardDAV).

Implements the same interface as GooglePeopleClient for transparent
provider switching via functional_category in ConnectorTool.

Uses httpx (async) + vobject + lxml for CardDAV protocol.
caldav library does NOT support CardDAV — this is a custom implementation
following RFC 6352.

IMPORTANT: iCloud CardDAV search is unreliable server-side.
Strategy: fetch all contacts → cache in Redis → filter locally.

Created: 2026-03-10
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.content_source import content_source_binding
from src.core.field_names import FIELD_CACHED_AT
from src.core.read_budget import source_http_hooks
from src.domains.connectors.clients.apple_carddav_xml import (
    PROPFIND_ADDRESSBOOK_HOME,
    PROPFIND_ADDRESSBOOKS,
    PROPFIND_CONTACTS_HREFS,
    PROPFIND_PRINCIPAL,
    REPORT_MULTIGET_TEMPLATE,
    extract_addressbook_home_set,
    extract_addressbook_url,
    extract_contact_hrefs,
    extract_principal_url,
    parse_multiget_response,
)
from src.domains.connectors.clients.apple_contact_groups_mixin import AppleContactGroupsMixin
from src.domains.connectors.clients.base_apple_client import BaseAppleClient
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.contact_details import ContactDetails
from src.domains.connectors.clients.contact_directory import (
    ContactDirectory,
    cached_directory,
    invalidate_contacts_cache,
)
from src.domains.connectors.clients.contact_photos import (
    ContactPhoto,
    card_photo,
    card_with_photo,
)
from src.domains.connectors.clients.normalizers.contact_order import contact_order_key
from src.domains.connectors.clients.normalizers.contact_values import TypedAddress, TypedValue
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)


class AppleContactsClient(AppleContactGroupsMixin, BaseAppleClient):
    """
    Apple iCloud Contacts client using CardDAV.

    Interface matches GooglePeopleClient for transparent provider switching.
    """

    connector_type = ConnectorType.APPLE_CONTACTS

    def __init__(
        self,
        user_id: UUID,
        credentials: AppleCredentials,
        connector_service: Any,
    ) -> None:
        super().__init__(user_id, credentials, connector_service)
        self._http_client: httpx.AsyncClient | None = None
        self._addressbook_url: str | None = None

    # =========================================================================
    # HTTP CLIENT & DISCOVERY
    # =========================================================================

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create httpx client with Basic Auth."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                event_hooks=source_http_hooks(self.user_id),
                auth=(self.credentials.apple_id, self.credentials.app_password),
                timeout=settings.apple_connection_timeout,
                follow_redirects=True,
            )
        return self._http_client

    async def _discover_addressbook(self) -> str:
        """
        Discover the CardDAV addressbook URL via PROPFIND.

        iCloud CardDAV discovery requires 3 steps:
        1. PROPFIND / → current-user-principal (e.g., /267545121/principal/)
        2. PROPFIND {principal} → addressbook-home-set (e.g., /267545121/carddavhome/card/)
        3. PROPFIND {home-set} Depth:1 → find collection with resourcetype addressbook
        """
        if self._addressbook_url is not None:
            return self._addressbook_url

        client = await self._get_http_client()

        # Step 1: Get current-user-principal
        resp = await client.request(
            "PROPFIND",
            settings.apple_carddav_url,
            content=PROPFIND_PRINCIPAL,
            headers={"Content-Type": "application/xml", "Depth": "0"},
        )
        self._check_http_status(resp.status_code)

        logger.debug(
            "carddav_step1_response",
            status=resp.status_code,
            body_preview=resp.text[:500],
        )
        principal_url = extract_principal_url(resp.text)
        if not principal_url:
            logger.error(
                "carddav_step1_failed",
                status=resp.status_code,
                body_length=len(resp.text),
            )
            raise ValueError("Could not discover CardDAV principal URL")

        if not principal_url.startswith("http"):
            principal_url = f"{settings.apple_carddav_url.rstrip('/')}{principal_url}"

        # Step 2: Get addressbook-home-set from principal
        resp = await client.request(
            "PROPFIND",
            principal_url,
            content=PROPFIND_ADDRESSBOOK_HOME,
            headers={"Content-Type": "application/xml", "Depth": "0"},
        )
        self._check_http_status(resp.status_code)

        logger.debug(
            "carddav_step2_response",
            status=resp.status_code,
            principal_url=principal_url,
            body_preview=resp.text[:500],
        )
        home_set_url = extract_addressbook_home_set(resp.text)
        if not home_set_url:
            logger.warning(
                "carddav_step2_no_home_set",
                status=resp.status_code,
                body_length=len(resp.text),
            )
            # Fallback: some servers expose addressbook directly on principal
            home_set_url = principal_url

        if not home_set_url.startswith("http"):
            home_set_url = f"{settings.apple_carddav_url.rstrip('/')}{home_set_url}"

        # Step 3: Find the actual addressbook collection
        resp = await client.request(
            "PROPFIND",
            home_set_url,
            content=PROPFIND_ADDRESSBOOKS,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_status(resp.status_code)

        logger.debug(
            "carddav_step3_response",
            status=resp.status_code,
            home_set_url=home_set_url,
            body_preview=resp.text[:500],
        )
        addressbook_url = extract_addressbook_url(resp.text, home_set_url)
        if not addressbook_url:
            logger.warning(
                "carddav_step3_no_addressbook",
                status=resp.status_code,
                body_length=len(resp.text),
            )
            # Last fallback: use the home-set URL itself as the addressbook
            addressbook_url = home_set_url

        self._addressbook_url = addressbook_url
        logger.debug(
            "apple_carddav_discovered",
            user_id=str(self.user_id),
            addressbook_url=addressbook_url,
        )
        return addressbook_url

    # =========================================================================
    # PUBLIC INTERFACE (matches GooglePeopleClient exactly)
    # =========================================================================

    async def search_contacts(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search contacts with local filtering (iCloud search is unreliable)."""
        return await self._execute_with_retry(
            "search_contacts",
            self._search_contacts_impl,
            query,
            max_results,
            use_cache,
            fields,
        )

    async def list_connections(
        self,
        page_size: int = 100,
        page_token: str | None = None,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """List all contacts."""
        return await self._execute_with_retry(
            "list_connections",
            self._list_connections_impl,
            page_size,
            page_token,
            use_cache,
            fields,
        )

    async def list_email_directory(
        self, max_contacts: int, *, cache_scope: str | None = None
    ) -> ContactDirectory:
        """The whole address book, up to ``max_contacts`` (``clients/contact_directory``).

        iCloud is read whole anyway (``_get_all_contacts_cached``); the directory
        is its compact, stamped cut, cached like the two other providers' and
        dropped by the same writes. A scoped read bypasses the iCloud book cache.

        Args:
            max_contacts: The caller's published cap.
            cache_scope: An account and snapshot identity isolating this directory in
                the shared cache from other accounts and older in-flight refreshes
                (``cached_directory``); None for the shared entry.

        Returns:
            The persons (names, addresses, numbers, birthdays), and whether the book was cut.
        """
        if cache_scope is not None:
            return await self._execute_with_retry(
                "list_email_directory", self._list_email_directory_impl, max_contacts, cache_scope
            )
        return await self._execute_with_retry(
            "list_email_directory", self._list_email_directory_impl, max_contacts
        )

    async def get_person(
        self,
        resource_name: str,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get a single contact by resource name (CardDAV URL)."""
        return await self._execute_with_retry(
            "get_person",
            self._get_person_impl,
            resource_name,
            fields,
            use_cache,
        )

    async def create_contact(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """Create a new contact.

        Its uid — the last segment of its URL — is drawn BEFORE the retry loop, so a
        resend after a lost answer writes the same contact again, never a second one (S1).
        """
        return await self._execute_with_retry(
            "create_contact",
            self._create_contact_impl,
            name,
            email,
            phone,
            organization,
            notes,
            contact_uid=str(uuid.uuid4()),
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )

    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """Update an existing contact (full PUT, no PATCH in CardDAV).

        A single e-mail, phone or address replaces the PRIMARY one and keeps the
        others; a list replaces that list; every other line of the card survives.
        """
        return await self._execute_with_retry(
            "update_contact",
            self._update_contact_impl,
            resource_name,
            name,
            email,
            phone,
            organization,
            notes,
            address,
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )

    async def get_contact_photo(self, resource_name: str) -> ContactPhoto | None:
        """The photo a contact's card holds; what it points at is never followed."""
        return await self._execute_with_retry(
            "get_contact_photo", self._get_contact_photo_impl, resource_name
        )

    async def set_contact_photo(self, resource_name: str, photo: ContactPhoto) -> None:
        """Replace a contact's photo, every other line of the card kept."""
        await self._execute_with_retry(
            "set_contact_photo", self._rewrite_photo_impl, resource_name, photo
        )

    async def remove_contact_photo(self, resource_name: str) -> None:
        """Take a contact's photo off, every other line of the card kept."""
        await self._execute_with_retry(
            "remove_contact_photo", self._rewrite_photo_impl, resource_name, None
        )

    async def delete_contact(self, resource_name: str) -> bool:
        """Delete a contact. Returns True on success."""
        return await self._execute_with_retry(
            "delete_contact",
            self._delete_contact_impl,
            resource_name,
        )

    # =========================================================================
    # IMPLEMENTATION
    # =========================================================================

    async def _get_all_contacts_cached(
        self, use_cache: bool = True
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """
        Get all contacts, using Redis cache when available.

        Strategy: fetch all contacts + cache in Redis + filter locally.
        This is necessary because iCloud CardDAV search is unreliable.

        The cache entry is an envelope ``{"contacts": [...], "cached_at": iso}``
        so a cache hit can report WHEN the payload was written — the same
        contract as ``GooglePeopleClient``/``GoogleGmailClient``, which
        ``calculate_cache_age_seconds`` relies on to expose data freshness.
        The key is bound to the Apple principal. Older unscoped entries are
        never attributed to whichever account happens to be connected now.

        Returns:
            Tuple of (contacts list, from_cache flag, cache write timestamp).
        """
        binding = content_source_binding(self)
        cache_key = f"apple_contacts:{self.user_id}:all:{binding}"

        # Check cache
        if use_cache and binding:
            try:
                redis = await get_redis_session()
                cached = await redis.get(cache_key)
                if cached:
                    payload = json.loads(cached)
                    if isinstance(payload, dict) and isinstance(payload.get("contacts"), list):
                        return payload["contacts"], True, payload.get(FIELD_CACHED_AT)
            except Exception as e:
                logger.debug("apple_contacts_cache_read_error", error=str(e))

        # Fetch all contacts via CardDAV
        addressbook_url = await self._discover_addressbook()
        client = await self._get_http_client()

        # Step 1: Get all contact hrefs via PROPFIND Depth:1
        resp = await client.request(
            "PROPFIND",
            addressbook_url,
            content=PROPFIND_CONTACTS_HREFS,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_status(resp.status_code)

        hrefs = extract_contact_hrefs(resp.text)
        logger.debug(
            "carddav_contacts_hrefs",
            user_id=str(self.user_id),
            hrefs_count=len(hrefs),
            propfind_status=resp.status_code,
            body_preview=resp.text[:500] if not hrefs else "ok",
        )
        if not hrefs:
            return [], False, None

        # Step 2: Batch fetch contact data via REPORT multiget (without photos)
        href_xml = "\n".join(f"  <d:href>{href}</d:href>" for href in hrefs)
        report_body = REPORT_MULTIGET_TEMPLATE.replace("{hrefs}", href_xml)

        resp = await client.request(
            "REPORT",
            addressbook_url,
            content=report_body,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_status(resp.status_code)

        contacts = parse_multiget_response(resp.text)
        logger.debug(
            "carddav_contacts_fetched",
            user_id=str(self.user_id),
            contacts_count=len(contacts),
            report_status=resp.status_code,
        )

        # Cache all contacts with their write timestamp (freshness contract)
        try:
            redis = await get_redis_session()
            if binding:
                await redis.set(
                    cache_key,
                    json.dumps(
                        {"contacts": contacts, FIELD_CACHED_AT: datetime.now(UTC).isoformat()}
                    ),
                    ex=settings.apple_contacts_cache_ttl,
                )
        except Exception as e:
            logger.debug("apple_contacts_cache_write_error", error=str(e))

        return contacts, False, None

    async def _invalidate_contacts_cache(self) -> None:
        """Invalidate the full contacts cache after mutations."""
        try:
            redis = await get_redis_session()
            await redis.delete(
                f"apple_contacts:{self.user_id}:all",
                f"apple_contacts:{self.user_id}:all:{content_source_binding(self)}",
            )
        except Exception as e:
            logger.debug("cache_invalidation_error", error=str(e))
        # And the directory the recipient suggestions read (Google/Microsoft parity).
        await invalidate_contacts_cache(self.user_id)

    async def _search_contacts_impl(
        self,
        query: str,
        max_results: int,
        use_cache: bool,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Search contacts with local filtering."""
        # Enforce the global per-request volumetry ceiling (centralized cap).
        max_results = apply_max_items_limit(max_results)

        book, from_cache, cached_at = await self._get_all_contacts_cached(use_cache)
        all_contacts = _people_of(book)

        # Local case-insensitive filtering
        query_lower = query.lower()
        results = []
        for contact in all_contacts:
            if _contact_matches_query(contact, query_lower):
                results.append({"person": contact})
                if len(results) >= max_results:
                    break

        return {
            "results": results,
            "totalItems": len(results),
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
        }

    async def _list_email_directory_impl(
        self, max_contacts: int, cache_scope: str | None = None
    ) -> ContactDirectory:
        """The directory through the shared cache, read from the iCloud cache."""
        return await cached_directory(
            self.user_id,
            self.connector_type.value,
            max_contacts,
            lambda cap: self._read_directory(cap, use_cache=cache_scope is None),
            cache_scope=cache_scope,
        )

    async def _read_directory(
        self, max_contacts: int, *, use_cache: bool = True
    ) -> tuple[list[dict[str, Any]], bool]:
        """Cut the (cached) iCloud address book at the caller's cap."""
        book, _from_cache, _cached_at = await self._get_all_contacts_cached(use_cache)
        all_contacts = _people_of(book)
        return all_contacts[:max_contacts], len(all_contacts) > max_contacts

    async def _list_connections_impl(
        self,
        page_size: int,
        page_token: str | None,
        use_cache: bool,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """List all contacts, by family then given name (``contact_order_key``)."""
        book, from_cache, cached_at = await self._get_all_contacts_cached(use_cache)
        # Read whole anyway, so sorted before it pages: a page follows the one before it.
        all_contacts = sorted(_people_of(book), key=contact_order_key)

        # Simple pagination
        start = 0
        if page_token:
            try:
                start = int(page_token)
            except ValueError:
                start = 0

        page = all_contacts[start : start + page_size]
        next_token = str(start + page_size) if start + page_size < len(all_contacts) else None

        return {
            "connections": page,
            "totalItems": len(all_contacts),
            "nextPageToken": next_token,
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
        }

    async def _get_person_impl(
        self,
        resource_name: str,
        fields: list[str] | None,
        use_cache: bool,
    ) -> dict[str, Any]:
        """Get a single contact with full data (including photos)."""
        client = await self._get_http_client()

        url = _contact_url(resource_name)

        resp = await client.get(
            url,
            headers={"Accept": "text/vcard"},
        )
        # 404 is a domain-level "not found"; every other error status must NOT
        # reach normalize_vcard, which degrades an unparsable body into a
        # contact named "Unknown" instead of surfacing the failure.
        self._check_http_status(resp.status_code, allow=(404,))

        if resp.status_code == 404:
            raise ValueError(f"Contact '{resource_name}' not found")

        contact = normalize_vcard(resp.text, resource_name)
        contact["from_cache"] = False
        contact["cached_at"] = None
        return contact

    async def _create_contact_impl(
        self,
        name: str,
        email: str | None,
        phone: str | None,
        organization: str | None,
        notes: str | None,
        *,
        contact_uid: str,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """Create a new contact via CardDAV PUT, at the uid its caller drew."""
        addressbook_url = await self._discover_addressbook()
        client = await self._get_http_client()

        # Build vCard
        vcard_str = build_vcard(
            name,
            email,
            phone,
            organization,
            notes,
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )
        contact_url = f"{addressbook_url.rstrip('/')}/{contact_uid}.vcf"

        resp = await client.put(
            contact_url,
            content=vcard_str,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_status(resp.status_code)

        if resp.status_code not in (201, 204):
            raise ValueError(f"Failed to create contact: HTTP {resp.status_code}")

        await self._invalidate_contacts_cache()

        result = normalize_vcard(vcard_str, contact_url)
        result["resourceName"] = contact_url
        return result

    async def _card_text(self, resource_name: str) -> str:
        """A contact's whole card: a failed read never reaches a rewrite (see below)."""
        client = await self._get_http_client()
        resp = await client.get(_contact_url(resource_name), headers={"Accept": "text/vcard"})
        self._check_http_status(resp.status_code, allow=(404,))
        if resp.status_code == 404:
            raise ValueError(f"Contact '{resource_name}' not found")
        return str(resp.text)

    async def _get_contact_photo_impl(self, resource_name: str) -> ContactPhoto | None:
        return card_photo(await self._card_text(resource_name))

    async def _rewrite_photo_impl(self, resource_name: str, photo: ContactPhoto | None) -> None:
        """The card put back whole, under its one change (no PATCH in CardDAV)."""
        written = card_with_photo(await self._card_text(resource_name), photo)
        await self._put_card(resource_name, written)

    async def _delete_card(self, resource_name: str) -> None:
        """A card gone; one already gone is done."""
        client = await self._get_http_client()
        resp = await client.delete(_contact_url(resource_name))
        self._check_http_status(resp.status_code, allow=(404,))
        await self._invalidate_contacts_cache()

    async def _put_card(self, resource_name: str, written: str) -> None:
        """A card put back whole, the book read again from here on."""
        client = await self._get_http_client()
        resp = await client.put(
            _contact_url(resource_name),
            content=written,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_status(resp.status_code)
        await self._invalidate_contacts_cache()

    async def _update_contact_impl(
        self,
        resource_name: str,
        name: str | None,
        email: str | None,
        phone: str | None,
        organization: str | None,
        notes: str | None,
        address: str | None,
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """Update a contact (full PUT, no PATCH in CardDAV)."""
        client = await self._get_http_client()

        url = _contact_url(resource_name)

        # GET existing vCard
        resp = await client.get(url, headers={"Accept": "text/vcard"})
        # A non-success body must never reach merge_vcard_fields: it falls back
        # to rebuilding a MINIMAL card from the update arguments, and the PUT
        # below would then overwrite every untouched field of the real contact.
        self._check_http_status(resp.status_code, allow=(404,))

        if resp.status_code == 404:
            raise ValueError(f"Contact '{resource_name}' not found for update")

        # Merge fields
        updated_vcard = merge_vcard_fields(
            resp.text,
            name,
            email,
            phone,
            organization,
            notes,
            address,
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )

        # PUT back
        resp = await client.put(
            url,
            content=updated_vcard,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_status(resp.status_code)

        await self._invalidate_contacts_cache()

        return normalize_vcard(updated_vcard, resource_name)

    async def _delete_contact_impl(self, resource_name: str) -> bool:
        """Delete a contact via HTTP DELETE."""
        client = await self._get_http_client()

        url = _contact_url(resource_name)

        resp = await client.delete(url)
        # 404 means "already gone" and stays a False return (idempotent delete);
        # any other error status is a real failure and must not be swallowed.
        self._check_http_status(resp.status_code, allow=(404,))

        await self._invalidate_contacts_cache()
        return resp.status_code in (200, 204)

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._addressbook_url = None


def _contact_matches_query(contact: dict[str, Any], query_lower: str) -> bool:
    """Check if a contact matches a search query (case-insensitive)."""
    # Check display name
    for name in contact.get("names", []):
        display = name.get("displayName", "")
        if query_lower in display.lower():
            return True

    # Check email
    for email in contact.get("emailAddresses", []):
        if query_lower in email.get("value", "").lower():
            return True

    # Check phone
    for phone in contact.get("phoneNumbers", []):
        if query_lower in phone.get("value", "").lower():
            return True

    # Check organization
    for org in contact.get("organizations", []):
        if query_lower in org.get("name", "").lower():
            return True

    return False


def _people_of(book: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The book's contacts: a group's card is none (``apple_contact_groups_mixin``)."""
    return [card for card in book if not card.get("isGroup")]


def _contact_url(resource_name: str) -> str:
    """The URL a contact is read at, on the CardDAV service — or refused before any request.

    A resource name comes from the service (an href, a URL it handed out) but also
    from a browser or a MODEL, and every request carries the account's Apple ID and
    app password. It must be a path under the service, or an https URL on the
    service's own domain (iCloud hands out partition hosts, ``p42-contacts.icloud.com``):
    a foreign host, a userinfo trick (``@host``) or a host suffix (``.host``) appended
    to the base would send those credentials elsewhere.

    Raises:
        ValueError: The name points outside the CardDAV service (a final answer, never retried).
    """
    base = settings.apple_carddav_url.rstrip("/")
    service = urlsplit(base)
    url = resource_name if resource_name.startswith("https://") else f"{base}{resource_name}"
    parts = urlsplit(url)
    on_service = (
        resource_name.startswith(("/", "https://"))
        and parts.scheme == service.scheme == "https"
        and parts.username is None
        and parts.password is None
        and parts.port == service.port
        and _same_service_domain(parts.hostname, service.hostname)
    )
    if not on_service:
        raise ValueError("Not a contact of this account's address book.")
    return url


def _same_service_domain(host: str | None, service_host: str | None) -> bool:
    """The service's host, or a sibling under its parent domain (``*.icloud.com``)."""
    if not host or not service_host:
        return False
    if host == service_host:
        return True
    parent = service_host.split(".", 1)[1] if service_host.count(".") >= 2 else None
    return parent is not None and host.endswith(f".{parent}")
