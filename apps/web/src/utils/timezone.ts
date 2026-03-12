/**
 * Timezone detection and validation utilities.
 * Uses browser Intl API for automatic timezone detection.
 */

import { logger } from '@/lib/logger';

/**
 * Get user's timezone from browser.
 *
 * Uses Intl.DateTimeFormat().resolvedOptions().timeZone
 * which returns IANA timezone name (e.g., "Europe/Paris").
 *
 * @returns IANA timezone string or null if detection fails
 *
 * @example
 * ```ts
 * const tz = getBrowserTimezone();
 * // => "Europe/Paris" (for user in France)
 * // => "America/New_York" (for user in Eastern US)
 * ```
 */
export function getBrowserTimezone(): string | null {
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    // Validate format (should be "Region/City")
    if (timezone && timezone.includes('/')) {
      return timezone;
    }

    return null;
  } catch (error) {
    logger.error('timezone_detection_failed', error instanceof Error ? error : undefined);
    return null;
  }
}

/**
 * Get UTC offset for a timezone at current time.
 *
 * @param timezone - IANA timezone name
 * @returns UTC offset string (e.g., "UTC+1", "UTC-5")
 *
 * @example
 * ```ts
 * getTimezoneOffset("Europe/Paris");
 * // => "UTC+1" (in winter)
 * // => "UTC+2" (in summer, DST)
 * ```
 */
export function getTimezoneOffset(timezone: string): string {
  try {
    const now = new Date();
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'shortOffset',
    });

    const parts = formatter.formatToParts(now);
    const offsetPart = parts.find(part => part.type === 'timeZoneName');

    if (offsetPart && offsetPart.value !== 'GMT') {
      // Convert "GMT+1" to "UTC+1"
      return offsetPart.value.replace('GMT', 'UTC');
    }

    return 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * Get current time in a specific timezone.
 *
 * @param timezone - IANA timezone name
 * @param locale - Locale string (e.g., "fr-FR", "en-US")
 * @returns Formatted time string
 *
 * @example
 * ```ts
 * getCurrentTimeInTimezone("Europe/Paris", "fr-FR");
 * // => "mercredi 29 octobre 2025 à 15:42"
 * ```
 */
export function getCurrentTimeInTimezone(timezone: string, locale: string = 'fr-FR'): string {
  // Safety check for undefined/null
  if (!timezone) {
    return new Date().toLocaleString(locale);
  }

  try {
    const now = new Date();
    const formatter = new Intl.DateTimeFormat(locale, {
      timeZone: timezone,
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

    return formatter.format(now);
  } catch {
    return new Date().toLocaleString(locale);
  }
}

/**
 * Format timezone for display in selector.
 *
 * @param timezone - IANA timezone name
 * @returns Formatted string (e.g., "Paris (UTC+1)")
 *
 * @example
 * ```ts
 * formatTimezoneDisplay("Europe/Paris");
 * // => "Paris (UTC+1)"
 * ```
 */
export function formatTimezoneDisplay(timezone: string): string {
  // Safety check for undefined/null
  if (!timezone) {
    return 'Unknown';
  }

  const city = timezone.split('/').pop() || timezone;
  const offset = getTimezoneOffset(timezone);

  // Replace underscores with spaces
  const formattedCity = city.replace(/_/g, ' ');

  return `${formattedCity} (${offset})`;
}

/**
 * Group timezones by region.
 *
 * @param timezones - List of IANA timezone names
 * @returns Object with regions as keys
 *
 * @example
 * ```ts
 * const grouped = groupTimezonesByRegion([
 *   "Europe/Paris",
 *   "Europe/London",
 *   "America/New_York"
 * ]);
 * // => { Europe: [...], America: [...] }
 * ```
 */
export function groupTimezonesByRegion(timezones: string[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {};

  timezones.forEach(tz => {
    const [region] = tz.split('/');
    if (!grouped[region]) {
      grouped[region] = [];
    }
    grouped[region].push(tz);
  });

  return grouped;
}

/**
 * Greeting period types based on time of day.
 */
export type GreetingPeriod = 'morning' | 'lunch' | 'afternoon' | 'evening' | 'night';

/**
 * Get the appropriate greeting period based on current time in user's timezone.
 *
 * Time ranges:
 * - 6h - 12h: morning (Bonne journée)
 * - 12h - 14h: lunch (Bon appétit)
 * - 14h - 18h: afternoon (Bonjour)
 * - 18h - 22h: evening (Bonne soirée)
 * - 22h - 6h: night (Bonne nuit)
 *
 * @param timezone - IANA timezone name (e.g., "Europe/Paris")
 * @returns Greeting period key for i18n
 *
 * @example
 * ```ts
 * getGreetingPeriod("Europe/Paris");
 * // => "morning" (if it's 10:00 in Paris)
 * // => "lunch" (if it's 12:30 in Paris)
 * ```
 */
export function getGreetingPeriod(timezone?: string | null): GreetingPeriod {
  try {
    const now = new Date();
    let hour: number;

    if (timezone) {
      // Get hour in user's timezone
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: timezone,
        hour: 'numeric',
        hour12: false,
      });
      hour = parseInt(formatter.format(now), 10);
    } else {
      // Fallback to local time
      hour = now.getHours();
    }

    if (hour >= 6 && hour < 12) {
      return 'morning';
    } else if (hour >= 12 && hour < 14) {
      return 'lunch';
    } else if (hour >= 14 && hour < 18) {
      return 'afternoon';
    } else if (hour >= 18 && hour < 22) {
      return 'evening';
    } else {
      return 'night';
    }
  } catch {
    // Fallback to afternoon as a neutral greeting
    return 'afternoon';
  }
}
