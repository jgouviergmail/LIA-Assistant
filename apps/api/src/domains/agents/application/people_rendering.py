"""Relations and Connections compose public previews without central renderer growth."""

from src.domains.agents.application.peer_block import canonical_peer_block
from src.domains.agents.application.peer_image import canonical_peer_image
from src.domains.agents.application.peer_removal import canonical_peer_removal
from src.domains.agents.application.peer_request import canonical_peer_request
from src.domains.agents.application.peer_response import canonical_peer_response
from src.domains.agents.application.peer_share import canonical_peer_share
from src.domains.agents.application.relation_rendering import (
    RELATION_CANONICAL,
    RELATION_PREVIEW_NOTES,
)

PEOPLE_PREVIEW_NOTES = {
    **RELATION_PREVIEW_NOTES,
    "peer_preferences.update": "application_peer_preferences_note",
    "peer_connection.request": "application_peer_request_note",
    "peer_connection.respond": "application_peer_response_note",
    "peer_share.update": "application_peer_share_note",
    "peer_connection.remove": "application_peer_removal_note",
    "peer_block.update": "application_peer_block_note",
    "peer_image.share": "application_peer_image_note",
}
PEOPLE_CANONICAL = {
    **RELATION_CANONICAL,
    "peer_connection.request": canonical_peer_request,
    "peer_connection.respond": canonical_peer_response,
    "peer_share.update": canonical_peer_share,
    "peer_connection.remove": canonical_peer_removal,
    "peer_block.update": canonical_peer_block,
    "peer_image.share": canonical_peer_image,
}
