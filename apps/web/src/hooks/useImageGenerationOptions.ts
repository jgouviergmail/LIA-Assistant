'use client';

/**
 * Hook for fetching what the configured image-generation model offers, and what
 * the person's next image will use (ADR-305).
 *
 * Source of truth: the ``image_generation_pricing`` rows a model family and a
 * provider client can serve (``ImageOptionsCache`` server-side). The active
 * model is whatever is configured in Configuration LLM for the
 * ``image_generation`` LLM type; the vocabulary differs per vendor (OpenAI
 * offers low/medium/high, Qwen one ``standard`` quality and 1K/2K sizes).
 *
 * Used by ``ImageGenerationSettings`` (Préférences > Génération d'images IA).
 */

import { useApiQuery } from '@/hooks/useApiQuery';

export interface QualityOption {
  value: string;
  /** Min cost (in USD) across the model's available sizes for this quality. */
  min_cost_usd: number;
  /** Max cost (in USD) across the model's available sizes for this quality. */
  max_cost_usd: number;
}

export interface SizeOption {
  value: string;
  /** Square, landscape or portrait — what the label names. */
  orientation: 'square' | 'landscape' | 'portrait';
  /** The model family's billing tier for this size ("1k", "2k"), if it has tiers. */
  tier: string | null;
  /** i18n key for the user-facing label (e.g. "settings.image_generation.size_square"). */
  label_key: string;
}

export interface ImageGenerationOptions {
  /** The image_generation LLM type's currently configured model_name. */
  active_model: string;
  /** Provider that hosts the active model. */
  provider: string;
  qualities: QualityOption[];
  sizes: SizeOption[];
  /** The quality the next image uses: the stored preference mapped onto the offer. */
  effective_quality: string;
  /** The size the next generated image uses: the stored preference mapped onto the offer. */
  effective_size: string;
  /** Whether the operator offers the prompt enhancement (ADR-315): the switch shows only then. */
  prompt_enhancement_available: boolean;
}

/**
 * Fetch image-generation options for the currently configured model.
 *
 * Returns ``undefined`` while loading. The endpoint returns 400 (and
 * ``error`` becomes set) when the configured model is not served — no family,
 * no client or no active pricing row — and the caller displays a graceful
 * empty state in that case.
 */
export function useImageGenerationOptions() {
  return useApiQuery<ImageGenerationOptions>('/image-generation/options', {
    componentName: 'ImageGenerationSettings',
  });
}
