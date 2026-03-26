# AI Image Generation (evolution)

> Architecture and integration guide for AI-powered image generation from text descriptions.

**Phase**: evolution — AI Image Generation
**Created**: 2026-03-25
**Status**: Implemented

---

## Overview

LIA can generate images from text descriptions using AI models (OpenAI gpt-image-1 family). Images are generated via a dedicated tool (`generate_image`), saved as attachments on disk, and displayed as cards below the assistant response.

### Features

| Feature | Description |
|---------|-------------|
| Multi-model | gpt-image-1, gpt-image-1.5, gpt-image-1-mini (admin-configurable) |
| Multi-provider | Extensible factory (OpenAI today, add Gemini/Stability later) |
| User preferences | Quality (low/medium/high), size (square/landscape/portrait), format (PNG) |
| Admin LLM Config | Model/provider selection via admin UI (LLM_TYPES_REGISTRY) |
| Admin Pricing | Full CRUD admin panel for image pricing (model, quality, size → cost/image) |
| Cost tracking | Per-image pricing (DB-cached), consolidated into TrackingContext |
| Attachment storage | Disk + DB with TTL-based cleanup via existing attachment system |
| Usage limits | Image costs included in per-user usage limit enforcement |

---

## Architecture

### Data Flow

```
User: "Generate an image of an astronaut cat"
  |
Router → domain: image_generation, tool: generate_image (score: 1.0)
  |
Planner → ExecutionPlan with 1 TOOL step
  |
Task Orchestrator → parallel_executor invokes generate_image tool
  |
  ├─ 1. Load user preferences (quality, size) from User model
  ├─ 2. Resolve provider + model from LLMConfigOverrideCache
  ├─ 3. OpenAIImageClient.generate(prompt) → base64 PNG
  ├─ 4. track_image_generation_call() → cost in TrackingContext
  ├─ 5. Save PNG as Attachment (disk + DB, TTL cleanup)
  ├─ 6. store_pending_image(conversation_id, url, alt)
  └─ 7. Return UnifiedToolOutput.action_success()
  |
Response Node → LLM generates text (knows image was generated)
  |
SSE Streaming
  ├─ Stream LLM tokens
  ├─ Archive message with generated_images in metadata
  ├─ done chunk includes generated_images: [{url, alt}]
  └─ Frontend renders image card below message bubble
```

### Edit Image Flow

```
User: "Make this image look realistic"
  |
Router → domain: image_generation, tool: edit_image (score: 1.0)
  |
Planner → ExecutionPlan with 1 TOOL step (source_attachment_id optional)
  |
Task Orchestrator → parallel_executor invokes edit_image tool
  |
  ├─ 1. Load user preferences (quality) from User model
  ├─ 2. Resolve source image:
  │     a. If source_attachment_id is valid UUID → use it
  │     b. Else → SELECT latest image attachment for user (ORDER BY created_at DESC)
  ├─ 3. Resize source to nearest supported dimension (1024×1024, 1024×1536, 1536×1024)
  ├─ 4. OpenAIImageClient.edit(prompt, image_b64) → new base64 PNG
  ├─ 5. track_image_generation_call() → cost in TrackingContext
  ├─ 6. Save result as new Attachment
  ├─ 7. store_pending_image(conversation_id, url, alt)
  └─ 8. Return UnifiedToolOutput.action_success()
```

### Key Design Decisions

1. **Attachment-based storage** (not inline base64): Images are saved to disk and served via `/api/v1/attachments/{id}`. This avoids bloating the LLM context and SSE stream with multi-MB data.

2. **Done metadata delivery** (not markdown injection): Image URLs are sent in the `done` chunk metadata, not as markdown tokens. The frontend renders them as dedicated HTML cards. This avoids HTML nesting violations (`<div>` inside `<p>`) and proxy issues.

3. **Module-level dict** (not ContextVar): `_pending_images` in `image_store.py` uses a thread-safe dict keyed by `conversation_id`. ContextVar was rejected because LangGraph tool execution runs in separate async tasks where ContextVar writes are invisible to the parent streaming coroutine.

4. **UnifiedToolOutput** (not plain str): The tool returns `UnifiedToolOutput.action_success()` so the `adaptive_replanner` correctly detects a successful result (not "empty_results").

---

## File Structure

### New Files

| File | Description |
|------|-------------|
| `src/core/config/image_generation.py` | Settings (feature flag, max images) |
| `src/domains/image_generation/__init__.py` | Domain package |
| `src/domains/image_generation/models.py` | `ImageGenerationPricing` SQLAlchemy model |
| `src/domains/image_generation/repository.py` | Pricing DB queries |
| `src/domains/image_generation/pricing_service.py` | In-memory pricing cache (follows GoogleApiPricingService) |
| `src/domains/image_generation/client.py` | Abstract client + OpenAI impl + factory |
| `src/domains/image_generation/tracker.py` | TrackingContext helper |
| `src/domains/image_generation/image_store.py` | Pending images store for SSE delivery |
| `src/domains/image_generation/resize.py` | Intelligent resize to nearest supported dimension |
| `src/domains/agents/tools/image_generation_tools.py` | `generate_image` + `edit_image` tools |
| `src/domains/agents/image_generation/catalogue_manifests.py` | Agent + Tool manifests |
| `src/domains/image_generation/router.py` | Admin CRUD endpoints (`/admin/image-pricing/pricing`) |
| `src/domains/image_generation/schemas.py` | Pydantic request/response schemas for admin API |
| `apps/web/src/components/settings/ImageGenerationSettings.tsx` | User settings UI |
| `apps/web/src/components/settings/AdminImagePricingSection.tsx` | Admin pricing management UI |

### Modified Files

| File | Change |
|------|--------|
| `src/core/config/__init__.py` | `ImageGenerationSettings` in MRO |
| `src/core/constants.py` | `IMAGE_GENERATION_*` constants |
| `src/core/field_names.py` | `FIELD_IMAGE_GENERATION_*` |
| `src/domains/auth/models.py` | 4 user preference columns |
| `src/domains/chat/models.py` | Cost tracking columns (MessageTokenSummary + UserStatistics) |
| `src/domains/chat/service.py` | `ImageGenerationRecord`, `record_image_generation_call()` |
| `src/domains/chat/schemas.py` | `TokenSummaryDTO` includes image costs in consolidated `cost_eur` |
| `src/domains/chat/repository.py` | UPSERT + statistics with image fields |
| `src/domains/usage_limits/repository.py` | Image costs in SQL sums |
| `src/domains/llm_config/constants.py` | `image_generation` LLM type + `IMAGE_GENERATION_MODELS` |
| `src/domains/agents/api/service.py` | Done metadata + message archiving with images |
| `src/domains/agents/nodes/response_node.py` | `/api/v1/attachments/` in allowed prefixes |
| `src/domains/agents/orchestration/adaptive_replanner.py` | Detect `result` key for action tools |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GENERATION_ENABLED` | `false` | Global feature flag |
| `IMAGE_GENERATION_MAX_IMAGES_PER_REQUEST` | `1` | Max images per tool call (1-4) |

### User Preferences (per-user, Settings > Preferences)

| Setting | Default | Values |
|---------|---------|--------|
| `image_generation_enabled` | `true` | User opt-in |
| `image_generation_default_quality` | `low` | low, medium, high |
| `image_generation_default_size` | `1024x1536` | 1024x1024, 1536x1024, 1024x1536 |
| `image_generation_output_format` | `png` | png, jpeg, webp |

### Admin LLM Config

LLM type `image_generation` in the admin Configuration LLM UI. Default: `openai / gpt-image-1`. Available models: `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`.

---

## Pricing

Pricing is stored in the `image_generation_pricing` table and cached in memory at startup. Cost is per-image, not per-token.

| Model | Quality | 1024x1024 | 1024x1536 | 1536x1024 |
|-------|---------|-----------|-----------|-----------|
| gpt-image-1 | low | $0.011 | $0.016 | $0.016 |
| gpt-image-1 | medium | $0.042 | $0.063 | $0.063 |
| gpt-image-1 | high | $0.167 | $0.250 | $0.250 |
| gpt-image-1.5 | low | $0.009 | $0.013 | $0.013 |
| gpt-image-1.5 | medium | $0.034 | $0.050 | $0.050 |
| gpt-image-1.5 | high | $0.133 | $0.200 | $0.200 |
| gpt-image-1-mini | low | $0.005 | $0.006 | $0.006 |
| gpt-image-1-mini | medium | $0.011 | $0.015 | $0.015 |
| gpt-image-1-mini | high | $0.036 | $0.052 | $0.052 |

### Cost Consolidation

Image generation costs are consolidated into the single `cost_eur` value shown to users:
- **Per-message**: `TokenSummaryDTO.to_metadata()` adds `image_generation_cost_eur` to `cost_eur`
- **Dashboard**: `UserService` sums LLM + Google API + image costs
- **Usage limits**: `usage_limits/repository.py` includes `cycle_image_generation_cost_eur` in limit checks

---

## Extensibility

### Adding a New Provider

1. Create `XxxImageClient(ImageGenerationClient)` in `client.py`
2. Add `"xxx": XxxImageClient` to `_IMAGE_CLIENT_REGISTRY`
3. Add `"xxx": [model_ids]` to `IMAGE_GENERATION_MODELS` in `llm_config/constants.py`
4. Insert pricing rows in `image_generation_pricing` table
5. Admin selects provider + model via LLM Config UI

### Adding a New Model

1. Insert pricing rows in `image_generation_pricing` table (9 entries: 3 qualities x 3 sizes)
2. Add model ID to `IMAGE_GENERATION_MODELS[provider]` in constants
3. Reload pricing cache (`POST /api/v1/google-api/pricing/reload-cache` pattern — admin endpoint TBD)
