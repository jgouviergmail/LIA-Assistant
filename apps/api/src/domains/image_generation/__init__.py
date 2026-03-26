"""Image generation domain.

Provides AI image generation capabilities with multi-provider support,
per-image pricing, and cost tracking integration.

Components:
- models: ImageGenerationPricing database model
- repository: Database queries for pricing data
- pricing_service: In-memory pricing cache (follows GoogleApiPricingService pattern)
- client: Abstract ImageGenerationClient + OpenAI implementation + factory
- tracker: TrackingContext helper for cost recording
- image_store: ContextVar helpers for generated image SSE injection
"""
