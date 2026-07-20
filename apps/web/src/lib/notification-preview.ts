/**
 * Plain-text previews for notification surfaces (toast descriptions).
 *
 * Assistant content is rich: an HTML document wrapped in
 * `<div class="lia-response">` when the user's display mode is `html`,
 * server-rendered data cards otherwise, Markdown in between. The chat renders
 * that through the ReactMarkdown + rehypeRaw pipeline, but a toast description
 * is plain React children — markup shows up as literal text
 * (`<div class="lia-response"><h2>…`).
 *
 * The backend already flattens the bodies it controls; this is the client-side
 * half of the same guard, covering every notification type uniformly (proactive
 * and reminder payloads keep their Markdown for the chat message and must only
 * be flattened for the preview).
 *
 * XSS note: this produces TEXT rendered as escaped React children. It is a
 * legibility helper, never a sanitizer — nothing here may be fed to
 * `dangerouslySetInnerHTML`.
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
function looksLikeHtml(text: string): boolean {
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
 * The closing tag is OPTIONAL (`|$`), and that is the point: this surface
 * truncates, so a `<style>` severed mid-rule keeps no `</style>`. Requiring the
 * pair let `TAG_RE` strip the marker and leave the raw CSS as text
 * ("body{color:red;font-size:12px}" in a toast).
 *
 * `(?<!\/)` rejects a self-closing `<script src="x"/>`, whose lazy body would
 * otherwise find no closing tag and swallow the rest of the document. The `\1`
 * backreference stops a `<style>` from being closed by a `</script>`.
 */
const BLOCK_RE = /<(head|style|script)\b[^>]*(?<!\/)>[\s\S]*?(?:<\/\1\s*>|$)/gi;

/**
 * Material Symbols icons render as `<span class="material-symbols-outlined">NAME</span>`,
 * where NAME is a font ligature identifier ("event", "mail") turned into a glyph
 * — never prose. Stripping tags alone would keep it, so a data card reads
 * "event Déjeuner avec Marie". Dropped whole, content included.
 *
 * Mirrors `_ICON_SPAN_RE` in `apps/api/src/domains/agents/display/plain_text.py`.
 */
const ICON_SPAN_RE =
  /<span[^>]*class=["'][^"']*material-symbols-outlined[^"']*["'][^>]*>[^<]*<\/span\s*>/gi;
const TAG_RE = /<[^>]+>/g;
const WHITESPACE_RE = /\s+/g;

/**
 * The entities worth decoding on a preview surface. Deliberately a fixed set,
 * NOT full parity with the backend's `html.unescape` — this layer is a
 * defense-in-depth net (scheduled-action bodies arrive already flattened, and
 * proactive/reminder bodies are Markdown), so an exotic entity surviving
 * verbatim is acceptable where pulling in a full entity table is not.
 */
const ENTITIES: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
};

/** Character budget for a toast description before ellipsizing. */
export const NOTIFICATION_PREVIEW_MAX_LENGTH = 100;

/**
 * Flatten rich content to a single-line plain-text preview.
 *
 * A no-op on Markdown and plain prose, so it is safe to apply to every
 * notification type.
 *
 * @param text - Notification content, possibly HTML.
 * @param maxLength - Character budget; omit to flatten without truncating.
 * @returns Single-line plain text, ellipsized when it exceeds the budget.
 */
export function toPlainPreview(text: string, maxLength?: number): string {
  if (!text) return '';

  let out = text;
  if (looksLikeHtml(out)) {
    // Drop <head>/<style>/<script> bodies and icon spans entirely — their
    // content is CSS/JS/metadata or a font ligature name, never prose.
    out = out.replace(BLOCK_RE, ' ').replace(ICON_SPAN_RE, ' ').replace(TAG_RE, ' ');
    for (const [entity, char] of Object.entries(ENTITIES)) {
      out = out.split(entity).join(char);
    }
  }

  out = out.replace(WHITESPACE_RE, ' ').trim();
  if (maxLength === undefined || out.length <= maxLength) return out;
  return `${out.slice(0, maxLength)}...`;
}
