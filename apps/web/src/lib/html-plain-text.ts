/**
 * Shared HTML detection + flattening for assistant content (ADR-177).
 *
 * Owns the client-side "is this really HTML?" detection and the multi-line
 * flattener. `notification-preview.ts` builds its single-line toast previews
 * on top; `message-clipboard.ts` uses the multi-line form for the clipboard
 * text/plain flavor, the native share sheet and the .md export.
 *
 * XSS note: everything here produces TEXT rendered as escaped React children
 * or written to the clipboard. It is a legibility helper, never a sanitizer —
 * nothing may be fed to `dangerouslySetInnerHTML`.
 */

import { decodeReference } from './markdown-references';

/**
 * Recognised HTML element tags emitted by the response/display layer.
 *
 * Mirrors `_HTML_TAG_RE` in `apps/api/src/domains/agents/display/plain_text.py`.
 * Detection is deliberate: blind tag-stripping would delete `"< 5 and y >"`
 * from the prose `"x < 5 and y > 3"`.
 */
const TAGS =
  'div|p|span|style|script|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th|a|strong|em|b|i|blockquote|code|pre';
const OPEN_TAG_RE = new RegExp(`<(${TAGS})\\b[^<>]*>`, 'gi');
const CLOSE_TAG_RE = new RegExp(`</(${TAGS})\\s*>`, 'gi');
const VOID_TAG_RE = /<(?:br|hr|img)\b[^<>]*\/?>/i;
const ATTR_TAG_RE = new RegExp(`<(?:${TAGS})\\s+[a-z-]+\\s*=\\s*["']`, 'i');

/**
 * Detect genuine markup — a lone `<tag` is not enough.
 *
 * Single-letter element names collide with ordinary comparisons and generics,
 * so `"if x<a and b>c"` would be detected as HTML and mutilated into
 * `"if xc"`. Markup is accepted on a matched tag pair, a void element, or a
 * tag carrying an attribute (which also covers a truncated document).
 */
export function looksLikeHtml(text: string): boolean {
  const opened = new Set(Array.from(text.matchAll(OPEN_TAG_RE), m => m[1].toLowerCase()));
  if (opened.size > 0) {
    for (const [, name] of text.matchAll(CLOSE_TAG_RE)) {
      if (opened.has(name.toLowerCase())) return true;
    }
  }
  return VOID_TAG_RE.test(text) || ATTR_TAG_RE.test(text);
}

/**
 * Elements whose content is never prose: CSS, JS, document metadata.
 *
 * Mirrors `_BLOCK_ELEMENT_RE` in `apps/api/src/domains/agents/display/components/base.py`
 * — the two must stay in step, a preview can be built on either side.
 *
 * The closing tag is OPTIONAL (`|$`), and that is the point: preview surfaces
 * truncate, so a `<style>` severed mid-rule keeps no `</style>`. Requiring the
 * pair let tag stripping remove the marker and leave the raw CSS as text
 * ("body{color:red;font-size:12px}" in a toast).
 *
 * `(?<!\/)` rejects a self-closing `<script src="x"/>`, whose lazy body would
 * otherwise find no closing tag and swallow the rest of the document. The `\1`
 * backreference stops a `<style>` from being closed by a `</script>`.
 */
export const BLOCK_RE = /<(head|style|script)\b[^<>]*(?<!\/)>[\s\S]*?(?:<\/\1\s*>|$)/gi;

/**
 * Material Symbols icons render as `<span class="material-symbols-outlined">NAME</span>`,
 * where NAME is a font ligature identifier ("event", "mail") turned into a glyph
 * — never prose. Stripping tags alone would keep it, so a data card reads
 * "event Déjeuner avec Marie". Dropped whole, content included.
 *
 * Mirrors `_ICON_SPAN_RE` in `apps/api/src/domains/agents/display/plain_text.py`.
 */
export const ICON_SPAN_RE =
  /<span[^<>]*class=["'][^"']*material-symbols-outlined[^"']*["'][^<>]*>[^<]*<\/span\s*>/gi;

/**
 * The named entities worth decoding on a client surface. Deliberately a fixed
 * set, NOT full parity with the backend's `html.unescape` — an exotic named
 * entity surviving verbatim is acceptable where pulling in a full entity table
 * is not. Numeric references are all decoded (`decodeReference`): a card's
 * escaped apostrophe is `&#x27;`, which a voice read out as typed.
 */
export const ENTITIES: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
};

/** A reference `htmlToPlainText` decodes: a numeric one, or a name of `ENTITIES`. */
const REFERENCE_RE = /&(?:#([0-9]{1,7})|#[xX]([0-9A-Fa-f]{1,6})|(nbsp|amp|lt|gt|quot|apos));/g;

/**
 * Flatten rich assistant HTML to readable MULTI-LINE plain text.
 *
 * Client-side mirror of the backend's `html_to_text`
 * (`display/components/base.py`, `preserve_links=False` semantics): same
 * bullets ("• "), same block spacing (one empty line between blocks, `<hr>` →
 * "---"), same inline-tag handling (stripped to '', no injected space), same
 * whitespace normalization (≤1 empty line, per-line trim). Extended for the
 * ADR-177 vocabulary the email-oriented backend set lacks: dl/dt/dd
 * ("key : value"), details/summary, caption/figcaption.
 *
 * Entities are decoded AFTER tag stripping, in ONE pass — the server's
 * order too since review 14: a message QUOTING markup as `&lt;div&gt;` keeps
 * its literal text instead of being eaten by the strip, and `&amp;lt;` reads
 * `&lt;`, never `<` (one entity after the other decoded it twice).
 *
 * A strict no-op on Markdown and plain prose (guarded by `looksLikeHtml`).
 */
export function htmlToPlainText(text: string): string {
  if (!text || !looksLikeHtml(text)) return text;
  let out = text.replace(BLOCK_RE, ' ').replace(ICON_SPAN_RE, ' ');
  // Links: keep the text only (backend preserve_links=False) — each tag on
  // its own, as the server does: paired lazily, every unclosed « <a »
  // rescanned the text to its end.
  out = out.replace(/<\/?a\b[^<>]*>/gi, '');
  // Block structure BEFORE the generic strip — base.py steps 4-7, rule for
  // rule and in their order: the voice twins read a stray « < » of the text
  // the same way only if every tag is gone at the same step.
  out = out.replace(/<\/?h[1-6]\b[^<>]*>/gi, '\n\n');
  out = out.replace(/<\/p>/gi, '\n\n');
  out = out.replace(/<p[^<>]*>/gi, '');
  out = out.replace(/<\/div>/gi, '\n');
  out = out.replace(/<div[^<>]*>/gi, '');
  out = out.replace(/<br\s*\/?>/gi, '\n');
  out = out.replace(/<hr\s*\/?>/gi, '\n---\n');
  out = out.replace(/<li[^<>]*>/gi, '\n• ');
  out = out.replace(/<\/li>/gi, '');
  out = out.replace(/<\/?[ou]l[^<>]*>/gi, '\n');
  out = out.replace(/<tr[^<>]*>/gi, '\n');
  out = out.replace(/<\/tr>/gi, '');
  out = out.replace(/<t[dh][^<>]*>/gi, ' ');
  out = out.replace(/<\/t[dh]>/gi, ' | ');
  out = out.replace(/<\/?table[^<>]*>/gi, '\n');
  out = out.replace(/<\/?t(?:body|head)[^<>]*>/gi, '');
  out = out.replace(/<blockquote[^<>]*>/gi, '\n> ');
  out = out.replace(/<\/blockquote>/gi, '\n');
  // The response vocabulary (ADR-177), base.py step 7b:
  out = out.replace(/<\/dt>/gi, ' : ');
  out = out.replace(/<\/(?:dd|dl|summary|details|figcaption|caption)>/gi, '\n');
  // Two adjacent spans (a stat's value and its label) keep a space between
  // them, or « 0créneau » is what a voice reads (mirrors base.py step 7b).
  out = out.replace(/<\/span>\s*(?=<span)/gi, ' ');
  // Inline emphasis tags drop BEFORE the generic strip (base.py step 8): a
  // stray « < » of the text would otherwise run to the next tag's « > » and
  // take the words between with it, where the server's twin keeps them.
  out = out.replace(/<\/?(?:b|strong|i|em|u|s|strike)[^<>]*>/gi, '');
  // Generic strip — remaining tags (incl. span) drop to ''; a tag never
  // holds a « < », so a run of unclosed ones is read once.
  out = out.replace(/<[^<>]+>/g, '');
  out = out.replace(
    REFERENCE_RE,
    (whole: string, decimal?: string, hexadecimal?: string, name?: string) =>
      name !== undefined
        ? ENTITIES[`&${name};`]
        : (decodeReference(decimal, hexadecimal, undefined) ?? whole)
  );
  // Whitespace normalization — mirrors base.py step 10.
  out = out.replace(/[ \t]+/g, ' ');
  out = out.replace(/\n{3,}/g, '\n\n');
  const lines = out.split('\n').map(line => line.trim());
  const cleaned: string[] = [];
  let previousEmpty = false;
  for (const line of lines) {
    if (line) {
      cleaned.push(line);
      previousEmpty = false;
    } else if (!previousEmpty) {
      cleaned.push(line);
      previousEmpty = true;
    }
  }
  return cleaned.join('\n').trim();
}
