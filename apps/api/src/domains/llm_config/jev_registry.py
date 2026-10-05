"""Every shipped Jev integration has one switch and one configuration slot."""

from dataclasses import dataclass
from enum import StrEnum

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.system_settings.models import SystemSettingKey


class JevUsage(StrEnum):
    """Shipped, independently switchable decision points."""

    MEETING_TEMPLATE = "meeting_template"
    FILTER_EMAIL = "filter_email"
    FILTER_EVENT = "filter_event"
    FILTER_TASK = "filter_task"
    FILTER_FILE = "filter_file"
    RADIO_VERIFICATION = "radio_verification"
    CONSULTATION_PATH = "consultation_path"
    CONSULTATION_BOUNDED = "consultation_bounded"
    OBSERVE_MEMORY = "observe_memory"
    OBSERVE_INTERESTS = "observe_interests"
    OBSERVE_JOURNAL = "observe_journal"
    OBSERVE_OPEN_LOOPS = "observe_open_loops"
    INITIATIVE_UTILITY = "initiative_utility"
    HITL_EXCLUSION = "hitl_exclusion"
    FILTER_REMINDER = "filter_reminder"
    FILTER_TICKET = "filter_ticket"
    FILTER_MCP = "filter_mcp"
    FILTER_DOCUMENT = "filter_document"
    MEMORY_REFERENCE_PRESENCE = "memory_reference_presence"
    HITL_REJECTION = "hitl_rejection"


@dataclass(frozen=True)
class JevUsageSpec:
    """One usage's routing, configuration and translated presentation."""

    setting_key: SystemSettingKey
    llm_type: str
    label_key: str


JEV_USAGES: dict[JevUsage, JevUsageSpec] = {
    JevUsage.MEETING_TEMPLATE: JevUsageSpec(
        SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED,
        "meeting_template_selection",
        "settings.admin.jev.usages.meeting_template",
    ),
    JevUsage.FILTER_EMAIL: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_EMAIL_ENABLED,
        "jev_filter_email",
        "settings.admin.jev.usages.filter_email",
    ),
    JevUsage.FILTER_EVENT: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_EVENT_ENABLED,
        "jev_filter_event",
        "settings.admin.jev.usages.filter_event",
    ),
    JevUsage.FILTER_TASK: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_TASK_ENABLED,
        "jev_filter_task",
        "settings.admin.jev.usages.filter_task",
    ),
    JevUsage.FILTER_FILE: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_FILE_ENABLED,
        "jev_filter_file",
        "settings.admin.jev.usages.filter_file",
    ),
    JevUsage.RADIO_VERIFICATION: JevUsageSpec(
        SystemSettingKey.JEV_RADIO_VERIFICATION_ENABLED,
        "jev_radio_verification",
        "settings.admin.jev.usages.radio_verification",
    ),
    JevUsage.CONSULTATION_PATH: JevUsageSpec(
        SystemSettingKey.JEV_CONSULTATION_PATH_ENABLED,
        "jev_consultation_path",
        "settings.admin.jev.usages.consultation_path",
    ),
    JevUsage.CONSULTATION_BOUNDED: JevUsageSpec(
        SystemSettingKey.JEV_CONSULTATION_BOUNDED_ENABLED,
        "jev_consultation_bounded",
        "settings.admin.jev.usages.consultation_bounded",
    ),
    JevUsage.INITIATIVE_UTILITY: JevUsageSpec(
        SystemSettingKey.JEV_INITIATIVE_UTILITY_ENABLED,
        "jev_initiative_utility",
        "settings.admin.jev.usages.initiative_utility",
    ),
    JevUsage.OBSERVE_MEMORY: JevUsageSpec(
        SystemSettingKey.JEV_OBSERVE_MEMORY_ENABLED,
        "jev_observe_memory",
        "settings.admin.jev.usages.observe_memory",
    ),
    JevUsage.OBSERVE_INTERESTS: JevUsageSpec(
        SystemSettingKey.JEV_OBSERVE_INTERESTS_ENABLED,
        "jev_observe_interests",
        "settings.admin.jev.usages.observe_interests",
    ),
    JevUsage.OBSERVE_JOURNAL: JevUsageSpec(
        SystemSettingKey.JEV_OBSERVE_JOURNAL_ENABLED,
        "jev_observe_journal",
        "settings.admin.jev.usages.observe_journal",
    ),
    JevUsage.OBSERVE_OPEN_LOOPS: JevUsageSpec(
        SystemSettingKey.JEV_OBSERVE_OPEN_LOOPS_ENABLED,
        "jev_observe_open_loops",
        "settings.admin.jev.usages.observe_open_loops",
    ),
    JevUsage.HITL_EXCLUSION: JevUsageSpec(
        SystemSettingKey.JEV_HITL_EXCLUSION_ENABLED,
        "jev_hitl_exclusion",
        "settings.admin.jev.usages.hitl_exclusion",
    ),
    JevUsage.FILTER_REMINDER: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_REMINDER_ENABLED,
        "jev_filter_reminder",
        "settings.admin.jev.usages.filter_reminder",
    ),
    JevUsage.FILTER_TICKET: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_TICKET_ENABLED,
        "jev_filter_ticket",
        "settings.admin.jev.usages.filter_ticket",
    ),
    JevUsage.FILTER_MCP: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_MCP_ENABLED,
        "jev_filter_mcp",
        "settings.admin.jev.usages.filter_mcp",
    ),
    JevUsage.FILTER_DOCUMENT: JevUsageSpec(
        SystemSettingKey.JEV_FILTER_DOCUMENT_ENABLED,
        "jev_filter_document",
        "settings.admin.jev.usages.filter_document",
    ),
    JevUsage.MEMORY_REFERENCE_PRESENCE: JevUsageSpec(
        SystemSettingKey.JEV_MEMORY_REFERENCE_PRESENCE_ENABLED,
        "jev_memory_reference_presence",
        "settings.admin.jev.usages.memory_reference_presence",
    ),
    JevUsage.HITL_REJECTION: JevUsageSpec(
        SystemSettingKey.JEV_HITL_REJECTION_ENABLED,
        "jev_hitl_rejection",
        "settings.admin.jev.usages.hitl_rejection",
    ),
}


def assert_jev_registry_complete() -> None:
    """Refuse a usage without a switch, or an unregistered decision slot."""
    slots = {
        key for key, meta in LLM_TYPES_REGISTRY.items() if meta.required_kind.value == "decision"
    }
    keys = {spec.setting_key for spec in JEV_USAGES.values()}
    if (
        set(JEV_USAGES) != set(JevUsage)
        or {spec.llm_type for spec in JEV_USAGES.values()} != slots
        or len(keys) != len(JEV_USAGES)
    ):
        raise RuntimeError("Jev usage registry is incomplete or has shared switches")


assert_jev_registry_complete()
