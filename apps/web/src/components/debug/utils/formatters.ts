/**
 * Formatters for Debug Panel
 *
 * Specific utilities for formatting values displayed in the debug panel.
 * Reuses existing functions from @/lib/format when possible.
 */

import { formatNumber as libFormatNumber, formatEuro as libFormatEuro } from '@/lib/format';

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
 * formatDuration(1250) // "1.2s"
 * formatDuration(450) // "450ms"
 * formatDuration(1250, false) // "1.2"
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
 * Formats a score with confidence badge
 *
 * @param score - Score (0-1)
 * @param confidence - Confidence level ('high', 'medium', 'low')
 * @returns Object with formatted score and color
 *
 * @example
 * formatScoreWithConfidence(0.85, 'high')
 * // { text: "85%", color: "green" }
 */
export function formatScoreWithConfidence(
  score: number,
  confidence: 'high' | 'medium' | 'low'
): {
  text: string;
  color: 'green' | 'yellow' | 'red';
} {
  const text = formatPercent(score);

  const colorMap: Record<typeof confidence, 'green' | 'yellow' | 'red'> = {
    high: 'green',
    medium: 'yellow',
    low: 'red',
  };

  return {
    text,
    color: colorMap[confidence],
  };
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
 * Formats a size in bytes with units
 *
 * @param bytes - Size in bytes
 * @returns Formatted string (e.g., "1.2 KB", "3.4 MB")
 *
 * @example
 * formatBytes(1024) // "1.0 KB"
 * formatBytes(1536) // "1.5 KB"
 * formatBytes(1048576) // "1.0 MB"
 * formatBytes(500) // "500 B"
 */
export function formatBytes(bytes: number): string {
  if (typeof bytes !== 'number' || !isFinite(bytes)) {
    return '-';
  }

  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
}

/**
 * Formats an ISO timestamp as relative time
 *
 * @param timestamp - ISO timestamp or Date
 * @returns Relative time string (e.g., "2s ago", "1m ago")
 *
 * @example
 * formatTimeAgo(new Date(Date.now() - 2000)) // "2s ago"
 * formatTimeAgo(new Date(Date.now() - 65000)) // "1m ago"
 */
export function formatTimeAgo(timestamp: Date | string): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  } catch {
    return '-';
  }
}
