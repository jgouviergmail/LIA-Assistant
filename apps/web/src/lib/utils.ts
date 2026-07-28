import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Google image domains that need proxying for COEP: require-corp compatibility.
 */
export const GOOGLE_IMAGE_DOMAINS = [
  'lh3.googleusercontent.com',
  'lh4.googleusercontent.com',
  'lh5.googleusercontent.com',
  'lh6.googleusercontent.com',
];

/**
 * Convert a Google image URL to use our proxy endpoint.
 * This is needed for COEP: require-corp compatibility on Safari iOS.
 *
 * Google's lh3.googleusercontent.com doesn't send CORS headers,
 * so we proxy the image through our backend.
 *
 * @param url - Original image URL
 * @returns Proxied URL if it's a Google image, original URL otherwise
 */
export function proxyGoogleImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;

  try {
    const parsed = new URL(url);
    if (GOOGLE_IMAGE_DOMAINS.includes(parsed.hostname)) {
      // Use the auth proxy endpoint
      return `/api/v1/auth/profile-image-proxy?url=${encodeURIComponent(url)}`;
    }
  } catch {
    // Invalid URL, return as-is
  }

  return url;
}

/**
 * Generate a UUID that works in both secure (HTTPS) and insecure (HTTP) contexts.
 * crypto.randomUUID() only works in secure contexts (HTTPS or localhost).
 * This fallback uses crypto.getRandomValues() which works everywhere.
 */
export function generateUUID(): string {
  // Use native crypto.randomUUID if available (secure context)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Fallback for insecure contexts (HTTP on non-localhost)
  // Uses crypto.getRandomValues() which is available in all modern browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15) >> (c === 'x' ? 0 : 3);
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/**
 * Typographic characters folded to the form a keyboard produces.
 *
 * Stripping diacritics is not enough: the translations mix the curly apostrophe
 * U+2019 with the ASCII one (measured 2026-07-28 across the six locales — 212
 * curly in `fr`, 94 in `it`, 16 in `en`), and French typography inserts no-break
 * spaces before double punctuation. A reader types `'` and a plain space, so
 * `settings.security.auth.description` — "application d’authentification" —
 * could not be found by searching "d'authentification".
 *
 * Every entry replaces ONE code point with ONE code point. That is a hard
 * constraint, not a coincidence: `findNormalizedMatches` maps normalized offsets
 * back to original ones by summing `normalizeSearchText(char).length`, so the
 * three highlighters built on it stay exact only while folding preserves length.
 * Ligature folding (`ß`→`ss`, `œ`→`oe`) is deliberately NOT done here for that
 * reason — it would need its own evidence and its own mapping proof.
 */
const SEARCH_FOLDINGS: ReadonlyArray<readonly [RegExp, string]> = [
  // Right/left single quotation mark, modifier letter apostrophe.
  [/[‘’ʼ]/g, "'"],
  // No-break space, narrow no-break space.
  [/[  ]/g, ' '],
];

/**
 * Normalize text for search: lowercase, strip accents, fold typography.
 * Useful for case-insensitive, accent-insensitive search.
 *
 * The single matcher of the whole search stack — FAQ, search excerpts, markdown
 * highlighting, chat history, slash commands and the settings search all go
 * through it, so any change here must keep one code point per code point.
 *
 * @param text - Text to normalize
 * @returns Normalized text (lowercase, no accents, keyboard-form punctuation)
 *
 * @example
 * normalizeSearchText('Café') // 'cafe'
 * normalizeSearchText('Gérard') // 'gerard'
 * normalizeSearchText('Ñoño') // 'nono'
 * normalizeSearchText('d’authentification') // "d'authentification"
 */
export function normalizeSearchText(text: string): string {
  const stripped = text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, ''); // Remove diacritical marks
  return SEARCH_FOLDINGS.reduce(
    (folded, [pattern, replacement]) => folded.replace(pattern, replacement),
    stripped
  );
}

/**
 * Find every occurrence of an already-normalized query inside `text`,
 * returned as ORIGINAL-text index ranges (QW-2 history search).
 *
 * Matching happens on the `normalizeSearchText` form while the ranges map
 * back to the original characters \u2014 searching "reunion" locates the literal
 * "R\u00c9UNION". Plain `indexOf` matching: the query is never a pattern.
 *
 * @param text - Original text to scan.
 * @param normalizedQuery - Query already passed through `normalizeSearchText`.
 * @returns Non-overlapping `[start, end)` ranges into `text`, in order.
 */
export function findNormalizedMatches(
  text: string,
  normalizedQuery: string
): Array<{ start: number; end: number }> {
  if (!normalizedQuery) return [];
  const normalized = normalizeSearchText(text);
  if (!normalized.includes(normalizedQuery)) return [];

  // Original char index \u2192 normalized index (\u00e9 contributes one normalized char,
  // combining marks contribute zero). Same mapping the FAQ highlighter uses.
  const map: number[] = [];
  let normalizedPos = 0;
  for (let i = 0; i < text.length; i++) {
    map.push(normalizedPos);
    normalizedPos += normalizeSearchText(text[i]).length;
  }
  map.push(normalizedPos); // end sentinel

  const toOriginalStart = (ns: number): number => {
    for (let i = 0; i < text.length; i++) if (map[i + 1] > ns) return i;
    return text.length;
  };
  const toOriginalEnd = (ne: number): number => {
    for (let i = 0; i < text.length; i++) if (map[i] >= ne) return i;
    return text.length;
  };

  const ranges: Array<{ start: number; end: number }> = [];
  let searchFrom = 0;
  for (;;) {
    const ns = normalized.indexOf(normalizedQuery, searchFrom);
    if (ns === -1) break;
    const ne = ns + normalizedQuery.length;
    ranges.push({ start: toOriginalStart(ns), end: toOriginalEnd(ne) });
    searchFrom = ne;
  }
  return ranges;
}
