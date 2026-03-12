/**
 * Common types for Settings components.
 *
 * Provides shared interfaces used across settings pages
 * to ensure consistency and reduce duplication.
 *
 * @module types/settings
 */

import type { Language } from '@/i18n/settings';

/**
 * Base props for settings section components.
 *
 * Used by:
 * - GeolocationSettings
 * - HomeLocationSettings
 * - MemorySettings
 * - PersonalitySettings
 * - TimezoneSelector
 * - LanguageSettings
 * - UserConnectorsSection
 * - AdminUsersSection
 * - AdminConnectorsSection
 * - AdminLLMPricingSection
 * - AdminPersonalitiesSection
 * - AdminVoiceSettingsSection
 */
export interface BaseSettingsProps {
  /** Current language for translations */
  lng: Language;
  /**
   * If true, wraps content in SettingsSection (collapsible accordion)
   * If false, renders only the inner content
   * @default true
   */
  collapsible?: boolean;
}
