'use client';

/**
 * Hook for fetching the qualities and sizes available for the currently
 * configured image-generation model.
 *
 * Source of truth: ``image_generation_pricing`` table (DISTINCT-aggregated
 * by ``ImageOptionsCache`` server-side). The active model is whatever is
 * configured in Configuration LLM for the ``image_generation`` LLM type.
 *
 * Used by ``ImageGenerationSettings`` (Préférences > Génération d'images
 * IA) to populate its dropdowns dynamically — replacing the previously
 * hardcoded values.
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
}

/**
 * Fetch image-generation options for the currently configured model.
 *
 * Returns ``undefined`` while loading. The endpoint returns 422 (and
 * ``error`` becomes set) when no pricing rows exist for the configured
 * model — the caller should display a graceful empty state in that case.
 */
export function useImageGenerationOptions() {
  return useApiQuery<ImageGenerationOptions>('/image-generation/options', {
    componentName: 'ImageGenerationSettings',
  });
}
