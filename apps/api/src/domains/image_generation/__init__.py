"""Image generation domain (ADR-305).

Several vendors behind one contract: a family declares what a model accepts and
how it is billed, one client per provider serves it.

Components:
- families / sizing: what each model family accepts, and size arithmetic
- providers/: the client contract and one client per vendor (OpenAI, Qwen)
- client: provider → client registry, checked complete at import
- options_cache / preferences: what the configured model offers, and the
  person's preferences mapped onto it
- models / repository / pricing_service: per-image prices and the cost of a call
- resize: an edit's source image, oriented and fitted to its family's limits
- tracker: TrackingContext helper for cost recording
- image_store: module-level store of pending images for the SSE done chunk
"""
