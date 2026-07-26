/**
 * Personality API Client
 *
 * Goes through `apiClient` like every other data path in the app. It used to
 * call `fetch` directly, which cost three things:
 *
 * - **Session handling**: a 401 must eject to the localized login. A raw fetch
 *   threw `Error("Failed to fetch personalities: 401")` and left the user on a
 *   dead settings panel.
 * - **A timeout**: `apiClient` arms `AbortSignal.timeout`; a raw fetch hangs as
 *   long as the network lets it.
 * - **One error contract**: four of these functions hand-rolled their own
 *   `detail` reader — two handling the Pydantic list shape, two interpolating
 *   the list straight into a template (printing `[object Object]`) — and the
 *   other four never read the backend reason at all. `ApiError` now carries the
 *   parsed body on `.data` for all of them, and `getApiErrorDetail` reads it.
 */

import apiClient from '@/lib/api-client';
import {
  PersonalityListResponse,
  PersonalityResponse,
  PersonalityCreate,
  PersonalityUpdate,
  UserPersonalityResponse,
  UserPersonalityUpdate,
} from '@/types/personality';

/**
 * Fetch all active personalities (localized to user's language)
 */
export async function fetchPersonalities(): Promise<PersonalityListResponse> {
  return apiClient.get<PersonalityListResponse>('/personalities');
}

/**
 * Fetch user's current personality preference
 */
export async function fetchCurrentPersonality(): Promise<UserPersonalityResponse> {
  return apiClient.get<UserPersonalityResponse>('/personalities/current');
}

/**
 * Update user's personality preference
 */
export async function updateCurrentPersonality(
  data: UserPersonalityUpdate
): Promise<UserPersonalityResponse> {
  return apiClient.patch<UserPersonalityResponse>('/personalities/current', data);
}

// ============================================================================
// Admin API functions
// ============================================================================

/**
 * Fetch all personalities with full details (admin only)
 */
export async function fetchPersonalitiesAdmin(): Promise<PersonalityResponse[]> {
  return apiClient.get<PersonalityResponse[]>('/personalities/admin');
}

/**
 * Create a new personality (admin only)
 */
export async function createPersonality(data: PersonalityCreate): Promise<PersonalityResponse> {
  return apiClient.post<PersonalityResponse>('/personalities/admin', data);
}

/**
 * Update a personality (admin only)
 *
 * @param id - Personality ID
 * @param data - Update data (code, emoji, title, description, etc.)
 * @param propagate - Auto-propagate translations when title/description change (default: true)
 */
export async function updatePersonality(
  id: string,
  data: PersonalityUpdate,
  propagate: boolean = true
): Promise<PersonalityResponse> {
  return apiClient.patch<PersonalityResponse>(`/personalities/admin/${id}`, data, {
    params: { propagate },
  });
}

/**
 * Delete a personality (admin only)
 */
export async function deletePersonality(id: string): Promise<void> {
  await apiClient.delete<void>(`/personalities/admin/${id}`);
}

/**
 * Trigger auto-translation for a personality (admin only)
 * Returns the number of translations created
 */
export async function translatePersonality(
  id: string
): Promise<{ translations_created: number; source_language: string }> {
  return apiClient.post<{ translations_created: number; source_language: string }>(
    `/personalities/admin/${id}/auto-translate`
  );
}
