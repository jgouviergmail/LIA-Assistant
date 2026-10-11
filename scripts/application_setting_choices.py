"""Generate backend display vocabulary from the UI translations; --check is a guard.

Only reviewed option keys are projected. Provider-specific options remain owned
by their runtime metadata endpoints, never inferred from translation text.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "apps/api/src/domains/agents/application/setting_choices.json"
PATHS = {
    "language": "native-language-name",
    "color_theme": "settings.theme.themes.{value}.label",
    "theme": "settings.theme.{value}",
    "font_family": "settings.font.fonts.{value}.label",
    "exchange_rhythm": "settings.usage_preferences.exchange_rhythm.options.{value}.label",
    "execution_mode": "workboard.execution_mode.{value}",
    "voice_stt_mode": "settings.voice_mode.stt_mode_{value}",
    "response_display_mode": "settings.preferences.display_mode.modes.{value}.label",
}


def render() -> str:
    import sys

    sys.path.insert(0, str(ROOT / "apps/api"))
    from src.core.i18n import normalize_language
    from src.domains.agents.application.schemas import PreferencePatch
    from src.domains.auth.preference_commands import AssistantPreferencePatch

    properties = {
        **PreferencePatch.model_json_schema()["properties"],
        **AssistantPreferencePatch.model_json_schema()["properties"],
    }
    definitions = PreferencePatch.model_json_schema().get("$defs", {})
    choices = {}
    for field, path in PATHS.items():
        prop = properties[field]

        def enums(node):
            if "$ref" in node:
                return enums(definitions[node["$ref"].split("/")[-1]])
            return node.get(
                "enum",
                [value for item in node.get("anyOf", []) for value in enums(item)],
            )

        values = enums(prop)
        if not values:
            raise ValueError(f"No authoritative choices for {field}")
        translations = {}
        for language in ("fr", "en", "de", "es", "it", "zh"):
            source = json.loads(
                (ROOT / f"apps/web/locales/{language}/translation.json").read_text(encoding="utf-8")
            )
            labels = {}
            for value in values:
                if path == "native-language-name":
                    language_source = (ROOT / "apps/web/src/i18n/settings.ts").read_text(
                        encoding="utf-8"
                    )
                    native = re.search(
                        rf"\b{re.escape(value.split('-')[0])}:\s*\{{\s*native:\s*'([^']+)'",
                        language_source,
                    )
                    if native is None:
                        raise ValueError(f"Missing UI language: {value}")
                    label = native.group(1)
                else:
                    label = source
                    for key in path.format(value=value).split("."):
                        label = label[key]
                if not isinstance(label, str) or not label.strip():
                    raise ValueError(f"Missing label: {language}/{field}/{value}")
                labels[value] = label
            translations[normalize_language(language)] = labels
        choices[field] = translations
    choices["__boolean__"] = {}
    for language in ("fr", "en", "de", "es", "it", "zh"):
        source = json.loads(
            (ROOT / f"apps/web/locales/{language}/translation.json").read_text(encoding="utf-8")
        )
        choices["__boolean__"][normalize_language(language)] = {
            "true": source["common"]["yes"],
            "false": source["common"]["no"],
        }
    return json.dumps(choices, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = render()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != generated:
            raise SystemExit(
                "Setting choice vocabulary drift: run scripts/application_setting_choices.py"
            )
    else:
        TARGET.write_text(generated, encoding="utf-8", newline="\n")
