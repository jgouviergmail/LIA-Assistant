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
 *   - Fonts: apps/web/src/lib/fonts.ts (next/font/local — self-hosted woff2 in src/fonts/)
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
// FONT SIZE
// ============================================================================

/*
 * The interface text size is a TEXT scale factor, never a zoom: every font size
 * of the stylesheet is written `size × var(--lia-text-scale)` (the Tailwind
 * `text-*` scale, the `text-px-*` utility, the `--lia-text-*` card tokens, the
 * body's inherited size and every `font-size` of the CSS files), while the root
 * `rem` stays the browser's own — so panels, spacing and icons keep their size
 * whatever the reader picks. Scaling the root size was measured shrinking the
 * chat, the debug panel and the settings with the text (owner, 2026-09-29).
 * Measured by e2e/smoke/font-size-extremes.spec.ts at both bounds: the panels
 * keep their boxes, and the two densest rows hold from 320 to 1440 px.
 *
 * Mirrored by the server (`USER_FONT_SIZE_*_PX` in apps/api/src/core/constants.py)
 * and pinned by apps/api/tests/unit/domains/users/test_font_size_preference.py,
 * which reads the three literals below — keep them plain integer literals.
 */
export const FONT_SIZE_MIN_PX = 14;
export const FONT_SIZE_MAX_PX = 20;
export const DEFAULT_FONT_SIZE_PX = 16;

/** Every size the settings offer, one whole pixel apart. */
export const FONT_SIZE_STEPS: readonly number[] = Array.from(
  { length: FONT_SIZE_MAX_PX - FONT_SIZE_MIN_PX + 1 },
  (_, i) => FONT_SIZE_MIN_PX + i
);

/** LocalStorage key for the font size preference. */
export const FONT_SIZE_STORAGE_KEY = 'font-size';

/** CSS custom property every font size of the stylesheet is multiplied by. */
export const FONT_SIZE_CSS_VAR = '--lia-text-scale';

/** True for a whole pixel size inside the offered range. */
export function isValidFontSize(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= FONT_SIZE_MIN_PX &&
    value <= FONT_SIZE_MAX_PX
  );
}

/**
 * Read a size from storage; anything but an offered step, spelled exactly as
 * the pre-paint script looks it up, reads as absent.
 */
export function parseStoredFontSize(raw: string | null): number | null {
  return FONT_SIZE_STEPS.find(step => String(step) === raw) ?? null;
}

/** The factor a size multiplies every text size by (16 px = 1). */
export function fontSizeScale(px: number): number {
  return px / DEFAULT_FONT_SIZE_PX;
}

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
