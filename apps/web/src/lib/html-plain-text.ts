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

/**
 * Recognised HTML element tags emitted by the response/display layer.
 *
 * Mirrors `_HTML_TAG_RE` in `apps/api/src/domains/agents/display/plain_text.py`.
 * Detection is deliberate: blind tag-stripping would delete `"< 5 and y >"`
 * from the prose `"x < 5 and y > 3"`.
 */
const TAGS =
  'div|p|span|style|script|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th|a|strong|em|b|i|blockquote|code|pre';
const OPEN_TAG_RE = new RegExp(`<(${TAGS})\\b[^>]*>`, 'gi');
const CLOSE_TAG_RE = new RegExp(`</(${TAGS})\\s*>`, 'gi');
const VOID_TAG_RE = /<(?:br|hr|img)\b[^>]*\/?>/i;
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
export const BLOCK_RE = /<(head|style|script)\b[^>]*(?<!\/)>[\s\S]*?(?:<\/\1\s*>|$)/gi;

/**
 * Material Symbols icons render as `<span class="material-symbols-outlined">NAME</span>`,
 * where NAME is a font ligature identifier ("event", "mail") turned into a glyph
 * — never prose. Stripping tags alone would keep it, so a data card reads
 * "event Déjeuner avec Marie". Dropped whole, content included.
 *
 * Mirrors `_ICON_SPAN_RE` in `apps/api/src/domains/agents/display/plain_text.py`.
 */
export const ICON_SPAN_RE =
  /<span[^>]*class=["'][^"']*material-symbols-outlined[^"']*["'][^>]*>[^<]*<\/span\s*>/gi;

/**
 * The entities worth decoding on a client surface. Deliberately a fixed set,
 * NOT full parity with the backend's `html.unescape` — this layer is a
 * defense-in-depth net, so an exotic entity surviving verbatim is acceptable
 * where pulling in a full entity table is not.
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
 * One deliberate divergence: entities are decoded AFTER tag stripping (the
 * historical frontend order) so a message QUOTING markup as `&lt;div&gt;`
 * keeps its literal text instead of being eaten by the strip.
 *
 * A strict no-op on Markdown and plain prose (guarded by `looksLikeHtml`).
 */
export function htmlToPlainText(text: string): string {
  if (!text || !looksLikeHtml(text)) return text;
  let out = text.replace(BLOCK_RE, ' ').replace(ICON_SPAN_RE, ' ');
  // Links: keep the text only (backend preserve_links=False).
  out = out.replace(/<a\s+[^>]*>([\s\S]*?)<\/a>/gi, '$1');
  // Block structure BEFORE the generic strip — mirrors base.py steps 4-7.
  out = out.replace(/<h[1-6][^>]*>([\s\S]*?)<\/h[1-6]>/gi, '\n\n$1\n\n');
  out = out.replace(/<\/p>/gi, '\n\n');
  out = out.replace(/<\/div>/gi, '\n');
  out = out.replace(/<br\s*\/?>/gi, '\n');
  out = out.replace(/<hr\b[^>]*\/?>/gi, '\n---\n');
  out = out.replace(/<li[^>]*>/gi, '\n• ');
  out = out.replace(/<\/?[ou]l[^>]*>/gi, '\n');
  out = out.replace(/<tr[^>]*>/gi, '\n');
  out = out.replace(/<t[dh][^>]*>/gi, ' ');
  out = out.replace(/<\/t[dh]>/gi, ' | ');
  out = out.replace(/<\/?table[^>]*>/gi, '\n');
  out = out.replace(/<blockquote[^>]*>/gi, '\n> ');
  out = out.replace(/<\/blockquote>/gi, '\n');
  // ADR-177 vocabulary (absent from the backend's email-oriented set):
  out = out.replace(/<\/dt>/gi, ' : ');
  out = out.replace(/<\/(?:dd|dl|summary|details|figcaption|caption)>/gi, '\n');
  // Generic strip — remaining tags (incl. inline strong/em/span) drop to ''.
  out = out.replace(/<[^>]+>/g, '');
  for (const [entity, char] of Object.entries(ENTITIES)) {
    out = out.split(entity).join(char);
  }
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
