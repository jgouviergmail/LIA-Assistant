/**
 * rehype-search-highlight — wrap history-search matches in `<mark>` (QW-2).
 *
 * WHY THIS EXISTS
 * ---------------
 * The FAQ search highlights via `dangerouslySetInnerHTML`, which is reserved
 * for app-controlled static content. Chat bubbles render LLM output through
 * the sanitized ReactMarkdown pipeline — the only XSS-conformant way to
 * highlight there is a hast-level transform running AFTER the sanitize
 * boundary, exactly like `rehype-math-in-text`.
 *
 * Matching is accent- and case-insensitive (same `normalizeSearchText`
 * semantics as the client-side message filter and the server's
 * `unaccent(ILIKE)`), while the ORIGINAL characters are what gets wrapped —
 * searching "reunion" marks the literal "RÉUNION" text.
 *
 * SCOPE / CONTRACT
 * ----------------
 * - Plain `indexOf` matching on the normalized text (no regex — user input is
 *   never interpreted as a pattern).
 * - Text inside `<code>`, `<pre>`, `<script>`, `<style>`, `<mark>` and any
 *   element carrying a math/KaTeX class is left untouched: marks inside code
 *   would break Prism re-tokenization, and marks inside KaTeX output would
 *   corrupt formula markup. Place the plugin AFTER `rehypeKatex`.
 *
 * SECURITY
 * --------
 * Reads only already-sanitized text nodes and emits a fixed-class `<mark>`
 * wrapping a plain text child — the XSS posture is identical to
 * `rehype-math-in-text`. Types are declared locally (structural subset of
 * hast) to keep the plugin dependency-free.
 */

import { findNormalizedMatches, normalizeSearchText } from '@/lib/utils';

interface TextNode {
  type: 'text';
  value: string;
}

interface ElementNode {
  type: 'element';
  tagName: string;
  properties?: Record<string, unknown> | null;
  children: HastNode[];
}

type HastNode = TextNode | ElementNode | { type: string; children?: HastNode[]; value?: string };

/** Fixed class rendered by the chat stylesheet (light + dark variants). */
export const SEARCH_MARK_CLASS = 'lia-search-mark';

/** Tags whose text content must never be highlighted. */
const SKIP_TAGS = new Set(['code', 'pre', 'script', 'style', 'mark']);

/** Classes marking generated math markup that a `<mark>` would corrupt. */
const SKIP_CLASSES = [
  'math-inline',
  'math-display',
  'language-math',
  'katex',
  // Material Symbols icons: the text is a font LIGATURE name ("event",
  // "mail"), not prose — a <mark> inserted mid-text breaks the ligature and
  // displays the raw word highlighted (ADR-177).
  'material-symbols-outlined',
];

function isElement(n: HastNode): n is ElementNode {
  return n.type === 'element' && typeof (n as ElementNode).tagName === 'string';
}

function isText(n: HastNode): n is TextNode {
  return n.type === 'text' && typeof (n as TextNode).value === 'string';
}

function isSkippable(el: ElementNode): boolean {
  if (SKIP_TAGS.has(el.tagName)) return true;
  const cn = el.properties?.className;
  const classes = Array.isArray(cn)
    ? cn.map(String)
    : typeof cn === 'string'
      ? cn.split(/\s+/)
      : [];
  return SKIP_CLASSES.some(m => classes.some(c => c === m || c.startsWith('katex')));
}

/** Split a text value into text/mark nodes around every match, or null when none. */
function highlightValue(value: string, normalizedQuery: string): HastNode[] | null {
  const ranges = findNormalizedMatches(value, normalizedQuery);
  if (ranges.length === 0) return null;

  const out: HastNode[] = [];
  let cursor = 0;
  for (const { start, end } of ranges) {
    if (start > cursor) out.push({ type: 'text', value: value.slice(cursor, start) });
    out.push({
      type: 'element',
      tagName: 'mark',
      properties: { className: [SEARCH_MARK_CLASS] },
      children: [{ type: 'text', value: value.slice(start, end) }],
    });
    cursor = end;
  }
  if (cursor < value.length) out.push({ type: 'text', value: value.slice(cursor) });
  return out;
}

function transform(node: HastNode, normalizedQuery: string, skip: boolean): void {
  const children = (node as ElementNode).children;
  if (!Array.isArray(children)) return;

  const next: HastNode[] = [];
  for (const child of children) {
    if (isText(child)) {
      const replaced = skip ? null : highlightValue(child.value, normalizedQuery);
      if (replaced) next.push(...replaced);
      else next.push(child);
    } else if (isElement(child)) {
      transform(child, normalizedQuery, skip || isSkippable(child));
      next.push(child);
    } else {
      next.push(child);
    }
  }

  (node as ElementNode).children = next;
}

/**
 * rehype plugin factory. Place AFTER `rehypeKatex` (last in the pipeline) so
 * generated math markup is skipped, never rewritten.
 *
 * @param options.query - Raw user search term (normalized internally).
 */
export default function rehypeSearchHighlight(options: { query: string }) {
  const normalizedQuery = normalizeSearchText(options.query.trim());
  return (tree: { type: string; children?: HastNode[]; [key: string]: unknown }): void => {
    if (!normalizedQuery) return;
    transform(tree as HastNode, normalizedQuery, false);
  };
}
