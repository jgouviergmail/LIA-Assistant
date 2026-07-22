/**
 * Excerpt builder for the history-search results list (QW-2).
 *
 * Server results are raw message content (markdown / assistant HTML). The
 * results panel shows a short, plain-text window around the FIRST match,
 * split into segments so the caller renders the match as a React `<mark>`
 * element — no HTML injection anywhere.
 */

import { findNormalizedMatches, normalizeSearchText } from '@/lib/utils';

export interface SearchExcerpt {
  /** Plain text before the match (possibly elided). */
  prefix: string;
  /** The matched original characters. */
  match: string;
  /** Plain text after the match (possibly elided). */
  suffix: string;
}

/** Ellipsis used on elided sides. */
const ELLIPSIS = '…';

/** Strip HTML tags and collapse whitespace — mirror of the FAQ stripHtml. */
function toPlainText(content: string): string {
  return content
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Build a plain-text excerpt centered on the first match of `query`.
 *
 * @param content - Raw message content (markdown/HTML allowed).
 * @param query - Raw user search term.
 * @param radius - Max characters kept on each side of the match.
 * @returns Segments to render, or null when the query does not match the
 *   plain-text form (e.g. it only matched markup that was stripped).
 */
export function buildSearchExcerpt(
  content: string,
  query: string,
  radius = 60
): SearchExcerpt | null {
  const normalizedQuery = normalizeSearchText(query.trim());
  if (!normalizedQuery) return null;

  const plain = toPlainText(content);
  const ranges = findNormalizedMatches(plain, normalizedQuery);
  if (ranges.length === 0) return null;

  const { start, end } = ranges[0];
  const prefixStart = Math.max(0, start - radius);
  const suffixEnd = Math.min(plain.length, end + radius);

  const prefix = (prefixStart > 0 ? ELLIPSIS : '') + plain.slice(prefixStart, start);
  const suffix = plain.slice(end, suffixEnd) + (suffixEnd < plain.length ? ELLIPSIS : '');

  return { prefix, match: plain.slice(start, end), suffix };
}
