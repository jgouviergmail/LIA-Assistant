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
from uuid import UUID

import httpx
import structlog
from lxml import etree

from src.core.config import settings
from src.domains.connectors.clients.base_apple_client import BaseAppleClient
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session

# Secure XML parser: disable entity resolution to prevent XXE attacks.
# CardDAV responses come from external servers (network input).
_SAFE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)

logger = structlog.get_logger(__name__)

# XML namespace constants
DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"

# CardDAV XML templates
_PROPFIND_PRINCIPAL = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:current-user-principal/></d:prop>
</d:propfind>"""

_PROPFIND_ADDRESSBOOK_HOME = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <card:addressbook-home-set/>
  </d:prop>
</d:propfind>"""

_PROPFIND_ADDRESSBOOKS = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:resourcetype/>
    <d:displayname/>
  </d:prop>
</d:propfind>"""

_PROPFIND_CONTACTS_HREFS = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:getetag/></d:prop>
</d:propfind>"""

# Bulk fetch WITHOUT photos (photos are up to 224KB/contact in base64)
_REPORT_MULTIGET_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<card:addressbook-multiget xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:getetag/>
    <card:address-data>
      <card:prop name="FN"/>
      <card:prop name="N"/>
      <card:prop name="EMAIL"/>
      <card:prop name="TEL"/>
      <card:prop name="ORG"/>
      <card:prop name="TITLE"/>
      <card:prop name="BDAY"/>
      <card:prop name="ADR"/>
      <card:prop name="NOTE"/>
      <card:prop name="URL"/>
    </card:address-data>
  </d:prop>
  {hrefs}
</card:addressbook-multiget>"""


class AppleContactsClient(BaseAppleClient):
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
            content=_PROPFIND_PRINCIPAL,
            headers={"Content-Type": "application/xml", "Depth": "0"},
        )
        self._check_http_auth_error(resp.status_code)

        logger.debug(
            "carddav_step1_response",
            status=resp.status_code,
            body_preview=resp.text[:500],
        )
        principal_url = _extract_principal_url(resp.text)
        if not principal_url:
            logger.error(
                "carddav_step1_failed",
                status=resp.status_code,
                body=resp.text[:2000],
            )
            raise ValueError("Could not discover CardDAV principal URL")

        if not principal_url.startswith("http"):
            principal_url = f"{settings.apple_carddav_url.rstrip('/')}{principal_url}"

        # Step 2: Get addressbook-home-set from principal
        resp = await client.request(
            "PROPFIND",
            principal_url,
            content=_PROPFIND_ADDRESSBOOK_HOME,
            headers={"Content-Type": "application/xml", "Depth": "0"},
        )
        self._check_http_auth_error(resp.status_code)

        logger.debug(
            "carddav_step2_response",
            status=resp.status_code,
            principal_url=principal_url,
            body_preview=resp.text[:500],
        )
        home_set_url = _extract_addressbook_home_set(resp.text)
        if not home_set_url:
            logger.warning(
                "carddav_step2_no_home_set",
                status=resp.status_code,
                body=resp.text[:2000],
            )
            # Fallback: some servers expose addressbook directly on principal
            home_set_url = principal_url

        if not home_set_url.startswith("http"):
            home_set_url = f"{settings.apple_carddav_url.rstrip('/')}{home_set_url}"

        # Step 3: Find the actual addressbook collection
        resp = await client.request(
            "PROPFIND",
            home_set_url,
            content=_PROPFIND_ADDRESSBOOKS,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_auth_error(resp.status_code)

        logger.debug(
            "carddav_step3_response",
            status=resp.status_code,
            home_set_url=home_set_url,
            body_preview=resp.text[:500],
        )
        addressbook_url = _extract_addressbook_url(resp.text, home_set_url)
        if not addressbook_url:
            logger.warning(
                "carddav_step3_no_addressbook",
                status=resp.status_code,
                body=resp.text[:2000],
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
    ) -> dict[str, Any]:
        """Create a new contact."""
        return await self._execute_with_retry(
            "create_contact",
            self._create_contact_impl,
            name,
            email,
            phone,
            organization,
            notes,
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
    ) -> dict[str, Any]:
        """Update an existing contact (full PUT, no PATCH in CardDAV)."""
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
    ) -> tuple[list[dict[str, Any]], bool]:
        """
        Get all contacts, using Redis cache when available.

        Strategy: fetch all contacts + cache in Redis + filter locally.
        This is necessary because iCloud CardDAV search is unreliable.

        Returns:
            Tuple of (contacts list, from_cache flag indicating actual cache hit).
        """
        cache_key = f"apple_contacts:{self.user_id}:all"

        # Check cache
        if use_cache:
            try:
                redis = await get_redis_session()
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached), True
            except Exception as e:
                logger.debug("apple_contacts_cache_read_error", error=str(e))

        # Fetch all contacts via CardDAV
        addressbook_url = await self._discover_addressbook()
        client = await self._get_http_client()

        # Step 1: Get all contact hrefs via PROPFIND Depth:1
        resp = await client.request(
            "PROPFIND",
            addressbook_url,
            content=_PROPFIND_CONTACTS_HREFS,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_auth_error(resp.status_code)

        hrefs = _extract_contact_hrefs(resp.text)
        logger.debug(
            "carddav_contacts_hrefs",
            user_id=str(self.user_id),
            hrefs_count=len(hrefs),
            propfind_status=resp.status_code,
            body_preview=resp.text[:500] if not hrefs else "ok",
        )
        if not hrefs:
            return [], False

        # Step 2: Batch fetch contact data via REPORT multiget (without photos)
        href_xml = "\n".join(f"  <d:href>{href}</d:href>" for href in hrefs)
        report_body = _REPORT_MULTIGET_TEMPLATE.replace("{hrefs}", href_xml)

        resp = await client.request(
            "REPORT",
            addressbook_url,
            content=report_body,
            headers={"Content-Type": "application/xml", "Depth": "1"},
        )
        self._check_http_auth_error(resp.status_code)

        contacts = _parse_multiget_response(resp.text)
        logger.debug(
            "carddav_contacts_fetched",
            user_id=str(self.user_id),
            contacts_count=len(contacts),
            report_status=resp.status_code,
        )

        # Cache all contacts
        try:
            redis = await get_redis_session()
            await redis.setex(
                cache_key,
                settings.apple_contacts_cache_ttl,
                json.dumps(contacts),
            )
        except Exception as e:
            logger.debug("apple_contacts_cache_write_error", error=str(e))

        return contacts, False

    async def _invalidate_contacts_cache(self) -> None:
        """Invalidate the full contacts cache after mutations."""
        try:
            redis = await get_redis_session()
            await redis.delete(f"apple_contacts:{self.user_id}:all")
        except Exception:
            pass

    async def _search_contacts_impl(
        self,
        query: str,
        max_results: int,
        use_cache: bool,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Search contacts with local filtering."""
        all_contacts, from_cache = await self._get_all_contacts_cached(use_cache)

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
            "cached_at": datetime.now(UTC).isoformat() if from_cache else None,
        }

    async def _list_connections_impl(
        self,
        page_size: int,
        page_token: str | None,
        use_cache: bool,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """List all contacts."""
        all_contacts, from_cache = await self._get_all_contacts_cached(use_cache)

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
            "cached_at": datetime.now(UTC).isoformat() if from_cache else None,
        }

    async def _get_person_impl(
        self,
        resource_name: str,
        fields: list[str] | None,
        use_cache: bool,
    ) -> dict[str, Any]:
        """Get a single contact with full data (including photos)."""
        client = await self._get_http_client()

        # Make resource_name absolute if needed
        url = resource_name
        if not url.startswith("http"):
            url = f"{settings.apple_carddav_url.rstrip('/')}{resource_name}"

        resp = await client.get(
            url,
            headers={"Accept": "text/vcard"},
        )
        self._check_http_auth_error(resp.status_code)

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
    ) -> dict[str, Any]:
        """Create a new contact via CardDAV PUT."""
        addressbook_url = await self._discover_addressbook()
        client = await self._get_http_client()

        # Build vCard
        vcard_str = build_vcard(name, email, phone, organization, notes)
        contact_uid = str(uuid.uuid4())
        contact_url = f"{addressbook_url.rstrip('/')}/{contact_uid}.vcf"

        resp = await client.put(
            contact_url,
            content=vcard_str,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_auth_error(resp.status_code)

        if resp.status_code not in (201, 204):
            raise ValueError(f"Failed to create contact: HTTP {resp.status_code}")

        await self._invalidate_contacts_cache()

        result = normalize_vcard(vcard_str, contact_url)
        result["resourceName"] = contact_url
        return result

    async def _update_contact_impl(
        self,
        resource_name: str,
        name: str | None,
        email: str | None,
        phone: str | None,
        organization: str | None,
        notes: str | None,
        address: str | None,
    ) -> dict[str, Any]:
        """Update a contact (full PUT, no PATCH in CardDAV)."""
        client = await self._get_http_client()

        # Make resource_name absolute if needed
        url = resource_name
        if not url.startswith("http"):
            url = f"{settings.apple_carddav_url.rstrip('/')}{resource_name}"

        # GET existing vCard
        resp = await client.get(url, headers={"Accept": "text/vcard"})
        self._check_http_auth_error(resp.status_code)

        if resp.status_code == 404:
            raise ValueError(f"Contact '{resource_name}' not found for update")

        # Merge fields
        updated_vcard = merge_vcard_fields(
            resp.text, name, email, phone, organization, notes, address
        )

        # PUT back
        resp = await client.put(
            url,
            content=updated_vcard,
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_auth_error(resp.status_code)

        await self._invalidate_contacts_cache()

        return normalize_vcard(updated_vcard, resource_name)

    async def _delete_contact_impl(self, resource_name: str) -> bool:
        """Delete a contact via HTTP DELETE."""
        client = await self._get_http_client()

        url = resource_name
        if not url.startswith("http"):
            url = f"{settings.apple_carddav_url.rstrip('/')}{resource_name}"

        resp = await client.delete(url)
        self._check_http_auth_error(resp.status_code)

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


# =========================================================================
# XML PARSING HELPERS
# =========================================================================


def _extract_principal_url(xml_text: str) -> str | None:
    """Extract current-user-principal URL from PROPFIND response."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)
        # Use Clark notation {namespace}tag — robust regardless of prefix
        href_elements = root.findall(f".//{{{DAV_NS}}}current-user-principal/{{{DAV_NS}}}href")
        if href_elements:
            return href_elements[0].text
    except Exception as e:
        logger.warning("carddav_principal_parse_error", error=str(e))
    return None


def _extract_addressbook_home_set(xml_text: str) -> str | None:
    """Extract addressbook-home-set URL from PROPFIND response on principal."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)
        href_elements = root.findall(f".//{{{CARDDAV_NS}}}addressbook-home-set/{{{DAV_NS}}}href")
        if href_elements and href_elements[0].text:
            return href_elements[0].text
    except Exception as e:
        logger.warning("carddav_home_set_parse_error", error=str(e))
    return None


def _extract_addressbook_url(xml_text: str, base_url: str) -> str | None:
    """Extract addressbook URL from PROPFIND response."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)

        for response in root.findall(f".//{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            href = href_el.text if href_el is not None else None
            if not href:
                continue

            # Check if this is an addressbook (has addressbook resourcetype)
            resourcetype = response.find(
                f".//{{{DAV_NS}}}propstat/{{{DAV_NS}}}prop/{{{DAV_NS}}}resourcetype"
            )
            if resourcetype is not None:
                is_addressbook = resourcetype.find(f"{{{CARDDAV_NS}}}addressbook") is not None
                if is_addressbook:
                    if not href.startswith("http"):
                        href = f"{settings.apple_carddav_url.rstrip('/')}{href}"
                    return href

        # Fallback: use first non-self href that looks like a collection
        for response in root.findall(f".//{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            href = href_el.text if href_el is not None else None
            if href and href != "/" and href.endswith("/"):
                parsed_base = base_url.rstrip("/")
                parsed_href = href.rstrip("/")
                # Skip the home-set URL itself — we want a child collection
                if parsed_href != parsed_base and not parsed_base.endswith(parsed_href):
                    if not href.startswith("http"):
                        href = f"{settings.apple_carddav_url.rstrip('/')}{href}"
                    return href

    except Exception as e:
        logger.warning("carddav_addressbook_parse_error", error=str(e))
    return None


def _extract_contact_hrefs(xml_text: str) -> list[str]:
    """Extract contact hrefs from PROPFIND Depth:1 response."""
    hrefs = []
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)

        for response in root.findall(f".//{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            href = href_el.text if href_el is not None else None
            if href and href.endswith(".vcf"):
                hrefs.append(href)
    except Exception as e:
        logger.warning("carddav_hrefs_parse_error", error=str(e))
    return hrefs


def _parse_multiget_response(xml_text: str) -> list[dict[str, Any]]:
    """Parse addressbook-multiget REPORT response into normalized contacts."""
    contacts = []
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)

        for response in root.findall(f".//{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            href = href_el.text if href_el is not None else None
            if not href:
                continue

            # Get vCard data — search for address-data element
            address_data_el = response.find(
                f".//{{{DAV_NS}}}propstat/{{{DAV_NS}}}prop/" f"{{{CARDDAV_NS}}}address-data"
            )
            if address_data_el is None or not address_data_el.text:
                continue

            try:
                contact = normalize_vcard(address_data_el.text.strip(), href)

                # Extract etag
                etag_el = response.find(
                    f".//{{{DAV_NS}}}propstat/{{{DAV_NS}}}prop/{{{DAV_NS}}}getetag"
                )
                if etag_el is not None and etag_el.text:
                    contact["etag"] = etag_el.text.strip('"')

                contacts.append(contact)
            except Exception as e:
                logger.debug(
                    "carddav_contact_parse_error",
                    href=href,
                    error=str(e),
                )
    except Exception as e:
        logger.warning("carddav_multiget_parse_error", error=str(e))
    return contacts


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
