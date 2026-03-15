/**
 * Utilities for internationalized number, date, and phone formatting.
 * Uses Intl.NumberFormat, Intl.DateTimeFormat, and libphonenumber-js.
 */

import { type Language, fallbackLng, getIntlLocale } from '@/i18n/settings';
import { parsePhoneNumber, isValidPhoneNumber, CountryCode } from 'libphonenumber-js';

/**
 * Format a number with locale-appropriate separators.
 *
 * @param value Number to format
 * @param locale Language code for formatting (default: 'fr')
 * @returns Formatted string (e.g., "1 234 567" for fr, "1,234,567" for en)
 *
 * @example
 * formatNumber(1234567) // "1 234 567" (French)
 * formatNumber(1234567, 'en') // "1,234,567" (English)
 * formatNumber(150) // "150"
 */
export function formatNumber(value: number, locale: Language = fallbackLng): string {
  const formatted = new Intl.NumberFormat(getIntlLocale(locale), {
    useGrouping: true,
  }).format(value);
  // Replace narrow no-break space (U+202F) and no-break space (U+00A0) with regular space
  // for consistent display across all environments
  return formatted.replace(/[\u202F\u00A0]/g, ' ');
}

/**
 * Format an amount in euros with locale-appropriate formatting.
 *
 * @param value Amount in euros
 * @param decimals Number of decimal places (default: 4)
 * @param locale Language code for formatting (default: 'fr')
 * @returns Formatted string (e.g., "0,0042 €" for fr, "€0.0042" for en)
 *
 * @example
 * formatEuro(0.0042) // "0,0042 €" (French)
 * formatEuro(2.45, 2, 'en') // "€2.45" (English)
 * formatEuro(2.45, 2) // "2,45 €" (French)
 */
export function formatEuro(
  value: number,
  decimals: number = 2,
  locale: Language = fallbackLng
): string {
  const formatted = new Intl.NumberFormat(getIntlLocale(locale), {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
  // Replace narrow no-break space (U+202F) and no-break space (U+00A0) with regular space
  // for consistent display across all environments
  return formatted.replace(/[\u202F\u00A0]/g, ' ');
}

/**
 * Format a file size in bytes to a human-readable string.
 *
 * @param bytes File size in bytes
 * @returns Formatted string (e.g., "1.5 MB", "256 KB", "0 B")
 *
 * @example
 * formatFileSize(0) // "0 B"
 * formatFileSize(512) // "512 B"
 * formatFileSize(1536) // "1.5 KB"
 * formatFileSize(2621440) // "2.5 MB"
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Format a date with locale-appropriate formatting.
 *
 * @param date Date to format (Date object, ISO string, or timestamp)
 * @param locale Language code for formatting (default: 'fr')
 * @param options Intl.DateTimeFormat options (optional)
 * @returns Formatted date string
 *
 * @example
 * formatDate(new Date()) // "24/10/2025" (French)
 * formatDate(new Date(), 'en') // "10/24/2025" (English)
 * formatDate(new Date(), 'fr', { dateStyle: 'long' }) // "24 octobre 2025"
 */
export function formatDate(
  date: Date | string,
  locale: Language = fallbackLng,
  options?: Intl.DateTimeFormatOptions
): string {
  return new Intl.DateTimeFormat(getIntlLocale(locale), options).format(new Date(date));
}

/**
 * Get billing cycle start and end dates formatted for display.
 *
 * @param cycleStartDate Start date of the billing cycle
 * @param locale Language code for formatting (default: 'fr')
 * @returns Object with formatted start and end dates, or null if no date
 *
 * @example
 * getCycleDates(new Date('2025-10-15')) // { start: "15/10", end: "15/11" }
 * getCycleDates(new Date('2025-10-15'), 'en') // { start: "10/15", end: "11/15" }
 */
export function getCycleDates(
  cycleStartDate: Date | string | null | undefined,
  locale: Language = fallbackLng
): { start: string; end: string } | null {
  if (!cycleStartDate) return null;

  const start = new Date(cycleStartDate);
  const end = new Date(start);
  end.setMonth(end.getMonth() + 1);

  const options: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: '2-digit',
  };

  return {
    start: formatDate(start, locale, options),
    end: formatDate(end, locale, options),
  };
}

/**
 * Format a billing cycle period with locale-appropriate formatting.
 * @deprecated Use getCycleDates with i18n translation instead
 */
export function formatCycleDates(
  cycleStartDate: Date | string | null | undefined,
  locale: Language = fallbackLng
): string {
  const dates = getCycleDates(cycleStartDate, locale);
  if (!dates) return '-';
  return `${dates.start} - ${dates.end}`;
}

/**
 * Format a phone number according to its country conventions.
 *
 * @param phone Phone number string (can include country code or not)
 * @param defaultCountry Default country if not detectable (default: 'FR')
 * @returns Formatted phone number or original string if not valid
 *
 * @example
 * formatPhone("+33612345678") // "06.12.34.56.78"
 * formatPhone("0612345678") // "06.12.34.56.78" (assumes FR)
 * formatPhone("+14155551234") // "(415) 555-1234"
 * formatPhone("+447911123456") // "07911 123456"
 */
export function formatPhone(phone: string, defaultCountry: CountryCode = 'FR'): string {
  if (!phone || typeof phone !== 'string') return phone;

  // Clean the input
  const cleaned = phone.trim();
  if (!cleaned) return phone;

  try {
    // Try to parse with default country
    if (!isValidPhoneNumber(cleaned, defaultCountry)) {
      // Try without default country (for numbers with +)
      if (!cleaned.startsWith('+') || !isValidPhoneNumber(cleaned)) {
        return phone; // Return original if not valid
      }
    }

    const parsed = parsePhoneNumber(cleaned, defaultCountry);
    if (!parsed) return phone;

    const country = parsed.country;

    // French format: 06.12.34.56.78
    if (country === 'FR') {
      const national = parsed.formatNational(); // "06 12 34 56 78"
      return national.replace(/\s/g, '.');
    }

    // For other countries, use their national format
    return parsed.formatNational();
  } catch {
    return phone; // Return original on error
  }
}

/**
 * Process a text string and format all phone numbers found.
 * Detects patterns like +33..., 06..., +1..., etc.
 *
 * @param text Text containing phone numbers
 * @param defaultCountry Default country for numbers without country code
 * @returns Text with formatted phone numbers
 */
export function formatPhonesInText(text: string, defaultCountry: CountryCode = 'FR'): string {
  if (!text || typeof text !== 'string') return text;

  // Regex to match phone number patterns:
  // - International: +XX followed by digits/spaces/dashes
  // - French mobile: 06/07 followed by 8 digits
  // - French landline: 01-05/09 followed by 8 digits
  const phoneRegex =
    /(\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{0,4})|(\b0[1-9][\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b)/g;

  return text.replace(phoneRegex, match => {
    const formatted = formatPhone(match, defaultCountry);
    return formatted;
  });
}
