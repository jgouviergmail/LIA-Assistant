"""The shapes an identifier may take on the way in (ADR-369).

A provider id travels in the body or the query string, never in the path: a
Graph id or an Apple resource name carries characters a path would mangle. It is
still bounded and checked here, before any client sees it — printable ASCII,
no whitespace, no control character — because an id reaches a provider URL, a
log line and a Redis key. Every client that interpolates one into a URL quotes it.

A NAME a person gave a container (an IMAP folder, a label) is another shape:
spaces and any script are legitimate there, control characters never are.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import StringConstraints

#: The longest id any provider was seen to mint is an Exchange id (~ 160 chars);
#: an Apple resource name is a URL path. 1 024 leaves room and bounds the cost.
PROVIDER_ID_MAX_CHARS: Final = 1024
#: A folder or label name, as a person typed it.
PROVIDER_NAME_MAX_CHARS: Final = 512

_PROVIDER_ID: Final = StringConstraints(
    min_length=1, max_length=PROVIDER_ID_MAX_CHARS, pattern=r"^[\x21-\x7e]+$"
)
ProviderId = Annotated[str, _PROVIDER_ID]
#: An optional one: the constraint sits on ``str | None`` — an Annotated wrapped
#: in a union would lose it (``test_annotated_metadata_guard``).
OptionalProviderId = Annotated[str | None, _PROVIDER_ID]
#: A provider's cursor travels back as it came: Graph's skip value is bounded at
#: 2 048 characters (``graph_paging``) plus its parameter's name; Google's and
#: an IMAP offset token are far shorter.
PAGE_TOKEN_MAX_CHARS: Final = 4096

_PAGE_TOKEN: Final = StringConstraints(
    min_length=1, max_length=PAGE_TOKEN_MAX_CHARS, pattern=r"^[\x21-\x7e]+$"
)
PageToken = Annotated[str, _PAGE_TOKEN]
OptionalPageToken = Annotated[str | None, _PAGE_TOKEN]
_PROVIDER_NAME: Final = StringConstraints(
    min_length=1,
    max_length=PROVIDER_NAME_MAX_CHARS,
    pattern=r"^[^\x00-\x1f\x7f]+$",
)
ProviderName = Annotated[str, _PROVIDER_NAME]
OptionalProviderName = Annotated[str | None, _PROVIDER_NAME]
