/**
 * Formatters for Debug Panel
 *
 * Specific utilities for formatting values displayed in the debug panel.
 * Reuses existing functions from @/lib/format when possible.
 */

import { formatNumber as libFormatNumber, formatEuro as libFormatEuro } from '@/lib/format';
import type { DebugTone } from './tones';

/**
 * Formats a decimal number as a percentage
 *
 * @param value - Decimal value (0.0 - 1.0)
 * @param decimals - Number of decimals (default: 0)
 * @returns Formatted string (e.g., "45%", "12.5%")
 *
 * @example
 * formatPercent(0.45) // "45%"
 * formatPercent(0.876) // "88%"
 * formatPercent(0.125, 1) // "12.5%"
 * formatPercent(0.00142, 2) // "0.14%"
 */
export function formatPercent(value: number, decimals: number = 0): string {
  if (typeof value !== 'number' || !isFinite(value)) {
    return '-';
  }
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Formats a token count with units (K, M)
 *
 * @param count - Number of tokens
 * @returns Formatted string (e.g., "1.5k", "2.3M")
 *
 * @example
 * formatTokenCount(150) // "150"
 * formatTokenCount(1500) // "1.5k"
 * formatTokenCount(2000000) // "2.0M"
 * formatTokenCount(2345678) // "2.3M"
 */
export function formatTokenCount(count: number): string {
  if (typeof count !== 'number' || !isFinite(count)) {
    return '-';
  }

  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }

  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`;
  }

  return count.toString();
}

/**
 * Formats a duration in milliseconds
 *
 * @param ms - Duration in milliseconds
 * @param includeUnit - Include unit (default: true)
 * @returns Formatted string (e.g., "1.2s", "450ms")
 *
 * @example
 * formatDuration(1200) // "1.2s"
 * formatDuration(450) // "450ms"
 * formatDuration(1200, false) // "1.2"
 * formatDuration(0) // "0ms"
 */
export function formatDuration(ms: number, includeUnit: boolean = true): string {
  if (typeof ms !== 'number' || !isFinite(ms)) {
    return '-';
  }

  if (ms >= 1000) {
    const seconds = (ms / 1000).toFixed(1);
    return includeUnit ? `${seconds}s` : seconds;
  }

  return includeUnit ? `${Math.round(ms)}ms` : Math.round(ms).toString();
}

/**
 * Formats a cost in euros (reuses lib/format.ts)
 *
 * @param cost - Cost in euros
 * @param decimals - Number of decimals (default: 4)
 * @returns Formatted string (e.g., "0,0014 EUR")
 *
 * @example
 * formatCost(0.00142) // "0,0014 €"
 * formatCost(2.45, 2) // "2,45 €"
 */
export function formatCost(cost: number, decimals: number = 4): string {
  if (typeof cost !== 'number' || !isFinite(cost)) {
    return '-';
  }
  return libFormatEuro(cost, decimals);
}

/**
 * Formats a generic value for display
 *
 * Automatically detects type and applies appropriate formatting:
 * - Boolean -> "Yes"/"No"
 * - Number 0-1 -> Percentage
 * - Number >1000 -> Formatted with separators
 * - String -> Unchanged
 * - null/undefined -> "-"
 * - Array -> Comma-joined
 * - Object -> JSON stringified
 *
 * @param value - Value to format
 * @returns Formatted string
 *
 * @example
 * formatValue(true) // "Yes"
 * formatValue(false) // "No"
 * formatValue(0.45) // "45%"
 * formatValue(1234) // "1 234"
 * formatValue("hello") // "hello"
 * formatValue(null) // "-"
 * formatValue(undefined) // "-"
 * formatValue(['a', 'b']) // "a, b"
 */
export function formatValue(value: unknown): string {
  // Null/undefined
  if (value === null || value === undefined) {
    return '-';
  }

  // Boolean
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  // Number
  if (typeof value === 'number') {
    if (!isFinite(value)) {
      return '-';
    }

    // Percentage (0-1 range)
    if (value > 0 && value < 1) {
      return formatPercent(value);
    }

    // Large numbers with separators
    if (value >= 1000 || value <= -1000) {
      return libFormatNumber(value);
    }

    // Small numbers
    return value.toString();
  }

  // String
  if (typeof value === 'string') {
    return value;
  }

  // Array
  if (Array.isArray(value)) {
    return value.map(v => formatValue(v)).join(', ');
  }

  // Object
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '[Object]';
    }
  }

  // Fallback
  return String(value);
}

/**
 * Truncates text with ellipsis
 *
 * @param text - Text to truncate
 * @param maxLength - Maximum length (default: 50)
 * @param ellipsis - Ellipsis character (default: "...")
 * @returns Truncated text
 *
 * @example
 * truncateText("Hello world", 8) // "Hello..."
 * truncateText("Short", 10) // "Short"
 * truncateText("Long text", 6, "…") // "Long…"
 */
export function truncateText(
  text: string,
  maxLength: number = 50,
  ellipsis: string = '...'
): string {
  if (typeof text !== 'string') {
    return String(text);
  }

  if (text.length <= maxLength) {
    return text;
  }

  return text.slice(0, maxLength - ellipsis.length) + ellipsis;
}

/**
 * Formats a wall-clock time as a deterministic 24h "HH:MM:SS".
 *
 * Locale-independent on purpose: request timestamps in the debug panel are
 * technical identifiers scanned across entries, so their shape must never
 * change with the runtime locale (the previous implementation pinned
 * 'fr-FR', which violated the active-locale rule in the other direction).
 *
 * @param date - Date to format
 * @returns "HH:MM:SS", or "-" for an invalid date
 */
export function formatClockTime(date: Date): string {
  const time = date.getTime();
  if (!isFinite(time)) {
    return '-';
  }
  const pad = (n: number): string => String(n).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

/**
 * Emotional weight label with tone.
 *
 * Maps a -10..+10 emotional weight to an English label bucket and a
 * semantic tone (single colour authority: `utils/tones.ts`). Used by both
 * Memory Injection and Memory Extraction sections.
 *
 * @param weight Emotional weight value (-10 to +10)
 * @returns Object with label string and semantic tone
 *
 * @example
 * getEmotionalLabel(-8) // { label: "TRAUMA", tone: "alert" }
 * getEmotionalLabel(5)  // { label: "POS",    tone: "success" }
 */
export function getEmotionalLabel(weight: number): { label: string; tone: DebugTone } {
  if (weight <= -7) return { label: 'TRAUMA', tone: 'alert' };
  if (weight <= -3) return { label: 'NEG', tone: 'destructive' };
  if (weight >= 7) return { label: 'STRONG+', tone: 'success' };
  if (weight >= 3) return { label: 'POS', tone: 'success' };
  return { label: 'NEU', tone: 'neutral' };
}
