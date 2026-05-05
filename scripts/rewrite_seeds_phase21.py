"""One-shot helper: rewrite the Phase 1+ seed files for the v1.x release.

- Transforms ``infrastructure/database/seeds/llm_pricing_seed.sql`` to
  insert into ``llm_models`` (catalogue + capabilities) THEN into
  ``llm_model_pricing`` with a FK lookup. The old single-INSERT block
  referenced columns dropped by migration #3 (``model_name`` is gone
  from llm_model_pricing) and the wrong UNIQUE target.

- Transforms ``infrastructure/database/seeds/image_generation_pricing_seed.sql``
  to add a ``provider`` value (always ``openai`` today since
  IMAGE_GENERATION_MODELS only contained OpenAI models) to every row.
  The column became NOT NULL in migration #3.

Idempotent — re-running it is safe; the resulting file is identical.
Safe to delete after Task 21 is committed.
"""

import re
from pathlib import Path

# --- 1) llm_pricing_seed.sql ---

SRC = Path("infrastructure/database/seeds/llm_pricing_seed.sql")
content = SRC.read_text(encoding="utf-8")

# Each pricing row in the legacy seed:
#   (gen_random_uuid(), 'model_name', input, cached|NULL, output, 'date', true, NOW(), NOW()),
ROW_RE = re.compile(
    r"\(gen_random_uuid\(\),\s*'([^']+)',\s*"
    r"([0-9.]+),\s*"
    r"(NULL|[0-9.]+),\s*"
    r"([0-9.]+),\s*"
    r"'([^']+)',\s*"
    r"(true|false),\s*"
    r"NOW\(\),\s*NOW\(\)\)"
)


def guess_provider(name: str) -> str:
    n = name.lower()
    if n.startswith(("claude-", "anthropic")):
        return "anthropic"
    if n.startswith("deepseek"):
        return "deepseek"
    if n.startswith(("sonar", "perplexity", "llama-3.1-sonar")):
        return "perplexity"
    if n.startswith(("gemini", "models/gemini")):
        return "gemini"
    if n.startswith("embedding-") or n == "text-embedding-004":
        # Google AI text-embedding-004 + embedding-001 family
        return "gemini"
    if n.startswith("qwen"):
        return "qwen"
    if n.startswith(("llama", "mistral", "phi", "mixtral", "tinyllama")):
        return "ollama"
    return "openai"


# Conservative defaults — admin can refine via the 14-field form.
DEFAULTS = dict(
    max_input_tokens=8192,
    max_output_tokens=4096,
    supports_tools=True,
    supports_structured_output=True,
    supports_strict_mode=False,
    supports_streaming=True,
    supports_vision=False,
    is_reasoning_model=False,
)

lines = content.splitlines()
# We need to drop the entire legacy INSERT block (from the comment line
# preceding "INSERT INTO llm_model_pricing" through the closing semicolon
# of the ON CONFLICT clause). ``insert_start_idx`` points at the comment
# preceding the legacy INSERT statement; ``header_end`` is the VALUES line
# (used to scan for rows).
insert_start_idx = None
header_end = None
for i, line in enumerate(lines):
    if "INSERT INTO llm_model_pricing" in line:
        # Walk back to include the preceding comment block (-- Insert ... or
        # the 117-models comment line) so the new content replaces it.
        insert_start_idx = i
        while insert_start_idx > 0 and lines[insert_start_idx - 1].strip().startswith("--"):
            insert_start_idx -= 1
        for j in range(i, min(i + 15, len(lines))):
            if "VALUES" in lines[j]:
                header_end = j
                break
        break
assert insert_start_idx is not None and header_end is not None

rows: list[dict] = []
on_conflict_idx = None
i = header_end + 1
while i < len(lines):
    stripped = lines[i].strip()
    if stripped.startswith("ON CONFLICT"):
        on_conflict_idx = i
        break
    m = ROW_RE.search(lines[i])
    if m:
        rows.append(
            dict(
                model_name=m.group(1),
                in_price=m.group(2),
                cached_price=m.group(3),
                out_price=m.group(4),
                eff_from=m.group(5),
                is_active=m.group(6),
            )
        )
    i += 1

assert on_conflict_idx is not None
on_conflict_end_idx = on_conflict_idx
while on_conflict_end_idx < len(lines):
    if ";" in lines[on_conflict_end_idx]:
        break
    on_conflict_end_idx += 1

print(f"Parsed {len(rows)} pricing rows")

# Build the new content. Header = everything before the legacy INSERT block.
header = list(lines[:insert_start_idx])
# Drop trailing blank lines so the new block follows cleanly.
while header and not header[-1].strip():
    header.pop()

new_block: list[str] = [
    "",
    f"-- Insert LLM Models catalogue (capabilities) + LLM Model Pricing ({len(rows)} models)",
    "",
]
new_block.append(
    "-- =========================================================================="
)
new_block.append(
    "-- 1) llm_models — catalogue (capabilities). One row per distinct model_name."
)
new_block.append(
    "-- Capabilities default to a conservative profile; the admin can refine them"
)
new_block.append("-- via Tarification LLM Texte (the 14-field form).")
new_block.append(
    "-- =========================================================================="
)
new_block.append("INSERT INTO llm_models (")
new_block.append("    provider,")
new_block.append("    model_name,")
new_block.append("    max_input_tokens,")
new_block.append("    max_output_tokens,")
new_block.append("    supports_tools,")
new_block.append("    supports_structured_output,")
new_block.append("    supports_strict_mode,")
new_block.append("    supports_streaming,")
new_block.append("    supports_vision,")
new_block.append("    is_reasoning_model,")
new_block.append("    is_active")
new_block.append(") VALUES")

seen: set[str] = set()
catalogue_rows: list[str] = []
for r in rows:
    if r["model_name"] in seen:
        continue
    seen.add(r["model_name"])
    provider = guess_provider(r["model_name"])
    d = DEFAULTS
    catalogue_rows.append(
        "    ('{p}', '{n}', {mi}, {mo}, {st}, {ss}, {strict}, {stream}, {sv}, {ir}, true)".format(
            p=provider,
            n=r["model_name"],
            mi=d["max_input_tokens"],
            mo=d["max_output_tokens"],
            st=str(d["supports_tools"]).lower(),
            ss=str(d["supports_structured_output"]).lower(),
            strict=str(d["supports_strict_mode"]).lower(),
            stream=str(d["supports_streaming"]).lower(),
            sv=str(d["supports_vision"]).lower(),
            ir=str(d["is_reasoning_model"]).lower(),
        )
    )
new_block.append(",\n".join(catalogue_rows))
new_block.append("ON CONFLICT (model_name) DO NOTHING;")
new_block.append("")
new_block.append(
    "-- =========================================================================="
)
new_block.append(
    "-- 2) llm_model_pricing — pricing rows. FK to llm_models via model_id."
)
new_block.append("-- Uses INSERT ... SELECT to resolve the FK from model_name.")
new_block.append(
    "-- =========================================================================="
)
new_block.append("INSERT INTO llm_model_pricing (")
new_block.append("    id,")
new_block.append("    model_id,")
new_block.append("    input_price_per_1m_tokens,")
new_block.append("    cached_input_price_per_1m_tokens,")
new_block.append("    output_price_per_1m_tokens,")
new_block.append("    effective_from,")
new_block.append("    is_active,")
new_block.append("    created_at,")
new_block.append("    updated_at")
new_block.append(")")
new_block.append(
    "SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output, "
    "p.effective_from::timestamptz, p.is_active, NOW(), NOW()"
)
new_block.append("FROM (VALUES")

pricing_value_rows: list[str] = []
for r in rows:
    cached = r["cached_price"] if r["cached_price"] != "NULL" else "NULL::numeric"
    pricing_value_rows.append(
        "    ('{n}', {i}::numeric, {c}, {o}::numeric, '{ef}', {a})".format(
            n=r["model_name"],
            i=r["in_price"],
            c=cached,
            o=r["out_price"],
            ef=r["eff_from"],
            a=r["is_active"],
        )
    )
new_block.append(",\n".join(pricing_value_rows))
new_block.append(
    ") AS p(model_name, input, cached, output, effective_from, is_active)"
)
new_block.append("JOIN llm_models m ON m.model_name = p.model_name")
new_block.append("ON CONFLICT (model_id, effective_from) DO NOTHING;")
new_block.append("")

out_lines = list(header)
out_lines += new_block
out_lines += list(lines[on_conflict_end_idx + 1 :])

out = "\n".join(out_lines)

# Update the model count check at the tail.
out = out.replace(
    "SELECT COUNT(*) INTO model_count FROM llm_model_pricing WHERE is_active = true;",
    "SELECT COUNT(*) INTO model_count FROM llm_models WHERE is_active = true;",
)
out = out.replace(
    "  - % active LLM model pricing entries",
    "  - % active LLM model catalogue entries (with pricing)",
)
old_check = (
    "    IF model_count < 117 THEN\n"
    "        RAISE WARNING 'Expected at least 117 models, but found %', model_count;\n"
    "    END IF;"
)
new_check = (
    f"    IF model_count < {len(seen)} THEN\n"
    f"        RAISE WARNING 'Expected at least {len(seen)} models, but found %', model_count;\n"
    "    END IF;"
)
out = out.replace(old_check, new_check)

SRC.write_text(out, encoding="utf-8")
print(f"OK -- rewrote {SRC} ({len(seen)} catalogue, {len(rows)} pricing rows)")


# --- 2) image_generation_pricing_seed.sql ---

IMG = Path("infrastructure/database/seeds/image_generation_pricing_seed.sql")
img = IMG.read_text(encoding="utf-8")

# Add provider to the column list
img = img.replace(
    "INSERT INTO image_generation_pricing (\n    id,\n    model,",
    "INSERT INTO image_generation_pricing (\n    id,\n    provider,\n    model,",
)

# Inject provider value into every VALUES row. Pattern matches:
#   (gen_random_uuid(), 'model', 'quality', ...)
# replacing it with:
#   (gen_random_uuid(), 'openai'::llm_provider_enum, 'model', 'quality', ...)
def _replace_value(match: re.Match) -> str:
    return "(gen_random_uuid(), 'openai'::llm_provider_enum, " + match.group(1)


img = re.sub(
    r"\(gen_random_uuid\(\),\s*('[^']+',\s*'[^']+',)",
    _replace_value,
    img,
)

IMG.write_text(img, encoding="utf-8")
print(f"OK -- patched {IMG} (provider='openai' on all rows)")
