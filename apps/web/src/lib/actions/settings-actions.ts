'use server';

import { createServerApiClient } from '@/lib/api-server';
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

interface LLMPricingData {
  model_name: string;
  input_price_per_1m_tokens: string;
  cached_input_price_per_1m_tokens: string | null;
  output_price_per_1m_tokens: string;
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('toggle_user_active_failed', error as Error, {
      component: 'ServerActions',
      action: 'toggleUserActive',
      userId,
      isActive,
    });
    return {
      success: false,
      error:
        err.response?.data?.detail ||
        `Erreur lors de ${isActive ? "l'activation" : 'la désactivation'} de l'utilisateur`,
    };
  }
}

/**
 * Delete user permanently (GDPR)
 *
 * @param userId - The ID of the user to delete
 */
export async function deleteUserGDPR(userId: string): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.delete(`/users/admin/${userId}/gdpr`);

    return {
      success: true,
      message: 'Utilisateur supprimé définitivement',
    };
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('delete_user_gdpr_failed', error as Error, {
      component: 'ServerActions',
      action: 'deleteUserGDPR',
      userId,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la suppression',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('create_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createLLMPricing',
      modelName: data.model_name,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la création du modèle',
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
  data: {
    model_name?: string;
    input_price_per_1m_tokens: string;
    cached_input_price_per_1m_tokens: string | null;
    output_price_per_1m_tokens: string;
  }
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('update_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateLLMPricing',
      originalModelName,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la modification du modèle',
    };
  }
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('reload_llm_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadLLMPricingCache',
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors du rechargement du cache',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('deactivate_llm_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateLLMPricing',
      pricingId,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la désactivation',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('create_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createGoogleApiPricing',
      apiName: data.api_name,
      endpoint: data.endpoint,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la création du tarif',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('update_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateGoogleApiPricing',
      originalApiName,
      originalEndpoint,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la modification du tarif',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('deactivate_google_api_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateGoogleApiPricing',
      pricingId,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors de la désactivation',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('reload_google_api_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadGoogleApiPricingCache',
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Erreur lors du rechargement du cache',
    };
  }
}

// ============================================================================
// Image Generation Pricing Admin
// ============================================================================

interface ImagePricingData {
  model: string;
  quality: string;
  size: string;
  cost_per_image_usd: string;
}

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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('create_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'createImagePricing',
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Error creating image pricing',
    };
  }
}

/**
 * Update image generation pricing entry (creates new version).
 */
export async function updateImagePricing(
  pricingId: string,
  data: Partial<ImagePricingData> & { cost_per_image_usd: string }
): Promise<ActionResponse> {
  try {
    const apiServer = await createServerApiClient();
    await apiServer.put(`/admin/image-pricing/pricing/${pricingId}`, data);
    return {
      success: true,
      message: 'Image pricing updated. New version created.',
    };
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('update_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'updateImagePricing',
      pricingId,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Error updating image pricing',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('deactivate_image_pricing_failed', error as Error, {
      component: 'ServerActions',
      action: 'deactivateImagePricing',
      pricingId,
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Error deactivating image pricing',
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
    const err = error as { response?: { data?: { detail?: string } } };
    logger.error('reload_image_pricing_cache_failed', error as Error, {
      component: 'ServerActions',
      action: 'reloadImagePricingCache',
    });
    return {
      success: false,
      error: err.response?.data?.detail || 'Error reloading cache',
    };
  }
}
