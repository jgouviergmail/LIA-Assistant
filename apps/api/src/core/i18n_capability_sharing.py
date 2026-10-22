"""Recipient text for explicit capability transfers; six canonical locales."""

from src.core.i18n import normalize_language

#: What the recipient's chat says when a transfer lands: who shared it, which
#: kind of capability, and its title — then that the copy arrived disabled.
#: One whole sentence per kind, because the kind's grammatical gender agrees
#: with the rest of the sentence in several languages.
_BODIES: dict[str, dict[str, str]] = {
    "skill": {
        "fr": "{sender} t’a partagé la compétence « {name} ». Les composants reçus sont désactivés. Consulte leur état et configure-les dans les paramètres.",
        "en": "{sender} shared the skill “{name}” with you. Received components are disabled. Review their status and configure them in settings.",
        "es": "{sender} ha compartido contigo la competencia «{name}». Los componentes recibidos están desactivados. Revisa su estado y configúralos en los ajustes.",
        "de": "{sender} hat die Kompetenz „{name}“ mit dir geteilt. Empfangene Komponenten sind deaktiviert. Prüfe ihren Status und konfiguriere sie in den Einstellungen.",
        "it": "{sender} ha condiviso con te la competenza «{name}». I componenti ricevuti sono disattivati. Controlla il loro stato e configurali nelle impostazioni.",
        "zh-CN": "{sender} 与你分享了技能“{name}”。接收的组件已停用。请在设置中查看状态并进行配置。",
    },
    "mcp": {
        "fr": "{sender} t’a partagé le serveur MCP « {name} ». Les composants reçus sont désactivés. Consulte leur état et configure-les dans les paramètres.",
        "en": "{sender} shared the MCP server “{name}” with you. Received components are disabled. Review their status and configure them in settings.",
        "es": "{sender} ha compartido contigo el servidor MCP «{name}». Los componentes recibidos están desactivados. Revisa su estado y configúralos en los ajustes.",
        "de": "{sender} hat den MCP-Server „{name}“ mit dir geteilt. Empfangene Komponenten sind deaktiviert. Prüfe ihren Status und konfiguriere sie in den Einstellungen.",
        "it": "{sender} ha condiviso con te il server MCP «{name}». I componenti ricevuti sono disattivati. Controlla il loro stato e configurali nelle impostazioni.",
        "zh-CN": "{sender} 与你分享了 MCP 服务器“{name}”。接收的组件已停用。请在设置中查看状态并进行配置。",
    },
    "plugin": {
        "fr": "{sender} t’a partagé le plugin « {name} ». Les composants reçus sont désactivés. Consulte leur état et configure-les dans les paramètres.",
        "en": "{sender} shared the plugin “{name}” with you. Received components are disabled. Review their status and configure them in settings.",
        "es": "{sender} ha compartido contigo el plugin «{name}». Los componentes recibidos están desactivados. Revisa su estado y configúralos en los ajustes.",
        "de": "{sender} hat das Plugin „{name}“ mit dir geteilt. Empfangene Komponenten sind deaktiviert. Prüfe ihren Status und konfiguriere sie in den Einstellungen.",
        "it": "{sender} ha condiviso con te il plugin «{name}». I componenti ricevuti sono disattivati. Controlla il loro stato e configurali nelle impostazioni.",
        "zh-CN": "{sender} 与你分享了插件“{name}”。接收的组件已停用。请在设置中查看状态并进行配置。",
    },
}

#: The sender once their account is gone: the sentence still says someone did.
_UNKNOWN_SENDERS: dict[str, str] = {
    "fr": "Un utilisateur",
    "en": "A user",
    "es": "Un usuario",
    "de": "Ein Benutzer",
    "it": "Un utente",
    "zh-CN": "一位用户",
}


def capability_shared_body(kind: str, name: str, sender: str | None, language: str) -> str:
    """The recipient's chat line for a landed transfer.

    Args:
        kind: The capability kind (``skill``, ``mcp`` or ``plugin``).
        name: Its title, already made literal for the chat.
        sender: The sender's display name, already made literal, or None when
            their account is gone.
        language: The recipient's language.

    Returns:
        The localized sentence naming who shared which capability.

    Raises:
        KeyError: For a kind the transfer table cannot hold.
    """
    code = normalize_language(language)
    return _BODIES[kind][code].format(sender=sender or _UNKNOWN_SENDERS[code], name=name)
