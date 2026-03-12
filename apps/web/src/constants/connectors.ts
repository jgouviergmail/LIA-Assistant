/**
 * Connector Types and Labels
 *
 * Centralized definitions for all third-party connector integrations.
 * This file eliminates duplication between AdminConnectorsSection and UserConnectorsSection.
 *
 * Usage:
 *   import { CONNECTOR_TYPES, CONNECTOR_LABELS, type ConnectorType } from '@/constants/connectors';
 *
 * Migration note:
 *   Previously duplicated in:
 *   - components/settings/AdminConnectorsSection.tsx (lines 16-34)
 *   - components/settings/UserConnectorsSection.tsx (lines 25-33)
 *
 * References:
 *   - ADR-001: Constants Centralization Strategy
 */

// ============================================================================
// CONNECTOR TYPES
// ============================================================================

/**
 * All supported connector types in the platform.
 *
 * When adding a new connector:
 * 1. Add the key to this array
 * 2. Add the label to CONNECTOR_LABELS
 * 3. Add the icon mapping to CONNECTOR_ICONS if applicable
 * 4. Update backend connector models if needed
 */
export const CONNECTOR_TYPES = [
  // Google OAuth connectors
  'google_gmail',
  'google_calendar',
  'google_drive',
  'google_contacts',
  'google_tasks',
  'google_places',
  // Google API Key connectors (global key, not per-user)
  'google_routes',
  // Apple iCloud connectors
  'apple_email',
  'apple_calendar',
  'apple_contacts',
  // Microsoft 365 connectors
  'microsoft_outlook',
  'microsoft_calendar',
  'microsoft_contacts',
  'microsoft_tasks',
  // External API Key connectors
  'openweathermap',
  'wikipedia',
  'perplexity',
  'brave_search',
  // Future connectors (not yet implemented)
  'slack',
  'notion',
  'github',
] as const;

/**
 * TypeScript type for connector identifiers.
 * This ensures type safety when working with connector types.
 */
export type ConnectorType = (typeof CONNECTOR_TYPES)[number];

// ============================================================================
// CONNECTOR LABELS
// ============================================================================

/**
 * Human-readable labels for each connector type.
 * Used in UI components for display purposes.
 */
export const CONNECTOR_LABELS: Record<ConnectorType, string> = {
  // Google OAuth connectors
  google_gmail: 'Gmail',
  google_calendar: 'Google Calendar',
  google_drive: 'Google Drive',
  google_contacts: 'Google Contacts',
  google_tasks: 'Google Tasks',
  google_places: 'Google Places',
  // Apple iCloud connectors
  apple_email: 'Apple Mail',
  apple_calendar: 'Apple Calendar',
  apple_contacts: 'Apple Contacts',
  // Microsoft 365 connectors
  microsoft_outlook: 'Microsoft Outlook',
  microsoft_calendar: 'Microsoft Calendar',
  microsoft_contacts: 'Microsoft Contacts',
  microsoft_tasks: 'Microsoft To Do',
  // Google API Key connectors
  google_routes: 'Google Routes',
  // External API Key connectors
  openweathermap: 'OpenWeatherMap',
  wikipedia: 'Wikipedia',
  perplexity: 'Perplexity',
  brave_search: 'Brave Search',
  // Future connectors
  slack: 'Slack',
  notion: 'Notion',
  github: 'GitHub',
};

// ============================================================================
// CONNECTOR CATEGORIES
// ============================================================================

// NOTE: Connector descriptions are now managed via i18n translations.
// See locales/{lng}/translation.json -> admin.connectors.connector_descriptions

/**
 * Connector categories for grouping in UI.
 * Helps organize connectors by their primary function.
 */
export const CONNECTOR_CATEGORIES = {
  google: [
    'google_gmail',
    'google_calendar',
    'google_drive',
    'google_contacts',
    'google_tasks',
    'google_places',
    'google_routes',
  ],
  apple: ['apple_email', 'apple_calendar', 'apple_contacts'],
  microsoft: ['microsoft_outlook', 'microsoft_calendar', 'microsoft_contacts', 'microsoft_tasks'],
  external: ['openweathermap', 'wikipedia', 'perplexity', 'brave_search'],
  productivity: ['slack', 'notion'],
  development: ['github'],
} as const;

/**
 * Category labels for UI display
 */
export const CATEGORY_LABELS = {
  google: 'Google Services',
  apple: 'Apple iCloud',
  microsoft: 'Microsoft 365',
  external: 'Services Externes',
  productivity: 'Productivité',
  development: 'Développement',
} as const;

// ============================================================================
// CONNECTOR STATUS
// ============================================================================

/**
 * Possible connector states
 */
export const CONNECTOR_STATUS = {
  ACTIVE: 'active',
  INACTIVE: 'inactive',
  ERROR: 'error',
  PENDING: 'pending',
} as const;

export type ConnectorStatus = (typeof CONNECTOR_STATUS)[keyof typeof CONNECTOR_STATUS];

/**
 * Status labels and colors for UI display
 */
export const CONNECTOR_STATUS_CONFIG: Record<ConnectorStatus, { label: string; color: string }> = {
  [CONNECTOR_STATUS.ACTIVE]: {
    label: 'Activé',
    color: 'green',
  },
  [CONNECTOR_STATUS.INACTIVE]: {
    label: 'Désactivé',
    color: 'gray',
  },
  [CONNECTOR_STATUS.ERROR]: {
    label: 'Erreur',
    color: 'red',
  },
  [CONNECTOR_STATUS.PENDING]: {
    label: 'En attente',
    color: 'yellow',
  },
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Type guard to check if a string is a valid connector type.
 *
 * @param type - String to validate
 * @returns True if type is a valid ConnectorType
 *
 * @example
 * if (isValidConnectorType(userInput)) {
 *   const label = CONNECTOR_LABELS[userInput]; // Type-safe access
 * }
 */
export function isValidConnectorType(type: string): type is ConnectorType {
  return CONNECTOR_TYPES.includes(type as ConnectorType);
}

/**
 * Get the category of a connector.
 *
 * @param connectorType - The connector type
 * @returns The category key or 'other' if not found
 *
 * @example
 * const category = getConnectorCategory('google_gmail'); // 'google'
 */
export function getConnectorCategory(
  connectorType: ConnectorType
): keyof typeof CONNECTOR_CATEGORIES | 'other' {
  for (const [category, types] of Object.entries(CONNECTOR_CATEGORIES)) {
    if ((types as readonly ConnectorType[]).includes(connectorType)) {
      return category as keyof typeof CONNECTOR_CATEGORIES;
    }
  }
  return 'other';
}

/**
 * Format connector status for display.
 *
 * @param isActive - Whether the connector is active
 * @returns Formatted status string
 *
 * @example
 * const status = formatConnectorStatus(true); // 'Activé'
 */
export function formatConnectorStatus(isActive: boolean): string {
  return isActive
    ? CONNECTOR_STATUS_CONFIG[CONNECTOR_STATUS.ACTIVE].label
    : CONNECTOR_STATUS_CONFIG[CONNECTOR_STATUS.INACTIVE].label;
}

/**
 * Get connector badge color based on active state.
 *
 * @param isActive - Whether the connector is active
 * @returns Tailwind color class
 *
 * @example
 * <Badge className={getConnectorBadgeColor(connector.is_active)}>
 *   {formatConnectorStatus(connector.is_active)}
 * </Badge>
 */
export function getConnectorBadgeColor(isActive: boolean): string {
  const status = isActive ? CONNECTOR_STATUS.ACTIVE : CONNECTOR_STATUS.INACTIVE;
  const color = CONNECTOR_STATUS_CONFIG[status].color;

  const colorMap: Record<string, string> = {
    green: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
    gray: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
    red: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
    yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  };

  return colorMap[color] || colorMap.gray;
}
