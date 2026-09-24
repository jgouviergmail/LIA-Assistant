# ADR-305 — An image model declares its offer; one provider client serves it

**Status**: accepted — 2026-09-23
**Amends**: ADR-184 (a constraint the system enforces is published to whoever produces the value), ADR-272 (every euro the platform pays is counted), ADR-279 (generated files), ADR-063 (one exchange rate reaches every worker)

## Context

Image generation was written for one vendor and kept the vendor's vocabulary as the
application's. Adding Qwen Image 3.0 (`qwen-image-3.0-pro`, `qwen-image-3.0`) exposed
every place where OpenAI had become an assumption:

1. **One global vocabulary.** `IMAGE_GENERATION_VALID_QUALITIES = ("low", "medium",
   "high")` and three fixed sizes validated the tool's inputs, the person's preferences
   and the resize templates, whatever model the administrator had configured. Qwen
   offers ONE quality and sizes anywhere in an area envelope; its billing depends on
   the output area (1K ≤ 2,250,000 px < 2K), not on a quality.
2. **The OpenAI edit did not run the configured model.** It went through the Responses
   API with an `image_generation` tool whose model was never set — the SDK documents
   the default as `gpt-image-1`, retiring on 2026-10-23 — while the cost was recorded
   against the configured model (`gpt-image-2`). The same call spent tokens on a TEXT
   model (`IMAGE_EDIT_RESPONSES_MODEL = "gpt-4.1-mini"`) that nobody recorded.
3. **What was offered was not what could run.** The image slot's admin list merged the
   catalogue's `kind = image` rows (Gemini image models, `chatgpt-image-latest`) with
   the priced models; only an OpenAI client existed, so a Gemini choice failed at the
   first generation. Pricing rows for any model were accepted and offered to the person.
4. **Input images were free.** Qwen bills every reference image of an edit
   (0.00275 USD at the output's tier); nothing could express it.
5. **Two exchange rates.** The image pricing service fetched its own USD→EUR rate from
   an external API at load, where every other cost reads the pricing cache's rate —
   published cross-worker since ADR-063's amendment of 2026-09-23.

## Decision

### (1) A family declares what a model accepts and how it is billed

`domains/image_generation/families.py` holds ordered `(ImageFamily, model prefixes)`
rules — the reasoning-profile shape (ADR-245), first match on the family's provider and
a prefix wins; a rule cannot pair one vendor's model names with another vendor's family:

| | OpenAI GPT Image | Qwen Image 3.0 |
|---|---|---|
| Qualities | `low`, `medium`, `high` | `standard` |
| Sizes | the three sizes OpenAI prices per image | any `WxH` with area 512²–2048² and aspect ≤ 8:1 |
| Billing tier | none | 1K when area ≤ 2,250,000 px, else 2K |
| Reference image of an edit | billed as tokens by OpenAI — not expressible per image | billed per image at the output's tier |
| Source image sent to an edit | fitted within the output size (its tokens grow with its area) | fitted within 2048 px and 10 MB of FILE (the model's documented input ceiling; measured: the base64 form may exceed it) |

**A model no family declares is not servable**, and every surface reads that one
answer: its pricing rows are refused on write, it is not offered to the person, it is
not listed for the image slot, and the LLM configuration refuses it
(`image_model_not_served`). The image slot's list is the image domain's alone — the
catalogue's `kind = image` rows no longer offer a model no client serves — and the
slot's provider must be the model's own (`image_model_provider_mismatch`): the tools run
a model on its provider, so another name on the admin card would name a vendor nobody
bills.

### (2) One client per provider, and the registry is complete by construction

`domains/image_generation/providers/` holds the contract (`base.py`) and one module per
vendor. A client returns ONE image as PNG bytes. `client.py` keeps the registry and the
factory; importing it verifies that every family's provider has a client and that
every client serves a family — a family without its client would be a model offered
nowhere, in silence (ADR-085), so a declared family IS a servable one and
`resolve_image_family` is the one question every surface asks. Both vendors speak the
OpenAI wire, so both clients get their SDK client from `providers/openai_sdk.py`: the
key and base URL resolve exactly as the chat factory's (`_require_api_key`,
`_get_base_url` — the Admin UI key, else the environment, and `QWEN_BASE_URL` for the
workspace host), the timeout is the image step's ceiling, and the SDK's failures are
translated there.

**A failure leaves a client as the contract's error, carrying its facts.**
`ImageGenerationError` holds the vendor's HTTP status, its error code and whether it
timed out; `ImageProviderNotConfiguredError` says a key is missing; no SDK exception
reaches a tool. The tool classifies those facts through the taxonomy every tool shares
(`http_status_to_error_code`, ADR-303) — a throttled call reads `RATE_LIMIT_EXCEEDED`,
a refused prompt `INVALID_INPUT`, a missing key `CONFIGURATION_ERROR` — where every
failure used to read `TOOL_ERROR`, a code outside the taxonomy that the honesty
directive can only quote. Anything else is a defect of ours: `INTERNAL_ERROR`, its
message kept out of the model's context.

- **OpenAI** generates with `images.generate` and edits with `images.edit`, both on the
  configured model. The Responses detour and `IMAGE_EDIT_RESPONSES_MODEL` are deleted:
  the model that runs is the model that is priced, and no hidden text model spends.
- **Qwen** uses the OpenAI-compatible endpoint of the workspace host for both text to
  image and image to image (`image` as a data URI in `extra_body`; `watermark` sent
  explicitly false). The result is a URL valid 24 hours, downloaded at once under an
  allowlist: https, a vendor host, no redirect, a bounded body, a total deadline and a
  PNG signature. The vendor's own billing tier (`usage.output_image_type`) is compared
  with ours and a disagreement is logged — the day the vendor moves its threshold, the
  log says so before the invoices do.

### (3) The cost counts the reference images, in the one exchange rate

`image_generation_pricing.cost_per_input_image_usd` (nullable) prices a reference
image at the row's key; the write path REQUIRES it for a family that bills reference
images per image and REFUSES it for one that does not. `ImageGenerationRecord` carries
`input_image_count`; the cost is `output × images + input × reference images`. The rate
is `get_cached_usd_eur_rate()` — the same figure every token, voice and live cost
reads — and the image pricing service no longer calls a currency API.

**An image the vendor billed is counted even when it never arrives.** A Qwen answer
carrying a URL means the image exists and is billed; if the download then fails, the
client raises `ImageDeliveryError` and the tool records the cost before returning the
failure (found by the cold review: the first version dropped that euro).

### (4) A preference is an intent the runtime maps onto the configured model

The person's stored quality and size survive a model change, so they are validated for
their SHAPE (a quality token, a `WxH` size) and mapped at run time by one resolver
(`image_generation/preferences.py`): a quality the model does not offer becomes the
cheapest it offers; a size it does not offer becomes the offered size of the same
orientation with the nearest area; an edit keeps the source's aspect ratio within the
preferred billing tier. `GET /image-generation/options` publishes the person's
EFFECTIVE quality and size, computed by that resolver, so the settings show what the
next image will use. A size's label is derived from its orientation, and the family's
tier is published beside it.

**The output format is applied — it used to be stored and read by nothing.** Every
client returns a PNG (the contract); `image_generation/encoding.py` writes it in the
format the person chose before it is stored, once for every vendor: PNG kept byte for
byte, JPEG flattened onto white, WebP keeping its transparency, lossy formats at
`IMAGE_GENERATION_ENCODING_QUALITY` (the setting an edit's source is re-encoded with).
Asking each vendor instead would be one path per vendor, and Qwen answers with a PNG
URL whatever it is asked. A conversion that fails delivers the PNG: the image is billed
already. Measured in the dev container on a real 1024×1024 image: 826 KiB as PNG,
58 KiB as JPEG (19 ms), 19 KiB as WebP (135 ms).

### (5) Qwen reaches every deployment by migration

The reference seed carries the twelve Qwen rows (two models × six sizes: 1K and 2K,
square, landscape 3:2 and portrait 2:3; the 1K sizes are OpenAI's own, so a stored
preference stays valid across the switch) and the two catalogue rows. Production does
not replay seeds, so migration `a9d3f1c7e5b2` mirrors them, guarded equal to the seed —
and the guard also holds EVERY seeded price, OpenAI's included, to its family's rules.
Its downgrade leaves nothing the previous revision cannot read: the Qwen rows are
deactivated, an image slot set on a Qwen model returns to its default (a chat slot on
Qwen is untouched), and a stored preference outside OpenAI's vocabulary is mapped into
it (the cheapest quality, the 1K size of the same orientation), since the previous
revision refuses to generate otherwise. The PostgreSQL test of the insert found a
statement binding one named parameter twice — in a select list and in a comparison —
which asyncpg refuses as two deduced types: every parameter is now bound once, typed.

### Measured

On Docker dev, against the real vendors (2026-09-23): Qwen `qwen-image-3.0` generated
a 1024×1024 PNG in 52 s and edited into a 1536×1024 PNG in 30 s, the vendor's billed
tier matching ours; OpenAI `gpt-image-2` generated in 13 s and edited through
`images.edit` in 9 s. Through the tools, a Qwen edit recorded 0.027504 USD —
0.024754 for the image plus 0.00275 for its reference image.

After the cold review, on the refactored clients: OpenAI generated through the shared
SDK builder in 13 s; a Qwen request below the size envelope came back as
`ImageGenerationError` (status 400, `InvalidParameter`) and the tool classified it
`INVALID_INPUT`, unbilled; and a Qwen edit whose PNG source weighed 9.01 MiB — 12.02 MiB
in base64 — was accepted (1536×1024 in 56 s), so the documented 10 MB is the FILE's
size and the family's byte limit reads it right.

## Stated limits

- **OpenAI's reference image and prompt are billed as tokens.** The Images API reports
  them (`usage.input_tokens_details`); the per-image table prices the output only, as
  before. Token-exact OpenAI accounting needs per-token rates this table does not hold.
- `gpt-image-2` accepts arbitrary sizes; the OpenAI family keeps the three sizes whose
  per-image price OpenAI publishes.
- Qwen's prompt rewriting and thinking keep the vendor's defaults (on): better images,
  slower answers.
- One image per call, one reference image per edit — the tools' shape, not the
  vendors'.

## Rejected

- **A per-model hard-coded size list for Qwen.** The family declares the envelope the
  vendor documents; the offered sizes are the priced rows, which the administrator owns.
- **Rejecting an unoffered preference on PATCH.** The offer changes with the
  administrator's model; a stored intent that stops being offered is mapped, never lost.
- **Following the vendor's redirect or fetching any https URL.** The result URL is the
  one server-side fetch the vendor directs; it is held to the vendor's hosts.
