/**
 * Connector constants and configuration.
 * Extracted from UserConnectorsSection.tsx for DRY compliance.
 */

import { Plug, Cloud, Book, Search, MapPin, Globe, type LucideIcon } from 'lucide-react';

// ============================================================================
// CONNECTOR TYPES
// ============================================================================

export const GOOGLE_CONNECTOR_TYPES = [
  'google_contacts',
  'google_gmail',
  'gmail', // Legacy type
  'google_calendar',
  'google_drive',
  'google_tasks',
  // Note: google_places moved to API_KEY_CONNECTOR_TYPES (uses global API key)
] as const;

export const API_KEY_CONNECTOR_TYPES = [
  'openweathermap',
  'wikipedia',
  'perplexity',
  'brave_search',
  'google_places', // Uses global API key, simple toggle activation
  'browser', // No API key required, headless browser automation
] as const;

export const APPLE_CONNECTOR_TYPES = ['apple_email', 'apple_calendar', 'apple_contacts'] as const;

export const MICROSOFT_CONNECTOR_TYPES = [
  'microsoft_outlook',
  'microsoft_calendar',
  'microsoft_contacts',
  'microsoft_tasks',
] as const;

export const HUE_CONNECTOR_TYPES = ['philips_hue'] as const;

// Gmail types (new + legacy) for checking if Gmail is connected
export const GMAIL_TYPES = ['google_gmail', 'gmail'] as const;

/**
 * Mutual exclusivity map: connector type -> conflicting types.
 * Only one connector per functional category can be ACTIVE at a time.
 * With 3 providers (Google, Apple, Microsoft), each type conflicts with 2 others.
 */
export const MUTUAL_EXCLUSIVITY_MAP: Record<string, string[]> = {
  // Email
  apple_email: ['google_gmail', 'microsoft_outlook'],
  google_gmail: ['apple_email', 'microsoft_outlook'],
  microsoft_outlook: ['apple_email', 'google_gmail'],
  // Calendar
  apple_calendar: ['google_calendar', 'microsoft_calendar'],
  google_calendar: ['apple_calendar', 'microsoft_calendar'],
  microsoft_calendar: ['apple_calendar', 'google_calendar'],
  // Contacts
  apple_contacts: ['google_contacts', 'microsoft_contacts'],
  google_contacts: ['apple_contacts', 'microsoft_contacts'],
  microsoft_contacts: ['apple_contacts', 'google_contacts'],
  // Tasks (no Apple — only Google and Microsoft)
  google_tasks: ['microsoft_tasks'],
  microsoft_tasks: ['google_tasks'],
};

// LocalStorage keys for bulk connection queues
export const BULK_CONNECT_QUEUE_KEY = 'google_bulk_connect_queue';
export const MICROSOFT_BULK_CONNECT_QUEUE_KEY = 'microsoft_bulk_connect_queue';

// ============================================================================
// OAUTH URL HELPERS
// ============================================================================

/**
 * Build full OAuth redirect URL from a relative authorize path.
 *
 * @param authorizeUrl - Relative URL from backend (e.g., "/api/v1/connectors/gmail/authorize")
 * @returns Full URL including API host for redirect
 *
 * @example
 * buildOAuthRedirectUrl("/api/v1/connectors/gmail/authorize")
 * // Returns "http://localhost:8000/api/v1/connectors/gmail/authorize" in dev
 */
export function buildOAuthRedirectUrl(authorizeUrl: string): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || '';
  return `${apiBaseUrl}${authorizeUrl}`;
}

// ============================================================================
// GOOGLE AUTH ENDPOINTS
// ============================================================================

export const GOOGLE_AUTH_ENDPOINTS: Record<string, string> = {
  google_contacts: '/connectors/google-contacts/authorize',
  google_gmail: '/connectors/gmail/authorize',
  google_calendar: '/connectors/google-calendar/authorize',
  google_drive: '/connectors/google-drive/authorize',
  google_tasks: '/connectors/google-tasks/authorize',
  // Note: google_places removed - now uses API key activation endpoint
};

export const MICROSOFT_AUTH_ENDPOINTS: Record<string, string> = {
  microsoft_outlook: '/connectors/microsoft-outlook/authorize',
  microsoft_calendar: '/connectors/microsoft-calendar/authorize',
  microsoft_contacts: '/connectors/microsoft-contacts/authorize',
  microsoft_tasks: '/connectors/microsoft-tasks/authorize',
};

export const HUE_AUTH_ENDPOINTS: Record<string, string> = {
  philips_hue: '/connectors/philips-hue/authorize',
};

// ============================================================================
// CONNECTOR ICONS CONFIGURATION
// ============================================================================

export interface ConnectorIconConfig {
  icon?: LucideIcon;
  emoji?: string;
  color: string;
}

export const CONNECTOR_ICONS: Record<string, ConnectorIconConfig> = {
  // Google Services (OAuth) - using emojis for visual distinction
  google_contacts: { emoji: '👥', color: 'blue' },
  google_gmail: { emoji: '📧', color: 'red' },
  gmail: { emoji: '📧', color: 'red' }, // Legacy type alias
  google_calendar: { emoji: '📅', color: 'green' },
  google_drive: { emoji: '📁', color: 'yellow' },
  google_tasks: { emoji: '✅', color: 'purple' },
  google_places: { icon: MapPin, color: 'emerald' },
  // Apple iCloud Services (same icons as Google equivalents for consistency)
  apple_email: { emoji: '📧', color: 'slate' },
  apple_calendar: { emoji: '📅', color: 'slate' },
  apple_contacts: { emoji: '👥', color: 'slate' },
  // Microsoft 365 Services (OAuth)
  microsoft_outlook: { emoji: '📧', color: 'blue' },
  microsoft_calendar: { emoji: '📅', color: 'blue' },
  microsoft_contacts: { emoji: '👥', color: 'blue' },
  microsoft_tasks: { emoji: '✅', color: 'blue' },
  // API Key Services
  openweathermap: { icon: Cloud, emoji: '🌤️', color: 'orange' },
  wikipedia: { icon: Book, emoji: '📚', color: 'slate' },
  perplexity: { icon: Search, emoji: '🔍', color: 'indigo' },
  brave_search: { icon: Search, emoji: '🦁', color: 'violet' },
  browser: { icon: Globe, emoji: '🌐', color: 'blue' },
  // Smart Home
  philips_hue: { emoji: '💡', color: 'yellow' },
};

// Uniform background class for all connector icons
export const ICON_BG_CLASS = 'bg-muted/80 dark:bg-muted/50';

// Text color classes for connector icons (used for icon components, not emojis)
export const ICON_TEXT_CLASSES: Record<string, string> = {
  blue: 'text-blue-600 dark:text-blue-400',
  red: 'text-red-600 dark:text-red-400',
  green: 'text-green-600 dark:text-green-400',
  yellow: 'text-yellow-600 dark:text-yellow-400',
  purple: 'text-purple-600 dark:text-purple-400',
  emerald: 'text-emerald-600 dark:text-emerald-400',
  orange: 'text-orange-600 dark:text-orange-400',
  slate: 'text-slate-600 dark:text-slate-400',
  indigo: 'text-indigo-600 dark:text-indigo-400',
  violet: 'text-violet-600 dark:text-violet-400',
};

// Default fallback icon
export const DEFAULT_CONNECTOR_ICON = Plug;

// ============================================================================
// API KEY CONNECTORS CONFIGURATION
// ============================================================================

export interface ApiKeyConnectorConfig {
  type: string;
  icon: LucideIcon;
  color: string;
  requiresKey: boolean;
}

export const API_KEY_CONNECTORS: readonly ApiKeyConnectorConfig[] = [
  {
    type: 'openweathermap',
    icon: Cloud,
    color: 'orange',
    requiresKey: true,
  },
  {
    type: 'wikipedia',
    icon: Book,
    color: 'slate',
    requiresKey: false, // Wikipedia doesn't require an API key
  },
  {
    type: 'perplexity',
    icon: Search,
    color: 'indigo',
    requiresKey: true,
  },
  {
    type: 'brave_search',
    icon: Search,
    color: 'violet',
    requiresKey: true,
  },
  {
    type: 'google_places',
    icon: MapPin,
    color: 'emerald',
    requiresKey: false, // Uses global API key configured on server
  },
  {
    type: 'browser',
    icon: Globe,
    color: 'blue',
    requiresKey: false, // No API key — uses local Playwright/Chromium
  },
] as const;

// ============================================================================
// CONNECTORS WITH PREFERENCES
// ============================================================================

// Connectors using the /connectors/{id}/preferences API
// Note: google_places uses LocationSettings (/users/me/home-location) instead
export const CONNECTORS_WITH_PREFERENCES = [
  'google_calendar',
  'google_tasks',
  'apple_calendar',
  'microsoft_calendar',
  'microsoft_tasks',
];

// Preference field mapping by connector type
export const PREFERENCE_FIELDS: Record<string, string> = {
  google_calendar: 'default_calendar_name',
  google_tasks: 'default_task_list_name',
  apple_calendar: 'default_calendar_name',
  microsoft_calendar: 'default_calendar_name',
  microsoft_tasks: 'default_task_list_name',
};

// ============================================================================
// GOOGLE CONNECTOR METADATA (for available connectors list)
// ============================================================================

export interface GoogleConnectorMetadata {
  type: string;
  labelKey: string;
  descriptionKey: string;
  /** For Gmail, we check multiple types (google_gmail, gmail) */
  checkTypes?: readonly string[];
}

export const GOOGLE_CONNECTORS_METADATA: readonly GoogleConnectorMetadata[] = [
  // --- Simple connectors (no preferences) ---
  {
    type: 'google_contacts',
    labelKey: 'settings.connectors.google.contacts',
    descriptionKey: 'settings.connectors.google.contacts_description',
  },
  {
    type: 'google_gmail',
    labelKey: 'settings.connectors.gmail.label',
    descriptionKey: 'settings.connectors.gmail.description',
    checkTypes: GMAIL_TYPES,
  },
  {
    type: 'google_drive',
    labelKey: 'settings.connectors.google.drive',
    descriptionKey: 'settings.connectors.google.drive_description',
  },
  // --- Connectors with preferences (grouped together) ---
  {
    type: 'google_calendar',
    labelKey: 'settings.connectors.google.calendar',
    descriptionKey: 'settings.connectors.google.calendar_description',
  },
  {
    type: 'google_tasks',
    labelKey: 'settings.connectors.google.tasks',
    descriptionKey: 'settings.connectors.google.tasks_description',
  },
  // Note: google_places moved to API_KEY_CONNECTORS (uses global API key)
] as const;

// ============================================================================
// APPLE CONNECTOR METADATA
// ============================================================================

export interface AppleConnectorMetadata {
  type: string;
  labelKey: string;
  descriptionKey: string;
  /** Functional category for mutual exclusivity display */
  category: 'email' | 'calendar' | 'contacts';
}

export const APPLE_CONNECTORS_METADATA: readonly AppleConnectorMetadata[] = [
  {
    type: 'apple_email',
    labelKey: 'settings.connectors.apple.email',
    descriptionKey: 'settings.connectors.apple.email_description',
    category: 'email',
  },
  {
    type: 'apple_calendar',
    labelKey: 'settings.connectors.apple.calendar',
    descriptionKey: 'settings.connectors.apple.calendar_description',
    category: 'calendar',
  },
  {
    type: 'apple_contacts',
    labelKey: 'settings.connectors.apple.contacts',
    descriptionKey: 'settings.connectors.apple.contacts_description',
    category: 'contacts',
  },
] as const;

// ============================================================================
// MICROSOFT CONNECTOR METADATA
// ============================================================================

export interface MicrosoftConnectorMetadata {
  type: string;
  labelKey: string;
  descriptionKey: string;
  /** Functional category for mutual exclusivity display */
  category: 'email' | 'calendar' | 'contacts' | 'tasks';
}

export const MICROSOFT_CONNECTORS_METADATA: readonly MicrosoftConnectorMetadata[] = [
  {
    type: 'microsoft_outlook',
    labelKey: 'settings.connectors.microsoft.outlook',
    descriptionKey: 'settings.connectors.microsoft.outlook_description',
    category: 'email',
  },
  {
    type: 'microsoft_calendar',
    labelKey: 'settings.connectors.microsoft.calendar',
    descriptionKey: 'settings.connectors.microsoft.calendar_description',
    category: 'calendar',
  },
  {
    type: 'microsoft_contacts',
    labelKey: 'settings.connectors.microsoft.contacts',
    descriptionKey: 'settings.connectors.microsoft.contacts_description',
    category: 'contacts',
  },
  {
    type: 'microsoft_tasks',
    labelKey: 'settings.connectors.microsoft.tasks',
    descriptionKey: 'settings.connectors.microsoft.tasks_description',
    category: 'tasks',
  },
] as const;

// Philips Hue Smart Home metadata
export const HUE_CONNECTORS_METADATA = [
  {
    type: 'philips_hue',
    labelKey: 'settings.connectors.hue.label',
    descriptionKey: 'settings.connectors.hue.description',
  },
] as const;
