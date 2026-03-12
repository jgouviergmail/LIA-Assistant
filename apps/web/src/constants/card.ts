/**
 * Card Component Constants
 *
 * Centralized constants for the unified card design system.
 * Used by both the Card component and design-system documentation.
 */

/**
 * Domain accent types for card left border colors.
 * Maps to CSS variables: --lia-{domain}-accent
 */
export const DOMAIN_ACCENTS = [
  'email',
  'contact',
  'calendar',
  'task',
  'place',
  'weather',
  'drive',
] as const;

/**
 * Type for domain accent values.
 * Use this type instead of inline union types for consistency.
 */
export type DomainAccent = (typeof DOMAIN_ACCENTS)[number];

/**
 * Visual variant types for card elevation/interaction.
 */
export const CARD_VARIANTS = ['default', 'elevated', 'interactive', 'flat', 'gradient'] as const;
export type CardVariant = (typeof CARD_VARIANTS)[number];

/**
 * Status variant types for semantic card states.
 */
export const CARD_STATUSES = ['default', 'info', 'success', 'warning', 'error'] as const;
export type CardStatus = (typeof CARD_STATUSES)[number];

/**
 * Size variant types for card padding.
 */
export const CARD_SIZES = ['none', 'sm', 'md', 'lg'] as const;
export type CardSize = (typeof CARD_SIZES)[number];
