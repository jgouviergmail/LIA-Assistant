"""Confirmed phone-data edits rebuild source-owned snapshots, including the health adapter."""

from src.domains.agents.application.health_editors import HEALTH_EDITORS
from src.domains.agents.application.sms_editing import SMS_EDITORS

INGESTION_EDITORS = {**HEALTH_EDITORS, **SMS_EDITORS}
