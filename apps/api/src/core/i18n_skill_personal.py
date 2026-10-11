"""Six-language personal skill state confirmation, separate from administration."""

from src.core.i18n_types import Language

SKILL_PERSONAL_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Activation personnelle de compétence",
        "Modifie uniquement votre activation personnelle. Aucune compétence n’est exécutée ; les réglages globaux et les autres comptes restent inchangés.",
    ),
    "en": (
        "Personal skill activation",
        "Changes only your personal enabled state. No skill is executed; global settings and other accounts are unchanged.",
    ),
    "de": (
        "Persönliche Skill-Aktivierung",
        "Ändert nur Ihre persönliche Aktivierung. Der Skill wird nicht ausgeführt; globale Einstellungen und andere Konten bleiben unverändert.",
    ),
    "es": (
        "Activación personal de una competencia",
        "Cambia solo su activación personal. No ejecuta la competencia; la configuración global y las otras cuentas no cambian.",
    ),
    "it": (
        "Attivazione personale di una competenza",
        "Modifica solo la sua attivazione personale. Non esegue la competenza; impostazioni globali e altri account restano invariati.",
    ),
    "zh-CN": (
        "个人技能启用状态",
        "仅修改您的个人启用状态。不执行技能；全局设置和其他账户不受影响。",
    ),
}
