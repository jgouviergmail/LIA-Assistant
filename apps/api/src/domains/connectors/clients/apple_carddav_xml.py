"""CardDAV's XML for the Apple contacts client: request bodies and response readers.

Out of ``apple_contacts_client.py`` (ADR-369 lot L2): the client kept its HTTP
conversation, this module the documents it exchanges. A response comes from a
network peer, so it is parsed with entity resolution and network access off
(XXE), and a reader that cannot read answers None or nothing — never raises.
"""

from typing import Any

import structlog
from lxml import etree

from src.core.config import settings
from src.domains.connectors.clients.normalizers.contacts_normalizer import normalize_vcard

logger = structlog.get_logger(__name__)

# Secure XML parser: disable entity resolution to prevent XXE attacks.
# CardDAV responses come from external servers (network input).
_SAFE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)

# XML namespace constants
DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"

# CardDAV XML templates
PROPFIND_PRINCIPAL = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:current-user-principal/></d:prop>
</d:propfind>"""

PROPFIND_ADDRESSBOOK_HOME = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <card:addressbook-home-set/>
  </d:prop>
</d:propfind>"""

PROPFIND_ADDRESSBOOKS = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">
  <d:prop>
    <d:resourcetype/>
    <d:displayname/>
  </d:prop>
</d:propfind>"""

PROPFIND_CONTACTS_HREFS = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:getetag/></d:prop>
</d:propfind>"""

# Bulk fetch WITHOUT photos (photos are up to 224KB/contact in base64)
REPORT_MULTIGET_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
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


def extract_principal_url(xml_text: str) -> str | None:
    """Extract current-user-principal URL from PROPFIND response."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)
        # Use Clark notation {namespace}tag — robust regardless of prefix
        href_elements = root.findall(f".//{{{DAV_NS}}}current-user-principal/{{{DAV_NS}}}href")
        if href_elements:
            return href_elements[0].text
    except Exception as e:
        logger.warning("carddav_principal_parse_error", error_type=type(e).__name__)
    return None


def extract_addressbook_home_set(xml_text: str) -> str | None:
    """Extract addressbook-home-set URL from PROPFIND response on principal."""
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=_SAFE_XML_PARSER)
        href_elements = root.findall(f".//{{{CARDDAV_NS}}}addressbook-home-set/{{{DAV_NS}}}href")
        if href_elements and href_elements[0].text:
            return href_elements[0].text
    except Exception as e:
        logger.warning("carddav_home_set_parse_error", error_type=type(e).__name__)
    return None


def extract_addressbook_url(xml_text: str, base_url: str) -> str | None:
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
        logger.warning("carddav_addressbook_parse_error", error_type=type(e).__name__)
    return None


def extract_contact_hrefs(xml_text: str) -> list[str]:
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
        logger.warning("carddav_hrefs_parse_error", error_type=type(e).__name__)
    return hrefs


def parse_multiget_response(xml_text: str) -> list[dict[str, Any]]:
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
        logger.warning("carddav_multiget_parse_error", error_type=type(e).__name__)
    return contacts


__all__ = [
    "CARDDAV_NS",
    "DAV_NS",
    "PROPFIND_ADDRESSBOOKS",
    "PROPFIND_ADDRESSBOOK_HOME",
    "PROPFIND_CONTACTS_HREFS",
    "PROPFIND_PRINCIPAL",
    "REPORT_MULTIGET_TEMPLATE",
    "extract_addressbook_home_set",
    "extract_addressbook_url",
    "extract_contact_hrefs",
    "extract_principal_url",
    "parse_multiget_response",
]
