/**
 * Next.js middleware for i18n routing
 *
 * Public content URLs declare their language: unprefixed URLs are French,
 * regardless of cookies or browser preferences. Reading any route never changes
 * the saved preference. An actual application mount synchronizes its language
 * separately, so speculative route fetches cannot change it.
 *
 * Application and authentication language detection priority:
 * 1. URL path (e.g., /fr/dashboard)
 * 2. Cookie (NEXT_LOCALE) - User's explicit choice, takes absolute priority
 * 3. Accept-Language header - Only used on first visit before user selects
 * 4. Fallback to default (fr)
 *
 * Once user selects a language via LanguageSelector, the cookie is set
 * and browser's Accept-Language is ignored to respect user's choice.
 */

import { NextRequest, NextResponse } from 'next/server';
import { i18nRouter } from 'next-i18n-router';
import { languages, fallbackLng, cookieName, isLanguage } from './i18n/settings';
import type { Language } from './i18n/settings';
import { isPublicContentPath } from './lib/public-pages';

/** Type for i18n router config passed to localeDetector */
interface I18nConfig {
  locales: readonly string[];
  defaultLocale: string;
}

/**
 * Check if a value is a valid supported language
 */
function isValidLanguage(value: string | undefined): value is Language {
  return value !== undefined && isLanguage(value);
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
  // Reading a route, including a Link prefetch, must not save a preference.
  // With serverSetCookie alone set to 'never', the router redirects an explicit
  // URL to its cookie locale. Disable that automatic read too: localeDetector
  // still reads the request cookie when an unprefixed application URL negotiates.
  localeCookie: '',
  serverSetCookie: 'never' as const,
};

const publicI18nConfig = {
  ...i18nConfig,
  // Editorial URLs never negotiate, including on a real navigation.
  localeDetector: false as const,
};

export function proxy(request: NextRequest) {
  const isPublicContent = isPublicContentPath(request.nextUrl.pathname);
  const applicationConfig = {
    ...i18nConfig,
    // An explicit /fr application URL must stay French. Removing its prefix
    // would make the next unprefixed request negotiate a conflicting cookie.
    // Unprefixed application URLs retain their usual language negotiation.
    prefixDefault: request.nextUrl.pathname.split('/')[1] === fallbackLng,
  };
  const response = i18nRouter(request, isPublicContent ? publicI18nConfig : applicationConfig);

  // With negotiation off, the public router redirects only to remove /fr.
  // That URL normalization is permanent; preference-dependent redirects in
  // the application remain temporary. Preserve the router's locale headers.
  if (isPublicContent && response.status === 307) {
    return new NextResponse(response.body, { status: 301, headers: response.headers });
  }

  return response;
}

// Apply middleware to all routes except:
// - API routes (/api/*)
// - Static files (_next/static/*, _next/image/*)
// - Favicon and other root-level static files
// - SEO files (robots.txt, sitemap.xml, llms.txt, manifest.json)
export const config = {
  matcher:
    '/((?!api|_next/static|_next/image|favicon.ico|robots\\.txt|sitemap\\.xml|llms\\.txt|manifest\\.json|google.*\\.html|.*\\..*).*)',
};
