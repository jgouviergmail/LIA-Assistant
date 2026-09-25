# ADR-315 — An image prompt may be rewritten with recognised techniques, never distorted

**Status**: accepted — 2026-09-24 (owner request: a dedicated model that understands what is asked and improves it with recognised image-prompting techniques, without distorting it — « image réaliste d'un chat » → « photo 85 mm, f/1.8, grain léger, d'un chat » — optional, turned on explicitly by the person in « AI image generation »; owner arbitration Q4: the image is sent as it is, the rewrite is not shown)
**Amends**: ADR-305 (the image tool), ADR-244 (a slot of its own), ADR-285 (a short answer without reasoning), ADR-275 (a truncated structured output is a refusal), ADR-309 (the static rules as the system message), ADR-184 (the bound the prompt states is the bound the code enforces), ADR-272 (both ceilings)

## Context

The image tool sends the planner's description as it is. Image models answer far better
to a description written the way their vendors document it, and both vendors LIA serves
publish it: OpenAI's image prompting guide (order the prompt — scene, subject, details,
constraints; say « photorealistic » and describe the shot in photographic terms; put the
text an image must carry in quotes; state exclusions such as « no watermark ») and the
prompt rewriter Qwen ships with Qwen-Image (enrich the visual details without changing
the core content, keep the text to render in quotes, no added text, stay short).

## Decision

1. **A slot of its own, `image_prompt_enhancement`** (registry, defaults, `LLMType`,
   the admin description in six languages): one short structured call, no reasoning
   where the resolved profile can switch it off (`short_answer_config`), the slot's own
   output cap. The default is a light chat model; every slot is configurable (ADR-244).
2. **A versioned prompt** (`image_prompt_enhancement_prompt`) that fixes what may not
   change — every subject, count, action, relationship, setting, named style and
   constraint, and every piece of text the image carries, verbatim in quotes, with no
   other text added — and states the techniques: the order, photographic terms for a
   realistic image, the medium and its technique for an illustration, the plainest
   style when none is named, a simple background when the setting is open, plain
   sentences with no keyword soup, parameters or image size (set elsewhere), the
   request's own language. One example, in English (owner rule). The request is data,
   never instructions. Its static part is the system message, the request the question
   (ADR-309); its one placeholder before the marker is the published bound.
3. **Deterministic checks decide whether the rewrite is sent**: an empty answer, one
   longer than `IMAGE_PROMPT_ENHANCEMENT_MAX_CHARS` (the bound the prompt states;
   default 1 200 characters, far below gpt-image's 32 000 characters and the 4 500
   tokens a Qwen Image 3.0 prompt may hold), or one that lost any text the request
   quoted — in any of the quote pairs people type — is discarded.
4. **Never a gate on the image**: a ceiling refusal (`skipped_quota`), a model failure or
   a truncated answer (`failed`), a discarded rewrite (`rejected`) all send the
   ORIGINAL prompt. The call names the account (both ceilings, ADR-272) and carries the
   turn's config (the turn's tracker bills it; `LLM_SPEND_ROADS`: TURN).
5. **Only a generation is enhanced.** An edit instruction names what to change in an
   existing image; lens and light language added to it would change what the person
   asked to keep.
6. **The person turns it on** (`users.image_generation_prompt_enhancement`, off by
   default, migration `79db1056a28e`); **the operator may withdraw it**
   (`IMAGE_PROMPT_ENHANCEMENT_ENABLED`). ONE reading of the operator's switch
   (`image_generation.preferences.prompt_enhancement_offered`) serves the tool and the
   options route, which publishes `prompt_enhancement_available` so the settings show
   the switch only where it would be honoured.
7. **What the vendor received is what is billed and audited** (the cost record's
   preview); the gallery, the card and the answer keep the person's own words (Q4).
8. **Observed**: `image_prompt_enhancement_total{outcome}` (`enhanced`, `unchanged`,
   `rejected`, `failed`, `skipped_quota`) on dashboard 05; logs carry lengths and
   outcomes, never the words.

## Consequences

- An opted-in generation costs one short extra call and a second or two.
- The image columns of `users` moved into `ImageGenerationColumns` (the model file sat
  at 588 of its 600 logical lines).
- Not measured on real models yet: the rewrite's quality across the configured slots is a
  paid measurement, to be budgeted before it runs.
