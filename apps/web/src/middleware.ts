/**
 * Next.js middleware for i18n routing
 *
 * Language detection priority:
 * 1. URL path (e.g., /fr/dashboard)
 * 2. Cookie (NEXT_LOCALE) - User's explicit choice, takes absolute priority
 * 3. Accept-Language header - Only used on first visit before user selects
 * 4. Fallback to default (fr)
 *
 * Once user selects a language via LanguageSelector, the cookie is set
 * and browser's Accept-Language is ignored to respect user's choice.
 */

import { NextRequest } from 'next/server';
import { i18nRouter } from 'next-i18n-router';
import { languages, fallbackLng, cookieName } from './i18n/settings';
import type { Language } from './i18n/settings';

/** Type for i18n router config passed to localeDetector */
interface I18nConfig {
  locales: readonly string[];
  defaultLocale: string;
}

/**
 * Check if a value is a valid supported language
 */
function isValidLanguage(value: string | undefined): value is Language {
  return value !== undefined && languages.includes(value as Language);
}

/**
 * Parse quality factor from Accept-Language segment
 * Returns 1.0 for missing/invalid q values (RFC 7231 default)
 */
function parseQualityFactor(qPart: string | undefined): number {
  if (!qPart) return 1.0;

  const match = qPart.match(/q\s*=\s*([\d.]+)/i);
  if (!match) return 1.0;

  const quality = parseFloat(match[1]);
  return Number.isNaN(quality) ? 1.0 : Math.min(1.0, Math.max(0, quality));
}

/**
 * Parse Accept-Language header and return best matching locale
 *
 * @param acceptLanguage - Header value (e.g., "en-US,en;q=0.9,fr;q=0.8")
 * @param locales - Supported locales
 * @param defaultLocale - Fallback locale
 */
function getLocaleFromAcceptLanguage(
  acceptLanguage: string,
  locales: readonly string[],
  defaultLocale: string
): string {
  // Parse and sort by quality factor (q value)
  const browserLocales = acceptLanguage
    .split(',')
    .map(lang => {
      const [locale, qPart] = lang.trim().split(';');
      const quality = parseQualityFactor(qPart);
      // Extract base language (e.g., "en-US" -> "en")
      const baseLocale = locale?.split('-')[0]?.toLowerCase() || '';
      return { locale: baseLocale, quality };
    })
    .filter(({ locale }) => locale.length > 0)
    .sort((a, b) => b.quality - a.quality);

  // Find first matching supported locale
  for (const { locale } of browserLocales) {
    if (locales.includes(locale)) {
      return locale;
    }
  }

  return defaultLocale;
}

/**
 * Custom locale detector that prioritizes user's explicit cookie choice
 * over browser's Accept-Language header.
 *
 * - If user has selected a language (cookie exists), use it exclusively
 * - Otherwise, detect from Accept-Language header for first-time visitors
 */
function localeDetector(request: NextRequest, config: I18nConfig): string {
  // Priority 1: User's explicit choice via cookie (set by LanguageSelector)
  const cookieLocale = request.cookies.get(cookieName)?.value;
  if (isValidLanguage(cookieLocale)) {
    return cookieLocale;
  }

  // Priority 2: Browser's Accept-Language (first visit only)
  const acceptLanguage = request.headers.get('Accept-Language');
  if (acceptLanguage) {
    return getLocaleFromAcceptLanguage(acceptLanguage, config.locales, config.defaultLocale);
  }

  // Fallback to default
  return config.defaultLocale;
}

/** i18n router configuration with custom locale detector */
const i18nConfig = {
  locales: [...languages],
  defaultLocale: fallbackLng,
  prefixDefault: false,
  localeDetector,
};

export function middleware(request: NextRequest) {
  return i18nRouter(request, i18nConfig);
}

// Apply middleware to all routes except:
// - API routes (/api/*)
// - Static files (_next/static/*, _next/image/*)
// - Favicon and other root-level static files
// - SEO files (robots.txt, sitemap.xml, llms.txt, manifest.json)
export const config = {
  matcher:
    '/((?!api|_next/static|_next/image|favicon.ico|robots\\.txt|sitemap\\.xml|llms\\.txt|manifest\\.json|.*\\..*).*)',
};
