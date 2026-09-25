# AI Image Generation (evolution)

> Architecture and integration guide for AI-powered image generation and editing.

**Phase**: evolution — AI Image Generation
**Created**: 2026-03-25
**Last Updated**: 2026-09-24 (prompt enhancement, [ADR-315](../architecture/ADR-315-Image-Prompt-Enhancement.md); sharing with a connection, [ADR-316](../architecture/ADR-316-Sharing-A-Generated-Image-With-A-Connection.md))
**Status**: Implemented

> **ADR-305**: an image model declares its offer through its **family**, and one
> provider **client** serves it. OpenAI GPT Image and Qwen Image 3.0 are served
> today. A model no family declares cannot be priced, offered, selected or run —
> and the image slot's model list comes from the image domain alone.

---

## Overview

LIA generates images from text descriptions and edits an existing image (generated
or uploaded) from an instruction. The image model is chosen by the administrator
(Configuration LLM, slot `image_generation`); the person chooses a quality and a size
among what that model offers. Images are saved as attachments on disk and displayed
as cards below the assistant response.

### Features

| Feature | Description |
|---------|-------------|
| Several vendors | OpenAI GPT Image (`gpt-image-*`) and Qwen Image 3.0 (`qwen-image-3.0`, `qwen-image-3.0-pro`), each through its own client |
| Families | What a model accepts (qualities, sizes, billing tiers, reference images) is declared once in `families.py` and read by every surface |
| User preferences | Quality and size among what the configured model offers (a stored preference survives a model change and is mapped onto the new offer), and the output format every image is delivered in |
| Admin LLM Config | Model selection via the admin UI; only servable image models are listed, and an unserved one is refused on write |
| Admin Pricing | Full CRUD on `image_generation_pricing`; every row is validated against its family (quality, size, reference-image price) |
| Cost tracking | Output images per (quality, size), plus the reference image of an edit where the vendor bills it per image, in the one exchange rate |
| Attachment storage | Disk + DB with TTL-based cleanup via the attachment system |
| Usage limits | Image costs included in per-user usage limit enforcement |
| Prompt enhancement | Optional rewrite of a generation prompt with recognised techniques, the person's opt-in (ADR-315) |
| Sharing | A generated image shared with a connection lands, as a copy, in their gallery and their chat (ADR-316) |

---

## Architecture

### Families and clients

```
image_generation/
├── families.py          ImageFamily per (provider, model prefixes): qualities,
│                        sizes (FixedSizes | AreaEnvelope), billing tiers,
│                        reference-image billing, source limits
├── sizing.py            WIDTHxHEIGHT arithmetic: orientation, nearest size
├── preferences.py       the configured model's offer, and the person's
│                        preferences mapped onto it (the ONE resolver)
├── options_cache.py     what each SERVABLE model offers (a family, and the
│                        active pricing rows it accepts)
├── pricing_service.py   what one call costs (output + reference images)
├── resize.py            an edit's source: EXIF orientation, family box, byte limit
├── encoding.py          flattening and encoding, and the person's output format
│                        (the vendor's PNG converted once, for every vendor)
├── client.py            provider → client registry, completeness checked at import
└── providers/
    ├── base.py          ImageGenerationClient, ImageResult (PNG bytes), SourceImage,
    │                    the failure contract (ImageGenerationError and its facts)
    ├── openai_sdk.py    the SDK client both vendors share (key, base URL, timeout)
    │                    and the translation of its failures into the contract
    ├── openai_images.py images.generate / images.edit on the configured model
    ├── qwen_images.py   the workspace's OpenAI-compatible /images/generations
    └── result_download.py  a vendor result URL, held to the vendor's hosts
```

| | OpenAI GPT Image | Qwen Image 3.0 |
|---|---|---|
| Qualities | `low`, `medium`, `high` | `standard` |
| Sizes | 1024x1024, 1536x1024, 1024x1536 | any `WxH`, area 512²–2048², aspect ≤ 8:1 |
| Billing tier | none | 1K when area ≤ 2,250,000 px, else 2K |
| Reference image of an edit | billed as tokens by OpenAI (not priced per image) | billed per image at the output's tier |
| Source sent to an edit | fitted within the output size | fitted within 2048 px and 10 MB of file (a larger base64 form is accepted — measured) |
| Transport | base64 in the answer | a URL valid 24 hours, downloaded at once |

The registry refuses to import when a family's provider has no client or a client
serves no family; `run_failfast_validations()` converts that into a refused boot. A
declared family is therefore a servable one: `resolve_image_family` is the one
question every surface asks.

### Data Flow

```
User: "Generate an image of an astronaut cat"
  |
Router → domain: image_generation, tool: generate_image
  |
Planner → ExecutionPlan with 1 TOOL step
  |
Task Orchestrator → parallel_executor invokes generate_image
  |
  ├─ 1. Caller: user id, the person's stored quality and size
  ├─ 2. active_image_options(): the configured model's offer (or the reason it
  │     is not served)
  ├─ 3. effective_quality / effective_size: the preferences mapped onto the offer
  ├─ 4. create_image_client(provider).generate(...) → PNG bytes
  ├─ 5. track_image_generation_call() → cost in TrackingContext
  ├─ 6. encode_for_delivery(): the PNG in the person's format (png, jpeg, webp),
  │     then saved as an Attachment (disk + DB, TTL cleanup)
  ├─ 7. store_pending_image(conversation_id, url, alt)
  └─ 8. Return UnifiedToolOutput.action_success()
  |
Response Node → the model answers (it knows the image was generated)
  |
SSE Streaming → done chunk includes generated_images: [{url, alt, expires_at}]
```

### Edit Image Flow

```
User: "Make this image look like night"
  |
edit_image (source_attachment_id optional)
  |
  ├─ 1. Caller and the configured model's offer (as above)
  ├─ 2. Source: the named attachment, else the person's latest image
  ├─ 3. read_oriented_size(): the source's size as displayed (EXIF applied)
  ├─ 4. edit_size(): the offered size nearest to the source's proportions,
  │     within the billing tier of the person's preferred size
  ├─ 5. prepare_source_image(): oriented, fitted within family.source_box(),
  │     PNG (JPEG when the PNG exceeds the vendor's byte limit)
  ├─ 6. client.edit(prompt, source, model, quality, size) → PNG bytes
  ├─ 7. track_image_generation_call(input_image_count=1)
  └─ 8. Save, queue the card, return
```

### Key Design Decisions

1. **The model that runs is the model that is priced.** OpenAI edits go through
   `images.edit` on the configured model. The former Responses-API detour ran the
   tool's own default model (`gpt-image-1`) and a text model whose tokens nobody
   recorded (ADR-305).

2. **A preference is an intent.** The person's stored quality and size are
   validated for their shape only (a short token, `WIDTHxHEIGHT`) and mapped at run
   time: a quality the model does not offer becomes the cheapest it offers; a size
   becomes the offered one of the same orientation with the nearest area.
   `GET /image-generation/options` publishes the EFFECTIVE values so the settings
   show what the next image will use.

3. **A vendor URL is held to the vendor.** Qwen answers with a URL valid 24 hours;
   it is downloaded at once over https, from the vendor's hosts only, without
   following a redirect, under a size ceiling and a total deadline, and must be a
   PNG. The URL (a signed token) is never logged. A download that fails after the
   vendor answered is an `ImageDeliveryError`: the image was billed, so its cost is
   recorded even though no card is shown.

4. **A failure is classified by its facts.** A client translates its vendor's
   failures into `ImageGenerationError`, carrying the HTTP status, the vendor's code
   and whether it timed out (`ImageProviderNotConfiguredError` for a missing key);
   the tool maps those facts through the taxonomy every tool shares
   (`http_status_to_error_code`, ADR-303): 429 → `RATE_LIMIT_EXCEEDED`, a refused
   prompt → `INVALID_INPUT`, a missing key → `CONFIGURATION_ERROR`. An exception no
   client translated is a defect: `INTERNAL_ERROR`, its message never handed to the
   model.

5. **The person's format is applied once, for every vendor.** Every client returns
   a PNG; `encode_for_delivery` writes it in the format the person chose before it
   is stored — PNG kept byte for byte, JPEG flattened onto white (no alpha channel),
   WebP keeping its transparency, lossy formats at `IMAGE_GENERATION_ENCODING_QUALITY`.
   Asking each vendor instead would be one path per vendor, and Qwen answers with a
   PNG URL whatever it is asked. The image is already billed when it is converted,
   so a conversion that fails delivers the PNG. Measured on a real 1024×1024 image:
   826 KiB as PNG, 58 KiB as JPEG (19 ms), 19 KiB as WebP (135 ms).

6. **Attachment-based storage** (not inline base64): images are saved to disk and
   served via `/api/v1/attachments/{id}`, keeping multi-MB data out of the LLM
   context and the SSE stream.

7. **Done metadata delivery** (not markdown injection): image URLs travel in the
   `done` chunk metadata and the frontend renders dedicated cards.

8. **Module-level dict** (not ContextVar): `_pending_images` in `image_store.py` is
   keyed by `conversation_id`, because LangGraph runs tools in separate tasks whose
   ContextVar writes the streaming coroutine cannot see.

9. **UnifiedToolOutput** (not plain str): `action_success()` lets the adaptive
   replanner recognise a successful action rather than an empty result.

---

## File Structure

| File | Description |
|------|-------------|
| `src/core/config/image_generation.py` | Settings (feature flag, rate limit, timeouts, result download) |
| `src/domains/image_generation/families.py` | Image families and their resolution |
| `src/domains/image_generation/sizing.py` | Size arithmetic shared by every family |
| `src/domains/image_generation/preferences.py` | Configured model's offer + preference resolution |
| `src/domains/image_generation/providers/` | Contract and one client per vendor |
| `src/domains/image_generation/client.py` | Registry, factory, completeness check |
| `src/domains/image_generation/options_cache.py` | `ImageOptionsCache`: servable models only |
| `src/domains/image_generation/options_router.py` | `GET /api/v1/image-generation/options` |
| `src/domains/image_generation/pricing_service.py` | Cost of a call |
| `src/domains/image_generation/resize.py` | Edit source preparation |
| `src/domains/image_generation/encoding.py` | Flattening, encoding, the person's output format |
| `src/domains/image_generation/router.py` | Admin CRUD (`/admin/image-pricing/pricing`), family-validated |
| `src/domains/image_generation/tracker.py` | TrackingContext helper |
| `src/domains/image_generation/image_store.py` | Pending images for SSE delivery |
| `src/domains/agents/tools/image_generation_tools.py` | `generate_image` + `edit_image` |
| `src/domains/agents/image_generation/catalogue_manifests.py` | Agent + tool manifests |
| `src/domains/agents/image_generation/prompt_enhancement.py` | Optional prompt rewrite before the vendor call (ADR-315) |
| `src/domains/peers/image_share.py` | Sharing a generated image with a connection (ADR-316) |
| `apps/web/src/components/peers/ShareImageDialog.tsx` | The share dialog (chat card and gallery) |
| `apps/web/src/components/settings/ImageGenerationSettings.tsx` | User settings UI |
| `apps/web/src/components/settings/AdminImagePricingSection.tsx` | Admin pricing UI |

---

## Expiry surfaced to the client (N2)

A generated image is an `Attachment` with `expires_at = now + attachments_ttl_hours`,
and the cleanup scheduler deletes expired attachments every 6 hours —
`list_expired` does not spare non-orphans, so a generated image really is purged.
Until N2 the frontend was never told: the image simply vanished from the history.

`PendingImage` now carries `expires_at` (ISO-8601 string, `None` when unknown),
and `to_wire_metadata()` serializes the list for **both** emission paths — the
SSE `done` chunk and the archived `message_metadata` row. One serializer rather
than two hand-written dict literals: the reloaded card must be the live one.

On the client, `classifyImageExpiry()` is a pure function returning
`unknown | expired | soon | later`. The deadline always comes from the backend —
the TTL is configurable, so a "24 h" written into the UI would eventually lie —
and a message with no `expires_at` (history predating the feature) renders
nothing rather than guessing.

## Where a generated image lives afterwards (ADR-279)

Every image the tool produces is stored as an `Attachment` stamped
`origin = generated_image`, with the prompt-derived `title` and the
`conversation_id` it was produced in.

Two consequences the chat card does not show:

- **it survives a conversation reset** — the reset removes what the person
  uploaded (`origins={upload}`) and nothing else;
- **it is listed, searchable and downloadable** from Settings →
  « My generated files », whose image gallery reads
  `GET /generated-assets?family=images`.

The TTL still applies: the expiry is written on each card, and the gallery makes
it visible rather than pushing it back.

## Prompt enhancement (ADR-315)

An opt-in of the person (`image_generation_prompt_enhancement`, off by default) that the
operator can withdraw (`IMAGE_PROMPT_ENHANCEMENT_ENABLED`). When both allow it,
`generate_image` hands its prompt to `agents/image_generation/prompt_enhancement.py`
before the vendor call:

- **one short structured call** on the slot `image_prompt_enhancement`, no reasoning
  where the resolved profile can switch it off, the account named (both ceilings) and
  the turn's config passed (the turn's tracker bills it);
- **the versioned prompt** `image_prompt_enhancement_prompt` fixes what may not change
  (subjects, count, actions, setting, named style, constraints, the text the image
  carries, verbatim in quotes, and no text added) and states the techniques the two
  vendors document (OpenAI's image prompting guide, the rewriter Qwen ships with
  Qwen-Image); its static part is the system message, the request the question;
- **deterministic checks** decide whether the rewrite is sent: empty, longer than
  `IMAGE_PROMPT_ENHANCEMENT_MAX_CHARS` (the bound the prompt states), or a quoted text
  lost → the ORIGINAL prompt goes;
- **never a gate on the image**: a ceiling refusal, a failure or a truncated answer
  sends the original prompt too.

Only a generation is enhanced — an edit instruction names what to change, and lens or
light language added to it would change what the person asked to keep. What the vendor
received is what the cost record's preview holds; the gallery, the card and the answer
keep the person's words. `image_prompt_enhancement_total{outcome}` counts every outcome
(dashboard 05). The settings show the switch only when `GET /image-generation/options`
publishes `prompt_enhancement_available`, read from the same predicate as the tool
(`preferences.prompt_enhancement_offered`).

## Sharing an image with a connection (ADR-316)

« Share with a connection » sits on every generated image card of the chat and of the
gallery (where connections are offered and the image has not expired). The dialog lists
the accepted connections and takes an optional comment; its button is the
confirmation. `POST /peers/connections/{connection_id}/images`
(`domains/peers/image_share.py`):

- shares only the sender's own, live, generated image on an accepted, unblocked
  connection, under two daily quotas serialised per sender by an advisory lock;
- copies the file under the recipient's folder and writes their gallery row — origin
  `generated_image`, a lifetime from reception, the sender's title, `shared_by_name` —
  and the `peer_image_shares` ledger row in one transaction;
- then shows the image in the recipient's chat (`proactive_peer_image`, the same card
  as a generated image, the comment as a literal quote), best-effort and on a session
  of its own.

`peers_image_shares_total{outcome}` counts the outcomes (dashboard 09).

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `IMAGE_GENERATION_ENABLED` | Global feature flag |
| `IMAGE_GENERATION_MAX_IMAGES_PER_REQUEST` | Max images per tool call |
| `IMAGE_GENERATION_RATE_LIMIT_CALLS` | Max tool calls per user per window (`generate_image` and `edit_image` tracked separately) |
| `IMAGE_GENERATION_RATE_LIMIT_WINDOW` | Rate limit window in seconds |
| `IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS` / `MAX_IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS` | Floor and ceiling of an image tool step; the ceiling is also each client's HTTP timeout |
| `IMAGE_GENERATION_RESULT_DOWNLOAD_TIMEOUT_SECONDS` | Total deadline to download an image a vendor returned as a URL |
| `IMAGE_GENERATION_RESULT_MAX_MB` | Largest image downloaded from a vendor result URL |
| `IMAGE_GENERATION_ENCODING_QUALITY` | JPEG/WebP quality of an image delivered in the person's format, and of an edit's source re-encoded to fit its vendor |
| `IMAGE_PROMPT_ENHANCEMENT_ENABLED` | Offer the prompt enhancement at all (ADR-315); false = never offered, never rewritten |
| `IMAGE_PROMPT_ENHANCEMENT_MAX_CHARS` | Longest enhanced prompt kept; a longer rewrite is discarded for the original |
| `QWEN_BASE_URL` | Qwen's OpenAI-compatible base URL — the workspace host of the region whose price grid is seeded |

Defaults and bounds live in `src/core/config/image_generation.py` and `.env.example`.

Both tools carry the standard `@track_tool_metrics` + `@rate_limit` decorators (per-user
sliding window). The rate limit is a technical anti-runaway ceiling for a paid external
API; it complements the usage-limits cost caps, which are per billing cycle and
Redis-cached (a burst could overshoot them before they bite). When the limit is
exceeded, the tool returns the standard `rate_limit_exceeded` JSON payload with
`retry_after_seconds` instead of executing.

### User Preferences (per-user, Settings > Preferences)

| Setting | Stored as | Used as |
|---------|-----------|---------|
| `image_generation_enabled` | boolean | User opt-in |
| `image_generation_default_quality` | a short lowercase token | mapped onto the configured model's qualities |
| `image_generation_default_size` | `WIDTHxHEIGHT` | mapped onto the configured model's sizes |
| `image_generation_output_format` | png, jpeg, webp | the format every generated or edited image is stored and served in |
| `image_generation_prompt_enhancement` | boolean | rewrite generation prompts first (ADR-315); inert while the operator withdraws it |

### Admin LLM Config

LLM type `image_generation` in the admin Configuration LLM UI. The list offers the
models `ImageOptionsCache` holds — a family declares them, a client serves them, an
active pricing row bills them — and nothing else; the write path refuses any other
(`image_model_not_served`) and a provider that is not the model's own
(`image_model_provider_mismatch`).

---

## Pricing

Pricing is stored in the `image_generation_pricing` table and cached in memory at
startup. Cost is per image, keyed by (model, quality, size). A row may also carry
`cost_per_input_image_usd`, the price of each reference image an edit sends —
required for a family that bills reference images per image, refused for one that
does not. The EUR figure uses the pricing cache's exchange rate, the one every cost
family reads.

The reference seed (`infrastructure/database/seeds/image_generation_pricing_seed.sql`)
carries the OpenAI rows and the Qwen Image 3.0 rows of the Germany (Frankfurt) grid,
deployment scope Global; migration `a9d3f1c7e5b2` carries the Qwen rows to instances
that never replay seeds. The seed is the reference for the figures; a guard test
holds it equal to the migration and holds every row to its family's rules.

### Cost Consolidation

Image generation costs are consolidated into the single `cost_eur` value shown to users:
- **Per-message**: `TokenSummaryDTO.to_metadata()` adds `image_generation_cost_eur` to `cost_eur`
- **Dashboard**: `UserService` sums LLM + Google API + image costs
- **Usage limits**: `usage_limits/repository.py` includes `cycle_image_generation_cost_eur` in limit checks

---

## Extensibility

### Adding a new vendor

1. Declare its family in `families.py` (qualities, size rule, billing tiers,
   reference-image billing, source limits) and add a rule for its model prefixes.
2. Write its client under `providers/` (implement `generate`, `edit`, `aclose`;
   return PNG bytes). A vendor speaking the OpenAI wire builds its SDK client with
   `openai_sdk_client` and wraps its calls in `vendor_errors`; one with a native SDK
   translates its own failures into `ImageGenerationError` the same way — status,
   vendor code, timeout — so the tool's classification needs no change.
3. Register the client in `client.py` — the import-time check refuses a family
   without a client and a client without a family.
4. Price its models: seed rows, plus a migration mirroring them for instances that
   do not replay seeds, plus the catalogue row (`llm_models`, kind `image`) that
   ADR-244's referential rule expects for any model a slot names.

### Adding a model of a known family

Through *Administration → LLM Image Pricing → Add*: pick the provider, fill in the
model name, a quality and a size the family accepts, the price per image, and the
reference-image price when the family bills it. The write publishes the cache
invalidation; every worker reloads `ImageOptionsCache`, and the model becomes
selectable in Configuration LLM. A model outside every family is refused with the
reason.
