/**
 * FAQ search helpers shared by the dashboard FAQ (FAQContent) and the public
 * landing FAQ page: HTML stripping for plain-text matching and accent-aware
 * highlight of query matches inside safe translation HTML.
 *
 * Extracted verbatim from FAQContent (2026-07) so the public page reuses the
 * exact same matching semantics instead of re-implementing them.
 */

import { findNormalizedMatches, normalizeSearchText } from '@/lib/utils';

/** Strip HTML tags and collapse whitespace for plain-text search matching. */
export function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Highlight search query matches in text content (accent-insensitive).
 * XSS Protection: User query is escaped before being used in the highlight regex.
 * The text content (from translations) contains safe HTML and is NOT escaped.
 *
 * This function finds matches using normalized (accent-stripped) text but
 * highlights the original characters in the source text.
 */
export function highlightText(text: string, query: string): string {
  if (!query.trim()) return text;

  const normalizedQuery = normalizeSearchText(query.trim());
  if (!normalizedQuery) return text;

  // For text with HTML, we need to only highlight text nodes, not tags
  // Split by HTML tags, highlight text parts, then rejoin
  const parts = text.split(/(<[^>]*>)/);

  return parts
    .map(part => {
      // Skip HTML tags
      if (part.startsWith('<') && part.endsWith('>')) {
        return part;
      }
      // Highlight text content
      return highlightTextContent(part, normalizedQuery);
    })
    .join('');
}

/**
 * Highlight matches in plain text (no HTML tags).
 *
 * Locating the matches is delegated to `findNormalizedMatches`, the single
 * accent-aware matcher the whole search stack shares (`search-excerpt`,
 * `rehype-search-highlight`). This module used to carry a second copy of that
 * mapping — a hand-rolled O(n²) double loop over a normalized-position table —
 * which is the kind of duplicate that drifts silently: `findNormalizedMatches`
 * even documented itself as using "the same mapping the FAQ highlighter uses".
 * Their equivalence is pinned by the differential class in
 * `__tests__/faq-search.test.ts`, which is what made this collapse safe.
 */
function highlightTextContent(text: string, normalizedQuery: string): string {
  if (!text) return text;

  const matches = findNormalizedMatches(text, normalizedQuery);
  if (matches.length === 0) return text;

  // Build highlighted string. The output is made only of slices of `text`
  // (trusted translation HTML) plus the fixed <mark> wrapper — nothing the user
  // typed is ever emitted, which is what keeps this safe for the
  // dangerouslySetInnerHTML render downstream.
  let result = '';
  let lastEnd = 0;

  for (const m of matches) {
    result += text.slice(lastEnd, m.start);
    result += `<mark class="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">${text.slice(m.start, m.end)}</mark>`;
    lastEnd = m.end;
  }
  result += text.slice(lastEnd);

  return result;
}
