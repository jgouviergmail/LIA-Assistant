/**
 * Personality API Client
 * Handles personality-related API calls
 */

import {
  PersonalityListResponse,
  PersonalityResponse,
  PersonalityCreate,
  PersonalityUpdate,
  UserPersonalityResponse,
  UserPersonalityUpdate,
} from '@/types/personality';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch all active personalities (localized to user's language)
 */
export async function fetchPersonalities(): Promise<PersonalityListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch personalities: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch user's current personality preference
 */
export async function fetchCurrentPersonality(): Promise<UserPersonalityResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/current`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch current personality: ${response.status}`);
  }

  return response.json();
}

/**
 * Update user's personality preference
 */
export async function updateCurrentPersonality(
  data: UserPersonalityUpdate
): Promise<UserPersonalityResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/current`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Failed to update personality: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Admin API functions
// ============================================================================

/**
 * Fetch all personalities with full details (admin only)
 */
export async function fetchPersonalitiesAdmin(): Promise<PersonalityResponse[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/admin`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch personalities: ${response.status}`);
  }

  return response.json();
}

/**
 * Create a new personality (admin only)
 */
export async function createPersonality(data: PersonalityCreate): Promise<PersonalityResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/admin`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    // Handle Pydantic validation errors (detail can be array or object)
    let errorMessage = `Failed to create personality: ${response.status}`;
    if (errorData.detail) {
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        // Pydantic validation errors
        errorMessage = errorData.detail
          .map((e: { msg?: string; loc?: string[] }) => e.msg || JSON.stringify(e))
          .join(', ');
      } else {
        errorMessage = JSON.stringify(errorData.detail);
      }
    }
    throw new Error(errorMessage);
  }

  return response.json();
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
  const url = new URL(`${API_BASE_URL}/api/v1/personalities/admin/${id}`);
  url.searchParams.set('propagate', propagate.toString());

  const response = await fetch(url.toString(), {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    // Handle Pydantic validation errors and conflict errors
    let errorMessage = `Failed to update personality: ${response.status}`;
    if (errorData.detail) {
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail
          .map((e: { msg?: string }) => e.msg || JSON.stringify(e))
          .join(', ');
      }
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Delete a personality (admin only)
 */
export async function deletePersonality(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/admin/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to delete personality: ${response.status}`);
  }
}

/**
 * Trigger auto-translation for a personality (admin only)
 * Returns the number of translations created
 */
export async function translatePersonality(
  id: string
): Promise<{ translations_created: number; source_language: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/personalities/admin/${id}/auto-translate`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to translate personality: ${response.status}`);
  }

  return response.json();
}
