"""Every shipped Jev integration has one switch and one configuration slot."""

from dataclasses import dataclass
from enum import StrEnum

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.system_settings.models import SystemSettingKey


class JevUsage(StrEnum):
    """Shipped, independently switchable decision points."""

    MEETING_TEMPLATE = "meeting_template"
    RADIO_VERIFICATION = "radio_verification"
    CONSULTATION_PATH = "consultation_path"
    CONSULTATION_BOUNDED = "consultation_bounded"
    OBSERVE_MEMORY = "observe_memory"
    OBSERVE_INTERESTS = "observe_interests"
    OBSERVE_JOURNAL = "observe_journal"
    OBSERVE_OPEN_LOOPS = "observe_open_loops"
    HITL_EXCLUSION = "hitl_exclusion"
    MEMORY_REFERENCE_PRESENCE = "memory_reference_presence"
    HITL_REJECTION = "hitl_rejection"
    PARAMETER_KIND = "parameter_kind"
    EMAIL_CLASSIFICATION = "email_classification"
    EVENT_CLASSIFICATION = "event_classification"


@dataclass(frozen=True)
class JevUsageSpec:
    """One usage's routing, configuration, translated presentation and stored thresholds.

    ``thresholds_key`` is ``None`` for a usage that decides nothing (the observers); the
    gates it stores are declared in ``jev_gates.py``, which checks both lists agree.
    """

    setting_key: SystemSettingKey
    llm_type: str
    label_key: str
    thresholds_key: SystemSettingKey | None = None


JEV_USAGES: dict[JevUsage, JevUsageSpec] = {
    JevUsage.MEETING_TEMPLATE: JevUsageSpec(
        SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED,
        "meeting_template_selection",
        "settings.admin.jev.usages.meeting_template",
        SystemSettingKey.JEV_MEETING_TEMPLATE_THRESHOLDS,
    ),
    JevUsage.RADIO_VERIFICATION: JevUsageSpec(
        SystemSettingKey.JEV_RADIO_VERIFICATION_ENABLED,
        "jev_radio_verification",
        "settings.admin.jev.usages.radio_verification",
        SystemSettingKey.JEV_RADIO_VERIFICATION_THRESHOLDS,
    ),
    JevUsage.CONSULTATION_PATH: JevUsageSpec(
        SystemSettingKey.JEV_CONSULTATION_PATH_ENABLED,
        "jev_consultation_path",
        "settings.admin.jev.usages.consultation_path",
        SystemSettingKey.JEV_CONSULTATION_PATH_THRESHOLDS,
    ),
    JevUsage.CONSULTATION_BOUNDED: JevUsageSpec(
        SystemSettingKey.JEV_CONSULTATION_BOUNDED_ENABLED,
        "jev_consultation_bounded",
        "settings.admin.jev.usages.consultation_bounded",
        SystemSettingKey.JEV_CONSULTATION_BOUNDED_THRESHOLDS,
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
        SystemSettingKey.JEV_HITL_EXCLUSION_THRESHOLDS,
    ),
    JevUsage.MEMORY_REFERENCE_PRESENCE: JevUsageSpec(
        SystemSettingKey.JEV_MEMORY_REFERENCE_PRESENCE_ENABLED,
        "jev_memory_reference_presence",
        "settings.admin.jev.usages.memory_reference_presence",
        SystemSettingKey.JEV_MEMORY_REFERENCE_PRESENCE_THRESHOLDS,
    ),
    JevUsage.HITL_REJECTION: JevUsageSpec(
        SystemSettingKey.JEV_HITL_REJECTION_ENABLED,
        "jev_hitl_rejection",
        "settings.admin.jev.usages.hitl_rejection",
        SystemSettingKey.JEV_HITL_REJECTION_THRESHOLDS,
    ),
    JevUsage.PARAMETER_KIND: JevUsageSpec(
        SystemSettingKey.JEV_PARAMETER_KIND_ENABLED,
        "jev_parameter_kind",
        "settings.admin.jev.usages.parameter_kind",
        SystemSettingKey.JEV_PARAMETER_KIND_THRESHOLDS,
    ),
    JevUsage.EMAIL_CLASSIFICATION: JevUsageSpec(
        SystemSettingKey.JEV_EMAIL_CLASSIFICATION_ENABLED,
        "jev_email_classification",
        "settings.admin.jev.usages.email_classification",
        SystemSettingKey.JEV_EMAIL_CLASSIFICATION_THRESHOLDS,
    ),
    JevUsage.EVENT_CLASSIFICATION: JevUsageSpec(
        SystemSettingKey.JEV_EVENT_CLASSIFICATION_ENABLED,
        "jev_event_classification",
        "settings.admin.jev.usages.event_classification",
        SystemSettingKey.JEV_EVENT_CLASSIFICATION_THRESHOLDS,
    ),
}


def assert_jev_registry_complete() -> None:
    """Refuse a usage without a switch, or an unregistered decision slot."""
    slots = {
        key for key, meta in LLM_TYPES_REGISTRY.items() if meta.required_kind.value == "decision"
    }
    keys = {spec.setting_key for spec in JEV_USAGES.values()}
    thresholds = [spec.thresholds_key for spec in JEV_USAGES.values() if spec.thresholds_key]
    if (
        set(JEV_USAGES) != set(JevUsage)
        or {spec.llm_type for spec in JEV_USAGES.values()} != slots
        or len(keys) != len(JEV_USAGES)
        or len(thresholds) != len(set(thresholds))
    ):
        raise RuntimeError("Jev usage registry is incomplete or has shared switches")


assert_jev_registry_complete()
