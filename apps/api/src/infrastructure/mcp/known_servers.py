"""Known MCP servers: what a person may add without typing an address.

One declaration, two readers: the settings screen and the chat's private form read it
through ``GET /mcp/servers/known``, and the assistant's configuration tool publishes its
keys in its schema. A known server is a PUBLIC fact (a vendor's own hosted endpoint, the
way it authenticates, what it is for): it carries no credential and confers nothing. Adding
one goes through the create door every typed address goes through, so an entry is held to
that door's schema by ``tests/unit/infrastructure/mcp/test_known_servers.py``.

An entry is admitted on measured facts, never on a vendor's page alone:

1. the vendor hosts it itself, on a fixed HTTPS address, over Streamable HTTP;
2. LIA reaches it AS IT IS, in one of four ways: with no account at all; by OAuth 2.1
   through an authorization server that publishes a registration endpoint (RFC 7591) and
   PKCE ``S256`` — what ``MCPOAuthFlowHandler.discover_auth_server`` finds, no client to
   pre-register; by OAuth with the person's OWN application where the vendor registers
   none (``own_oauth_client``: the authorization server is still discovered); or with a
   key or a token the vendor issues to the person, which the address refuses to answer
   without (``api_key`` names the header it is read from, ``bearer`` is read from
   ``Authorization``). The catalogue holds the header's NAME, never a value: the secret
   is the person's to type in the form;
3. for a server that needs no account, what its tools weigh in a prompt was read and
   stays moderate (a server whose five tools weigh seventeen thousand tokens is left to
   be added by hand, knowingly).

``task mcp:known-servers:check`` re-measures 1 and 2 for every entry (network, read-only,
no account): run it before a release, an address a vendor moved is a dead card.

``domain_description`` is what the assistant reads to route a request to the server
(technical English, ADR-323). It names the SUBJECT, never a tool nobody listed: the tools
of a server that needs an account are unknown until the person signs in, and the settings
screen can then write the description from the real ones. What the PERSON reads about a
server is in the web locales, by key (``settings.mcp.known.servers``); its icon is the
vendor's own, a file of the web application's ``public/mcp-icons/`` named by ``icon``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

#: How a known server authenticates. An API key or a bearer token is the person's own: the
#: catalogue names the scheme (and the header of a key), the person types the value.
KnownServerAuth = Literal["none", "oauth2", "api_key", "bearer"]

#: Where the web application serves the vendors' icons (``apps/web/public/mcp-icons/``).
KNOWN_SERVER_ICON_DIRECTORY: Final[str] = "mcp-icons"


@dataclass(frozen=True, slots=True)
class KnownMCPServer:
    """One vendor-hosted server offered ready to add.

    Attributes:
        key: Stable slug: the published identifier, and the key of the screen's wording.
        name: The brand's own name; the default name of the server once added.
        url: The vendor's Streamable HTTP endpoint (HTTPS, public whole).
        auth_type: ``none``; ``oauth2`` at the vendor; ``api_key`` or ``bearer``, a
            secret the vendor issues to the person.
        domain_description: What the server is about, for the assistant's routing.
        icon: The vendor's icon, a file name under the web application's
            ``public/mcp-icons/`` (two servers of one vendor may share it).
        header_name: The header an ``api_key`` server reads its key from; ``None`` for
            every other scheme.
        oauth_scopes: The scopes an ``oauth2`` server must be asked for, when its
            authorization server publishes none that suffice; ``None`` otherwise.
        own_oauth_client: Whether an ``oauth2`` vendor registers no client for LIA, so the
            person brings their own OAuth application (its id and secret).
    """

    key: str
    name: str
    url: str
    auth_type: KnownServerAuth
    domain_description: str
    icon: str
    header_name: str | None = None
    oauth_scopes: str | None = None
    own_oauth_client: bool = False


#: The catalogue, in the order it is offered (by name).
KNOWN_MCP_SERVERS: Final[tuple[KnownMCPServer, ...]] = (
    KnownMCPServer(
        key="agentmail",
        name="AgentMail",
        url="https://mcp.agentmail.to/mcp",
        auth_type="bearer",
        domain_description=(
            "AgentMail: email inboxes of the agent's own, separate from the person's "
            "mailbox: send, receive, search and organise messages, threads and drafts."
        ),
        icon="agentmail.png",
    ),
    KnownMCPServer(
        key="airtable",
        name="Airtable",
        url="https://mcp.airtable.com/mcp",
        auth_type="oauth2",
        domain_description="The person's Airtable workspace: bases, tables and records.",
        icon="airtable.png",
    ),
    KnownMCPServer(
        key="asana",
        name="Asana",
        url="https://mcp.asana.com/v2/mcp",
        auth_type="oauth2",
        domain_description="The person's Asana workspace: tasks, projects and goals.",
        icon="asana.png",
    ),
    KnownMCPServer(
        key="botbin",
        name="botbin.io",
        url="https://botbin.io/mcp",
        auth_type="none",
        domain_description=(
            "botbin.io: self-contained HTML pages, dashboards and visualisations published "
            "at a public link, then updated in place or read back."
        ),
        icon="botbin.svg",
    ),
    KnownMCPServer(
        key="brightdata",
        name="Bright Data",
        url="https://mcp.brightdata.com/mcp",
        auth_type="bearer",
        domain_description=(
            "Bright Data: live web data: search engine results (Google, Bing), any web "
            "page read as Markdown, and structured data from ready-made scrapers of "
            "popular sites (Amazon, LinkedIn, Instagram, Zillow...)."
        ),
        icon="brightdata.png",
    ),
    KnownMCPServer(
        key="cala",
        name="Cala",
        url="https://api.cala.ai/mcp/",
        auth_type="api_key",
        domain_description=(
            "Cala: verified knowledge with its sources: researched answers with citations, "
            "and structured entities (companies, people, places, laws, financial "
            "instruments) to search and read."
        ),
        icon="cala.png",
        header_name="X-API-Key",
    ),
    KnownMCPServer(
        key="calendly",
        name="Calendly",
        url="https://mcp.calendly.com",
        auth_type="oauth2",
        domain_description=(
            "The person's Calendly account: scheduling links, event types, scheduled "
            "events and invitees."
        ),
        icon="calendly.svg",
    ),
    KnownMCPServer(
        key="canva",
        name="Canva",
        url="https://mcp.canva.com/mcp",
        auth_type="oauth2",
        domain_description="The person's Canva account: designs.",
        icon="canva.png",
    ),
    KnownMCPServer(
        key="clickup",
        name="ClickUp",
        url="https://mcp.clickup.com/mcp",
        auth_type="oauth2",
        domain_description="The person's ClickUp workspace: tasks, lists and docs.",
        icon="clickup.png",
    ),
    KnownMCPServer(
        key="coingecko",
        name="CoinGecko",
        url="https://mcp.api.coingecko.com/mcp",
        auth_type="none",
        domain_description=(
            "CoinGecko: cryptocurrency market data: prices, market capitalisation, trading "
            "volumes, historical charts, exchanges and token information."
        ),
        icon="coingecko.png",
    ),
    KnownMCPServer(
        key="context7",
        name="Context7",
        url="https://mcp.context7.com/mcp",
        auth_type="none",
        domain_description=(
            "Up-to-date, version-specific documentation and code examples of software "
            "libraries and frameworks."
        ),
        icon="context7.png",
    ),
    KnownMCPServer(
        key="credits_fm",
        name="Credits.fm",
        url="https://credits.fm/mcp",
        auth_type="none",
        domain_description=(
            "Credits.fm: music credits: the songwriters, performers, producers and "
            "publishers of songs, and music identifiers (ISRC, ISWC, IPI, ISNI, UPC), "
            "from a title, an artist or a Spotify or Apple Music link."
        ),
        icon="credits_fm.png",
    ),
    KnownMCPServer(
        key="deepwiki",
        name="DeepWiki",
        url="https://mcp.deepwiki.com/mcp",
        auth_type="none",
        domain_description=(
            "Any public GitHub repository explained: its documentation structure, its "
            "contents, and answers to questions about it."
        ),
        icon="deepwiki.png",
    ),
    KnownMCPServer(
        key="drawio",
        name="draw.io",
        url="https://mcp.draw.io/mcp",
        auth_type="none",
        domain_description=(
            "draw.io: diagrams (flowcharts, architecture, sequence, organisation charts) "
            "drawn from Mermaid syntax or draw.io XML and shown interactively, with a "
            "search of the draw.io shape library."
        ),
        icon="drawio.svg",
    ),
    KnownMCPServer(
        key="dropbox",
        name="Dropbox",
        url="https://mcp.dropbox.com/mcp",
        auth_type="oauth2",
        domain_description="The person's Dropbox: files and folders.",
        icon="dropbox.svg",
    ),
    KnownMCPServer(
        key="exa",
        name="Exa",
        url="https://mcp.exa.ai/mcp",
        auth_type="none",
        domain_description=(
            "Exa: web search for current information (news, facts, people, companies) and "
            "the full content of a web page read as clean text."
        ),
        icon="exa.png",
    ),
    KnownMCPServer(
        key="findadomain",
        name="Find a Domain",
        url="https://api.findadomain.dev/mcp",
        auth_type="none",
        domain_description=(
            "Find a Domain: whether a domain name is free to register, extension by "
            "extension, and the list of top-level domains."
        ),
        icon="findadomain.png",
    ),
    KnownMCPServer(
        key="github",
        name="GitHub",
        url="https://api.githubcopilot.com/mcp/",
        auth_type="oauth2",
        domain_description=(
            "The person's GitHub: repositories, files, branches, commits, issues, pull "
            "requests and their reviews, releases, and code search."
        ),
        icon="github.svg",
        oauth_scopes="repo",
        own_oauth_client=True,
    ),
    KnownMCPServer(
        key="huggingface",
        name="Hugging Face",
        url="https://huggingface.co/mcp",
        auth_type="bearer",
        domain_description=(
            "Hugging Face Hub: models, datasets, Spaces and papers to search and read, and "
            "tasks run through Spaces (image generation, speech, background removal...)."
        ),
        icon="huggingface.svg",
    ),
    KnownMCPServer(
        key="ign_carto",
        name="IGN Carto",
        url="https://geollm.beta.ign.fr/carto/mcp",
        auth_type="none",
        domain_description=(
            "IGN, the French national mapping agency: an interactive map of a place in "
            "France on an IGN background (Plan IGN map or aerial photography)."
        ),
        icon="ign.png",
    ),
    KnownMCPServer(
        key="ign_geocontext",
        name="IGN Geocontext",
        url="https://geollm.beta.ign.fr/geocontext/mcp",
        auth_type="none",
        domain_description=(
            "IGN Geoplatform: geographic facts about a place in France: geocoding, "
            "altitude, administrative units, cadastral parcels, town-planning zoning, "
            "public-utility easements, and IGN reference datasets (WFS)."
        ),
        icon="ign.png",
    ),
    KnownMCPServer(
        key="kiwi",
        name="Kiwi.com",
        url="https://mcp.kiwi.com",
        auth_type="none",
        domain_description=(
            "Flight search on Kiwi.com: itineraries and prices between two places on "
            "given dates, with booking links."
        ),
        icon="kiwi.png",
    ),
    KnownMCPServer(
        key="linear",
        name="Linear",
        url="https://mcp.linear.app/mcp",
        auth_type="oauth2",
        domain_description="The person's Linear workspace: issues, projects and comments.",
        icon="linear.png",
    ),
    KnownMCPServer(
        key="microsoft_learn",
        name="Microsoft Learn",
        url="https://learn.microsoft.com/api/mcp",
        auth_type="none",
        domain_description=(
            "Official Microsoft, Azure and .NET documentation and code samples, to "
            "search and read."
        ),
        icon="microsoft_learn.png",
    ),
    KnownMCPServer(
        key="notion",
        name="Notion",
        url="https://mcp.notion.com/mcp",
        auth_type="oauth2",
        domain_description="The person's Notion workspace: pages, databases and comments.",
        icon="notion.png",
    ),
    KnownMCPServer(
        key="origami",
        name="Origami Entreprises",
        url="https://mcp.origami-entreprises.fr/mcp",
        auth_type="oauth2",
        domain_description=(
            "Origami Entreprises: French companies: identity, directors, annual accounts "
            "and financial indicators, BODACC notices and legal filings, and the person's "
            "company portfolios and alerts."
        ),
        icon="origami.svg",
    ),
    KnownMCPServer(
        key="parallel",
        name="Parallel",
        url="https://mcp.parallel.ai/mcp",
        auth_type="none",
        domain_description=(
            "Parallel: web search and web page reading for current information, image "
            "search, and specialised sources (scientific preprints, PubMed, clinical "
            "trials, chemical compounds)."
        ),
        icon="parallel.svg",
    ),
    KnownMCPServer(
        key="stewdio",
        name="Stewdio",
        url="https://mcp.stewdio.ai/mcp",
        auth_type="oauth2",
        domain_description=(
            "The person's Stewdio account: motion-graphics files (pages, compositions and "
            "layers), their assets and their comments."
        ),
        icon="stewdio.svg",
    ),
    KnownMCPServer(
        key="streamline",
        name="Streamline",
        url="https://public-api.streamlinehq.com/mcp",
        auth_type="api_key",
        domain_description=(
            "Streamline: a library of icons and illustrations: search sets, families and "
            "styles, and download icons as files."
        ),
        icon="streamline.svg",
        header_name="X-API-Key",
    ),
    KnownMCPServer(
        key="todoist",
        name="Todoist",
        url="https://ai.todoist.net/mcp",
        auth_type="oauth2",
        domain_description="The person's Todoist: tasks, projects, sections and labels.",
        icon="todoist.png",
    ),
    KnownMCPServer(
        key="trivago",
        name="trivago",
        url="https://mcp.trivago.com/mcp",
        auth_type="none",
        domain_description=(
            "Hotel search on trivago: accommodation and prices compared for a destination "
            "and dates, and price trends of a destination."
        ),
        icon="trivago.png",
    ),
    KnownMCPServer(
        key="wolfram",
        name="Wolfram|Alpha",
        url="https://agenttools.wolfram.com/mcp",
        auth_type="none",
        domain_description=(
            "Wolfram|Alpha and the Wolfram Language: exact computation, mathematics and "
            "curated factual data."
        ),
        icon="wolfram.svg",
    ),
)

#: The published keys, in the catalogue's order.
KNOWN_MCP_SERVER_KEYS: Final[tuple[str, ...]] = tuple(server.key for server in KNOWN_MCP_SERVERS)

_BY_KEY: Final[dict[str, KnownMCPServer]] = {server.key: server for server in KNOWN_MCP_SERVERS}


def find_known_server(key: str) -> KnownMCPServer | None:
    """The catalogue entry a key names.

    Args:
        key: A published key, exactly as published (no folding, no trimming).

    Returns:
        The entry, or ``None`` when the catalogue publishes no such key.
    """
    return _BY_KEY.get(key)
