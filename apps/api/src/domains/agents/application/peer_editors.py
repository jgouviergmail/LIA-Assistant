"""Reviewed Connections proposal editors compose without central-dispatch growth."""

from src.domains.agents.application.peer_block_editing import rebuild_peer_block_draft
from src.domains.agents.application.peer_image_editing import rebuild_peer_image_draft
from src.domains.agents.application.peer_preference_editing import rebuild_peer_preference_draft
from src.domains.agents.application.peer_removal_editing import rebuild_peer_removal_draft
from src.domains.agents.application.peer_request_editing import rebuild_peer_request_draft
from src.domains.agents.application.peer_response_editing import rebuild_peer_response_draft
from src.domains.agents.application.peer_share_editing import rebuild_peer_share_draft

PEER_EDITORS = {
    "peer_image.share": rebuild_peer_image_draft,
    "peer_block.update": rebuild_peer_block_draft,
    "peer_connection.remove": rebuild_peer_removal_draft,
    "peer_share.update": rebuild_peer_share_draft,
    "peer_connection.respond": rebuild_peer_response_draft,
    "peer_preferences.update": rebuild_peer_preference_draft,
    "peer_connection.request": rebuild_peer_request_draft,
}
