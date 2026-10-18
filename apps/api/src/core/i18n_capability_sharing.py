"""Recipient text for explicit capability transfers; six canonical locales."""

from src.core.i18n import normalize_language

_BODIES: dict[str, str] = {
    "fr": "Une ressource t’a été partagée : {name}. Les composants reçus sont désactivés. Consulte leur état et configure-les dans les paramètres.",
    "en": "A capability was shared with you: {name}. Received components are disabled. Review their status and configure them in settings.",
    "es": "Se ha compartido un recurso contigo: {name}. Los componentes recibidos están desactivados. Revisa su estado y configúralos en los ajustes.",
    "de": "Eine Erweiterung wurde mit dir geteilt: {name}. Empfangene Komponenten sind deaktiviert. Prüfe ihren Status und konfiguriere sie in den Einstellungen.",
    "it": "Una risorsa è stata condivisa con te: {name}. I componenti ricevuti sono disattivati. Controlla il loro stato e configurali nelle impostazioni.",
    "zh-CN": "有人与你分享了扩展：{name}。接收的组件已停用。请在设置中查看状态并进行配置。",
}


def capability_shared_body(name: str, language: str) -> str:
    return _BODIES[normalize_language(language)].format(name=name)
