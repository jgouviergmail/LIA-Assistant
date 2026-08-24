"""Download, filter and vendor the public model-capability snapshot.

Two upstream registries, both fetched by hand (never at runtime):

- ``BerriAI/litellm`` ``model_prices_and_context_window.json`` — MIT (the file
  sits at the repository root, outside ``enterprise/``).
- ``models.dev`` ``api.json``.

Only capability fields are kept, and only for the providers LIA can serve.
Prices, reasoning metadata, streaming and the sampling flags are dropped on
purpose — see the design spec, sections 0 ter and 0 quinquies.

Usage:
    task llm:catalogue:fetch    # from the repository root
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
MODELSDEV_URL = "https://models.dev/api.json"

OUT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "infrastructure"
    / "llm"
    / "catalogue"
    / "snapshot.json"
)

#: LiteLLM ``litellm_provider`` values LIA can serve.
LITELLM_PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "gemini",
    "vertex_ai-language-models",
    "dashscope",
    "perplexity",
    "ollama",
    "elevenlabs",
}
#: models.dev top-level provider ids LIA can serve (canonical vendors only).
MODELSDEV_PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "google",
    "google-vertex",
    "alibaba",
    "alibaba-cn",
    "perplexity",
    "ollama",
}

LITELLM_KEEP = {
    "litellm_provider",
    "mode",
    "max_input_tokens",
    # ``max_tokens`` is deliberately NOT kept: over the 512 entries it either
    # duplicates ``max_output_tokens`` (361) or duplicates ``max_input_tokens``
    # (the 22 entries where it is the only one present -- Gemini embeddings and
    # the veo family). Measured 2026-08-24: zero entries where it carries an
    # output cap nothing else does.
    "max_output_tokens",
    "supports_function_calling",
    "supports_response_schema",
    "supports_vision",
    "deprecation_date",
}
MODELSDEV_KEEP = {"limit", "tool_call", "structured_output", "attachment", "status"}


#: models.dev answers 403 to a request without a User-Agent (measured
#: 2026-08-24: plain -> 403, with a User-Agent -> 200). Identify honestly.
USER_AGENT = "lia-catalogue-fetch/1.0 (+https://github.com/jgouviergmail/LIA)"


def _fetch(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _filter_litellm(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict) or value.get("litellm_provider") not in LITELLM_PROVIDERS:
            continue
        out[key] = {k: v for k, v in value.items() if k in LITELLM_KEEP}
    return out


def _filter_modelsdev(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for provider_id, provider in raw.items():
        if provider_id not in MODELSDEV_PROVIDERS:
            continue
        for model_id, model in provider.get("models", {}).items():
            kept = {k: v for k, v in model.items() if k in MODELSDEV_KEEP}
            kept["provider"] = provider_id
            out[f"{provider_id}/{model_id}"] = kept
    return out


def main() -> None:
    """Fetch both registries, filter them and write the vendored snapshot."""
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "litellm": _filter_litellm(_fetch(LITELLM_URL)),
        "modelsdev": _filter_modelsdev(_fetch(MODELSDEV_URL)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUT} - litellm={len(snapshot['litellm'])} modelsdev={len(snapshot['modelsdev'])}"
    )


if __name__ == "__main__":
    main()
