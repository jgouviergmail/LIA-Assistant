'use server';

import { createServerApiClient } from '@/lib/api-server';
import { getApiErrorDetail } from '@/lib/api-error';
import { logger } from '@/lib/logger';

/**
 * Server Actions for dashboard settings mutations
 *
 * Following Next.js 15 best practices:
 * - All mutations as server actions
 * - Proper error handling with typed responses
 * - Optimistic UI updates with useOptimistic hook (client-side)
 * - Type-safe responses
 * - BFF pattern with cookie forwarding to backend API
 *
 * Note: Cache revalidation removed to support optimistic updates.
 * Client components handle state updates using React 19's useOptimistic hook.
 */

// Response types
interface ActionResponse {
  success: boolean;
  error?: string;
  message?: string;
}

interface UserActivationData {
  is_active: boolean;
  reason?: string | null;
}

interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
}

interface UserActivationResponse {
  user: UserProfile;
  email_notification_sent: boolean;
  email_notification_error: string | null;
}

export type LLMProviderName =
  | 'openai'
  | 'anthropic'
  | 'deepseek'
  | 'perplexity'
  | 'ollama'
  | 'gemini'
  | 'qwen'
  | 'elevenlabs'
  | 'edge';

// Mirrors backend LLMModelKindLiteral / ReasoningWidgetLiteral / PricingUnitLiteral.
export type LLMModelKindName = 'chat' | 'image' | 'audio' | 'realtime' | 'tts' | 'embedding';
export type ReasoningWidgetName = 'none' | 'enum' | 'budget_int' | 'toggle_budget';
export type LLMPricingUnitName = 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';

/** One UTC window of a time-based tariff (ADR-223). Mirrors the backend
 *  ``TimeSlotPrice`` schema: [start,end) at minute granularity, end < start
 *  wraps midnight, windows must not overlap, prices in USD as decimal
 *  strings (same wire shape as the base unit prices). */
export interface TimeSlotPricePayload {
  start_utc: string;
  end_utc: string;
  input_unit_price: string;
  cached_input_unit_price: string | null;
  output_unit_price: string;
}

export interface ReasoningBudgetRangePayload {
  min: number;
  max: number;
  off_sentinel?: number | null;
  dynamic_sentinel?: number | null;
}

/** Reasoning + sampling block — Template mode (one field) OR Custom mode (10 fields).
 *  The backend's model_validator enforces XOR. */
export interface ReasoningSamplingPayload {
  reasoning_template?: string | null;
  kind?: LLMModelKindName | null;
  is_reasoning_model?: boolean | null;
  reasoning_widget?: ReasoningWidgetName | null;
  reasoning_enum_values?: string[] | null;
  reasoning_budget_range?: ReasoningBudgetRangePayload | null;
  reasoning_doc_i18n_key?: string | null;
  supports_temperature?: boolean | null;
  supports_top_p?: boolean | null;
  supports_frequency_penalty?: boolean | null;
  supports_presence_penalty?: boolean | null;
}

interface LLMPricingData extends ReasoningSamplingPayload {
  // Catalogue
  provider: LLMProviderName;
  model_name: string;
  max_input_tokens: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_strict_mode: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  // Pricing — semantic of the unit prices is given by `pricing_unit`
  // ('per_1m_tokens' for chat/text models, 'per_audio_minute' / 'per_audio_hour'
  // for STT/TTS).
  pricing_unit?: 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';
  input_unit_price: string;
  cached_input_unit_price: string | null;
  output_unit_price: string;
  /** Optional UTC windowed tariff; omitted = flat pricing. */
  time_slots?: TimeSlotPricePayload[];
}

/** Partial update payload — every field is optional. */
export interface LLMPricingUpdateData extends ReasoningSamplingPayload {
  model_name?: string;
  max_input_tokens?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_structured_output?: boolean;
  supports_strict_mode?: boolean;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  pricing_unit?: 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';
  input_unit_price?: string;
  cached_input_unit_price?: string | null;
  output_unit_price?: string;
  /** UTC windowed tariff: omitted = inherit the current row's slots onto the
   *  new temporal version; `[]` = clear (the backend drops explicit nulls, so
   *  the empty list IS the clearing sentinel); non-empty = replace. */
  time_slots?: TimeSlotPricePayload[];
}

/**
 * Toggle user activation status
 *
 * @param userId - The ID of the user to toggle
 * @param isActive - The new active status
 * @param reason - Optional reason for deactivation
 */
export async function toggleUserActive(
  userId: string,
  isActive: boolean,
  reason?: string | null
): Promise<ActionResponse> {
  try {
    const data: UserActivationData = {
      is_active: isActive,
    };

    if (!isActive && reason) {
      data.reason = reason;
    }

    const apiServer = await createServerApiClient();
    const response = await apiServer.patch<UserActivationResponse>(
      `/users/admin/${userId}/activation`,
      data
    );

    // Check if email notification was sent
    let message = `Utilisateur ${isActive ? 'activé' : 'désactivé'} avec succès`;

    if (response.email_notification_sent) {
      message += '. Un email de notification a été envoyé.';
    } else if (response.email_notification_error) {
      // Email failed - show warning but operation succeeded
      message += ` ⚠️ Attention : ${response.email_notification_error}`;
    }

    return {
      success: true,
      message,
    };
  } catch (error) {
    logger.error('toggle_user_active_failed', error as Error, {
      component: 'ServerActions',
      action: 'toggleUserActive',
      userId,
      isActive,
    });
    return {
      success: false,
      error:
        getApiErrorDetail(error) ??
        `Erreur lors de ${isActive ? "l'activation" : 'la désactivation'} de l'utilisateur`,
    };
  }
}

/**
 * Soft-delete user account: purge all personal data, preserve billing history.
 * Lifecycle: Active → Deactivated → **Deleted** → Erased (GDPR)
 * Precondition: user must be deactivated (is_active=false) first.
 *
 * @param userId - The ID of the user to delete
 * @param reason - Optional reason for deletion
 */
export async function deleteUserAccount(userId: string, reason?: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(
      `/users/admin/${userId}/delete-account`,
      reason
        ? {
            body: JSON.stringify({ reason }),
          }
        : undefined
    );

    return {
      success: true,
      message: 'Compte supprimé (données purgées, historique facturation conservé)',
    };
  } catch (error) {
    logger.error('delete_user_account_failed', error as Error, {
      component: 'ServerActions',
      action: 'deleteUserAccount',
      userId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la suppression du compte',
    };
  }
}

/**
 * GDPR hard-delete: permanently erase user row (email, name) from database.
 * Lifecycle: Active → Deactivated → Deleted → **Erased** (GDPR)
 * Precondition: user must be soft-deleted (via deleteUserAccount) first.
 *
 * @param userId - The ID of the user to erase
 */
export async function deleteUserGDPR(userId: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(`/users/admin/${userId}/gdpr`);

    return {
      success: true,
      message: 'Utilisateur effacé définitivement (RGPD)',
    };
  } catch (error) {
    logger.error('delete_user_gdpr_failed', error as Error, {
      component: 'ServerActions',
      action: 'deleteUserGDPR',
      userId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? "Erreur lors de l'effacement RGPD",
    };
  }
}

/**
 * Create new LLM pricing model
 *
 * @param data - The pricing data for the new model
 */
export async function createLLMPricing(data: LLMPricingData): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/llm/pricing', data);

    return {
      success: true,
      message: `Modèle "${data.model_name}" créé avec succès.`,
    };
  } catch (error) {
    logger.error('create_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createLLMPricing',
      modelName: data.model_name,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la création du modèle',
    };
  }
}

/**
 * Update LLM pricing model
 *
 * @param originalModelName - The current name of the model (for URL path)
 * @param data - The new pricing data (including optional new model_name for renaming)
 */
export async function updateLLMPricing(
  originalModelName: string,
  data: LLMPricingUpdateData
): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.put(`/admin/llm/pricing/${originalModelName}`, data);

    const newModelName = data.model_name || originalModelName;

    return {
      success: true,
      message: `Modèle "${newModelName}" modifié avec succès. Nouvelle version créée.`,
    };
  } catch (error) {
    logger.error('update_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateLLMPricing',
      originalModelName,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la modification du modèle',
    };
  }
}

/** Reasoning shape group derived from existing models. Drives the
 *  "Copy reasoning shape from..." selector. ``kind``, the four
 *  ``supports_*`` sampling flags AND ``reasoning_doc_i18n_key`` are
 *  intentionally NOT part of the template — they are saved per model
 *  regardless of the template chosen. */
export interface ReasoningTemplate {
  template_model_name: string;
  representative_provider: LLMProviderName;
  description: string;
  matching_count: number;
  is_reasoning_model: boolean;
  reasoning_widget: ReasoningWidgetName;
  reasoning_enum_values: string[] | null;
  reasoning_budget_range: ReasoningBudgetRangePayload | null;
}

interface ReasoningTemplatesResponse {
  templates: ReasoningTemplate[];
}

/** Fetch the list of reasoning + sampling templates derived from existing models.
 *  Drives the admin Pricing form's "Copy behavior from..." selector. */
export async function fetchReasoningTemplates(): Promise<ReasoningTemplate[]> {
  const apiServer = await createServerApiClient();
  const response = await apiServer.get<ReasoningTemplatesResponse>(
    '/admin/llm/reasoning-templates'
  );
  return response.templates;
}

/**
 * Reload LLM pricing cache
 */
export async function reloadLLMPricingCache(): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/llm/pricing/reload-cache');

    return {
      success: true,
      message: 'Cache des tarifs LLM rechargé avec succès.',
    };
  } catch (error) {
    logger.error('reload_llm_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadLLMPricingCache',
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors du rechargement du cache',
    };
  }
}

/**
 * Deactivate LLM pricing model
 *
 * @param pricingId - The ID of the pricing to deactivate
 */
export async function deactivateLLMPricing(pricingId: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(`/admin/llm/pricing/${pricingId}`);

    return {
      success: true,
      message: 'Modèle désactivé avec succès.',
    };
  } catch (error) {
    logger.error('deactivate_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateLLMPricing',
      pricingId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la désactivation',
    };
  }
}

// ============================================================================
// GOOGLE API PRICING ACTIONS
// ============================================================================

interface GoogleApiPricingData {
  api_name: string;
  endpoint: string;
  sku_name: string;
  cost_per_1000_usd: string;
}

/**
 * Create new Google API pricing entry
 *
 * @param data - The pricing data for the new entry
 */
export async function createGoogleApiPricing(data: GoogleApiPricingData): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/google-api/pricing', data);

    return {
      success: true,
      message: `Tarif "${data.api_name}:${data.endpoint}" créé avec succès.`,
    };
  } catch (error) {
    logger.error('create_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createGoogleApiPricing',
      apiName: data.api_name,
      endpoint: data.endpoint,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la création du tarif',
    };
  }
}

/**
 * Update Google API pricing entry
 *
 * @param originalApiName - The current API name (for URL path)
 * @param originalEndpoint - The current endpoint path (for URL path)
 * @param data - The new pricing data (including optional new api_name/endpoint for renaming)
 */
export async function updateGoogleApiPricing(
  originalApiName: string,
  originalEndpoint: string,
  data: {
    api_name?: string;
    endpoint?: string;
    sku_name: string;
    cost_per_1000_usd: string;
  }
): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.put(
      `/admin/google-api/pricing/${originalApiName}/${encodeURIComponent(originalEndpoint)}`,
      data
    );

    const newApiName = data.api_name || originalApiName;
    const newEndpoint = data.endpoint || originalEndpoint;

    return {
      success: true,
      message: `Tarif "${newApiName}:${newEndpoint}" modifié avec succès. Nouvelle version créée.`,
    };
  } catch (error) {
    logger.error('update_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateGoogleApiPricing',
      originalApiName,
      originalEndpoint,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la modification du tarif',
    };
  }
}

/**
 * Deactivate Google API pricing entry
 *
 * @param pricingId - The ID of the pricing to deactivate
 */
export async function deactivateGoogleApiPricing(pricingId: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(`/admin/google-api/pricing/${pricingId}`);

    return {
      success: true,
      message: 'Tarif désactivé avec succès.',
    };
  } catch (error) {
    logger.error('deactivate_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateGoogleApiPricing',
      pricingId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors de la désactivation',
    };
  }
}

/**
 * Reload Google API pricing cache
 */
export async function reloadGoogleApiPricingCache(): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/google-api/pricing/reload-cache');

    return {
      success: true,
      message: 'Cache des tarifs rechargé avec succès.',
    };
  } catch (error) {
    logger.error('reload_google_api_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadGoogleApiPricingCache',
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Erreur lors du rechargement du cache',
    };
  }
}

// ============================================================================
// Image Generation Pricing Admin
// ============================================================================

interface ImagePricingData {
  /** Provider that hosts the image-generation model (required on create). */
  provider: LLMProviderName;
  model: string;
  quality: string;
  size: string;
  cost_per_image_usd: string;
}

/** Partial update payload for image pricing. ``provider`` is intrinsic and
 * never sent on update (the backend rejects it on PUT). */
export type ImagePricingUpdateData = {
  model?: string;
  quality?: string;
  size?: string;
  cost_per_image_usd: string;
};

/**
 * Create new image generation pricing entry.
 */
export async function createImagePricing(data: ImagePricingData): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/image-pricing/pricing', data);
    return {
      success: true,
      message: `Pricing ${data.model}/${data.quality}/${data.size} created.`,
    };
  } catch (error) {
    logger.error('create_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createImagePricing',
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Error creating image pricing',
    };
  }
}

/**
 * Update image generation pricing entry (creates new version).
 */
export async function updateImagePricing(
  pricingId: string,
  data: ImagePricingUpdateData
): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.put(`/admin/image-pricing/pricing/${pricingId}`, data);
    return {
      success: true,
      message: 'Image pricing updated. New version created.',
    };
  } catch (error) {
    logger.error('update_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateImagePricing',
      pricingId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Error updating image pricing',
    };
  }
}

/**
 * Deactivate image generation pricing entry (soft delete).
 */
export async function deactivateImagePricing(pricingId: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(`/admin/image-pricing/pricing/${pricingId}`);
    return {
      success: true,
      message: 'Image pricing deactivated.',
    };
  } catch (error) {
    logger.error('deactivate_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateImagePricing',
      pricingId,
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Error deactivating image pricing',
    };
  }
}

/**
 * Reload image generation pricing cache.
 */
export async function reloadImagePricingCache(): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.post('/admin/image-pricing/pricing/reload-cache');
    return {
      success: true,
      message: 'Image pricing cache reloaded.',
    };
  } catch (error) {
    logger.error('reload_image_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadImagePricingCache',
    });
    return {
      success: false,
      error: getApiErrorDetail(error) ?? 'Error reloading cache',
    };
  }
}
