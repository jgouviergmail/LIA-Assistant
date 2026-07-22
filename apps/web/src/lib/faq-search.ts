/**
 * FAQ search helpers shared by the dashboard FAQ (FAQContent) and the public
 * landing FAQ page: HTML stripping for plain-text matching and accent-aware
 * highlight of query matches inside safe translation HTML.
 *
 * Extracted verbatim from FAQContent (2026-07) so the public page reuses the
 * exact same matching semantics instead of re-implementing them.
 */

import { normalizeSearchText } from '@/lib/utils';

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
 * Maps normalized positions back to original text positions.
 */
function highlightTextContent(text: string, normalizedQuery: string): string {
  if (!text) return text;

  const normalizedText = normalizeSearchText(text);

  // Find all match positions in normalized text
  const escapedQuery = normalizedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(escapedQuery, 'gi');

  const matches: Array<{ start: number; end: number }> = [];
  let match;
  while ((match = regex.exec(normalizedText)) !== null) {
    matches.push({ start: match.index, end: match.index + match[0].length });
  }

  if (matches.length === 0) return text;

  // Build mapping from original char index to normalized char index
  // NFD normalization: é (1 char) → e + ́ (2 chars), then we remove diacritics
  const originalToNormalized: number[] = [];
  let normalizedPos = 0;

  for (let i = 0; i < text.length; i++) {
    originalToNormalized.push(normalizedPos);
    const char = text[i].toLowerCase();
    const nfdChar = char.normalize('NFD');
    // Count base characters (non-combining marks) after NFD
    const baseChars = nfdChar.replace(/[̀-ͯ]/g, '').length;
    normalizedPos += baseChars;
  }
  originalToNormalized.push(normalizedPos); // End sentinel

  // Map normalized match positions to original positions
  const originalMatches: Array<{ start: number; end: number }> = [];

  for (const m of matches) {
    let origStart = 0;
    let origEnd = text.length;

    // Find original start: first i where normalizedPos[i] <= m.start < normalizedPos[i+1]
    for (let i = 0; i < text.length; i++) {
      if (originalToNormalized[i] <= m.start && originalToNormalized[i + 1] > m.start) {
        origStart = i;
        break;
      }
    }

    // Find original end: first i where normalizedPos[i] >= m.end
    for (let i = origStart; i <= text.length; i++) {
      if (originalToNormalized[i] >= m.end) {
        origEnd = i;
        break;
      }
    }

    originalMatches.push({ start: origStart, end: origEnd });
  }

  // Build highlighted string (don't escape - content is from safe translations)
  let result = '';
  let lastEnd = 0;

  for (const m of originalMatches) {
    result += text.slice(lastEnd, m.start);
    result += `<mark class="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">${text.slice(m.start, m.end)}</mark>`;
    lastEnd = m.end;
  }
  result += text.slice(lastEnd);

  return result;
}
