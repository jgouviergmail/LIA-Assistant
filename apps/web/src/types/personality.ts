/**
 * Personality types for LLM personality system
 */

/**
 * PersonalityListItem - Personality data for user display
 * Includes localized title and description
 */
export interface PersonalityListItem {
  id: string;
  code: string;
  emoji: string;
  is_default: boolean;
  title: string;
  description: string;
}

/**
 * PersonalityListResponse - Response from GET /api/v1/personalities
 */
export interface PersonalityListResponse {
  personalities: PersonalityListItem[];
  count: number;
}

/**
 * UserPersonalityResponse - Response from GET /api/v1/personalities/current
 */
export interface UserPersonalityResponse {
  personality_id: string | null;
  personality: PersonalityListItem | null;
}

/**
 * UserPersonalityUpdate - Request body for PATCH /api/v1/personalities/current
 */
export interface UserPersonalityUpdate {
  personality_id: string | null;
}

// Admin types (for settings panel)

/**
 * PersonalityTranslation - Translation for a personality
 */
export interface PersonalityTranslation {
  id: string;
  language_code: string;
  title: string;
  description: string;
  is_auto_translated: boolean;
}

/**
 * PersonalityResponse - Full personality with all translations (admin)
 */
export interface PersonalityResponse {
  id: string;
  code: string;
  emoji: string;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
  prompt_instruction: string;
  translations: PersonalityTranslation[];
  created_at: string;
  updated_at: string;
}

/**
 * PersonalityCreate - Request body for creating a personality (admin)
 */
export interface PersonalityCreate {
  code: string;
  emoji: string;
  is_default?: boolean;
  sort_order?: number;
  prompt_instruction: string;
  title: string;
  description: string;
  source_language?: string;
}

/**
 * PersonalityUpdate - Request body for updating a personality (admin)
 *
 * Supports updating:
 * - code (with uniqueness validation)
 * - emoji, is_default, is_active, sort_order
 * - prompt_instruction
 * - title/description (triggers auto-propagation to all languages by default)
 */
export interface PersonalityUpdate {
  code?: string;
  emoji?: string;
  is_default?: boolean;
  is_active?: boolean;
  sort_order?: number;
  prompt_instruction?: string;
  // Translation fields (triggers propagation if changed)
  title?: string;
  description?: string;
  source_language?: string;
}
