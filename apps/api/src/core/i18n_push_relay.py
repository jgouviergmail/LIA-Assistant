"""
The one sentence the wake relay is allowed to say.

The relay forwards notifications for deployments it does not belong to, so it
must never carry what they contain. It sends this fixed text instead, and the
shell fetches the real content from its own server over the user's own session
once opened.

That is the whole privacy argument for the relay's existence, and it lives or
dies on this module staying a constant. There is no parameter here, and none
should be added: the moment a caller can influence the text, the relay is
carrying content again.

Supported Languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n_types import SupportedLanguage


class PushRelayMessages:
    """The generic wake notification, in the six languages LIA speaks."""

    @staticmethod
    def wake_title(language: SupportedLanguage = "fr") -> str:
        """Title of the generic wake notification."""
        messages: dict[str, str] = {
            "fr": "LIA",
            "en": "LIA",
            "es": "LIA",
            "de": "LIA",
            "it": "LIA",
            "zh-CN": "LIA",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def wake_body(language: SupportedLanguage = "fr") -> str:
        """Body of the generic wake notification.

        Deliberately says that something is waiting without hinting at what:
        a lock screen is read by whoever is holding the phone.
        """
        messages: dict[str, str] = {
            "fr": "Vous avez du nouveau. Ouvrez pour voir.",
            "en": "You have something new. Open to see it.",
            "es": "Tienes algo nuevo. Abre para verlo.",
            "de": "Es gibt Neues für Sie. Zum Ansehen öffnen.",
            "it": "C'è qualcosa di nuovo per te. Apri per vederlo.",
            "zh-CN": "您有新消息，打开查看。",
        }
        return messages.get(language, messages["en"])
