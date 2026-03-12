/**
 * Font Family Types and Definitions
 *
 * Centralized definitions for all font families available in the application.
 * This file eliminates duplication between font-context.tsx and FontSettings.tsx.
 *
 * Usage:
 *   import { FONT_FAMILIES, FONT_FAMILY_NAMES, type FontFamilyName } from '@/constants/fonts';
 *
 * References:
 *   - Backend: apps/api/src/domains/shared/schemas.py (VALID_FONT_FAMILIES)
 *   - CSS: apps/web/src/styles/globals.css (data-font selectors)
 *   - Fonts: apps/web/src/lib/fonts.ts (next/font/google configuration)
 */

// ============================================================================
// FONT FAMILY TYPES
// ============================================================================

/**
 * All supported font family names in the platform.
 *
 * When adding a new font:
 * 1. Add the key to this array
 * 2. Add the font definition to FONT_DEFINITIONS
 * 3. Add the CSS variable in globals.css under data-font selectors
 * 4. Add the font loading in lib/fonts.ts
 * 5. Update backend VALID_FONT_FAMILIES in shared/schemas.py
 * 6. Add i18n translations for the font label and description
 */
export const FONT_FAMILY_NAMES = [
  'system',
  'noto-sans',
  'plus-jakarta-sans',
  'ibm-plex-sans',
  'geist',
  'source-sans-pro',
  'merriweather',
  'libre-baskerville',
  'fira-code',
] as const;

/**
 * TypeScript type for font family identifiers.
 * This ensures type safety when working with font families.
 */
export type FontFamilyName = (typeof FONT_FAMILY_NAMES)[number];

/**
 * Default font family when no preference is set.
 */
export const DEFAULT_FONT_FAMILY: FontFamilyName = 'system';

/**
 * LocalStorage key for font family preference.
 */
export const FONT_STORAGE_KEY = 'font-family';

// ============================================================================
// FONT CATEGORIES
// ============================================================================

/**
 * Font category types for grouping in UI.
 */
export type FontCategory = 'sans' | 'serif' | 'mono';

/**
 * Font categories for grouping in UI.
 */
export const FONT_CATEGORIES: Record<FontCategory, FontFamilyName[]> = {
  sans: ['system', 'noto-sans', 'plus-jakarta-sans', 'ibm-plex-sans', 'geist', 'source-sans-pro'],
  serif: ['merriweather', 'libre-baskerville'],
  mono: ['fira-code'],
};

// ============================================================================
// FONT DEFINITIONS
// ============================================================================

/**
 * Font definition with metadata for UI display.
 */
export interface FontDefinition {
  name: FontFamilyName;
  fontFamily: string;
  category: FontCategory;
}

/**
 * Complete font definitions with CSS font-family values for preview.
 * Maps each font name to its CSS font-family stack.
 */
export const FONT_DEFINITIONS: FontDefinition[] = [
  {
    name: 'system',
    fontFamily: 'var(--font-inter), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'noto-sans',
    fontFamily: 'var(--font-noto-sans), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'plus-jakarta-sans',
    fontFamily: 'var(--font-plus-jakarta), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'ibm-plex-sans',
    fontFamily: 'var(--font-ibm-plex), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'geist',
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'source-sans-pro',
    fontFamily: 'var(--font-source-sans), system-ui, sans-serif',
    category: 'sans',
  },
  {
    name: 'merriweather',
    fontFamily: 'var(--font-merriweather), Georgia, serif',
    category: 'serif',
  },
  {
    name: 'libre-baskerville',
    fontFamily: 'var(--font-libre-baskerville), Georgia, serif',
    category: 'serif',
  },
  {
    name: 'fira-code',
    fontFamily: 'var(--font-fira-code), monospace',
    category: 'mono',
  },
];

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Type guard to check if a string is a valid font family name.
 *
 * @param fontFamily - String to validate
 * @returns True if fontFamily is a valid FontFamilyName
 *
 * @example
 * if (isValidFontFamily(userInput)) {
 *   const definition = getFontDefinition(userInput); // Type-safe access
 * }
 */
export function isValidFontFamily(fontFamily: string): fontFamily is FontFamilyName {
  return FONT_FAMILY_NAMES.includes(fontFamily as FontFamilyName);
}

/**
 * Get the font definition by name.
 *
 * @param fontFamily - The font family name
 * @returns The font definition or undefined if not found
 *
 * @example
 * const font = getFontDefinition('geist');
 * if (font) console.log(font.fontFamily);
 */
export function getFontDefinition(fontFamily: FontFamilyName): FontDefinition | undefined {
  return FONT_DEFINITIONS.find(f => f.name === fontFamily);
}

/**
 * Get the category of a font family.
 *
 * @param fontFamily - The font family name
 * @returns The category or 'sans' as default
 *
 * @example
 * const category = getFontCategory('merriweather'); // 'serif'
 */
export function getFontCategory(fontFamily: FontFamilyName): FontCategory {
  return getFontDefinition(fontFamily)?.category ?? 'sans';
}

/**
 * Get all fonts in a specific category.
 *
 * @param category - The font category
 * @returns Array of font definitions in that category
 *
 * @example
 * const serifFonts = getFontsByCategory('serif');
 */
export function getFontsByCategory(category: FontCategory): FontDefinition[] {
  return FONT_DEFINITIONS.filter(f => f.category === category);
}
