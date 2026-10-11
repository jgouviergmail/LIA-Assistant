"""Relations and Connections compose their reviewed public proposal editors."""

from src.domains.agents.application.peer_editors import PEER_EDITORS
from src.domains.agents.application.relation_editors import RELATION_EDITORS

PEOPLE_EDITORS = {**RELATION_EDITORS, **PEER_EDITORS}
