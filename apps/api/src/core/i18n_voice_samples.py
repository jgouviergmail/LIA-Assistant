"""The bounded sentence heard when choosing a TTS voice in settings."""

from src.core.i18n import resolve_language

VOICE_SAMPLE_PHRASES: dict[str, str] = {
    "fr": "Bonjour, ceci est un échantillon de ma voix !",
    "en": "Hello, this is a sample of my voice!",
    "de": "Hallo, dies ist eine Hörprobe meiner Stimme!",
    "es": "¡Hola, esta es una muestra de mi voz!",
    "it": "Ciao, questo è un esempio della mia voce!",
    "zh-CN": "你好，这是我的声音示例！",
}


def voice_sample_phrase(language: str) -> str:
    """The fixed sample sentence in the account's language."""
    return VOICE_SAMPLE_PHRASES[resolve_language(language)]
