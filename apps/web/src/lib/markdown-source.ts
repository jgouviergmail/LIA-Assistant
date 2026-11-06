/**
 * What a message becomes before the Markdown parser reads it.
 *
 * The chat renders Markdown and the HTML LIA writes through ONE parser, and
 * CommonMark was not written for the second: what follows are the string
 * repairs that keep an HTML answer whole. Every one of them is LIA's to apply
 * to LIA's own output. A person's message reaches the parser as they typed it
 * (`remark-literal-html.ts` then keeps what looks like a tag as text).
 *
 * Every rule here runs on each streamed token, so each is linear by
 * construction (ADR-326): a span stops at its terminator or at the end of the
 * text, and a tag's attributes never cross another `<`.
 */

import { protectReferencedDollars } from './markdown-dollars';

/** Block-level HTML open tag at the very start — marks an HTML response. */
const HTML_BLOCK_START_RE =
  /^<(?:div|section|article|header|main|aside|nav|figure|details|h[1-6]|p|ul|ol|table|blockquote)\b/i;

function isHtmlAnswer(text: string): boolean {
  return HTML_BLOCK_START_RE.test(text.trimStart());
}

/**
 * A fence, read first so that a `<pre>` it quotes stays quoted, or a `<pre>`:
 * its opening tag (group 1) and what follows up to its end (group 2).
 */
const FENCE_OR_PRE_RE =
  /```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|(<pre\b[^<>]*>)([\s\S]*?(?:<\/pre\s*>|$))/gi;

/**
 * Make every `<pre>` of an HTML answer one line for CommonMark.
 *
 * A `lia-response` answer opens one HTML block, and CommonMark ends such a
 * block at its first blank line, wherever it stands. Measured on production
 * (2026-11-04): a blank line between two functions of a `<pre>` turned the rest
 * of the code into paragraphs, the last of which then left the `<code>` when
 * the HTML parser met `</code></pre>`. 24 of the 48 stored code blocks lost
 * their indentation, their blank lines and their tail, and the Copy button
 * handed that over. `&#10;` is a line break to the HTML parser and no line at
 * all to CommonMark, so the code comes out byte for byte. An unclosed `<pre>`
 * runs to the end of the text: it is one being streamed.
 */
function protectPreformatted(text: string): string {
  if (!isHtmlAnswer(text)) return text;
  return text.replace(FENCE_OR_PRE_RE, (block, open: string | undefined, body: string) =>
    open === undefined ? block : open + body.replace(/\r?\n/g, '&#10;')
  );
}

/**
 * De-indent the structural lines of an HTML response so CommonMark never
 * mistakes a pretty-printed tag for an indented code block.
 *
 * Measured on prod (2026-07-29): the model intermittently pretty-prints its
 * `<div class="lia-response">` card with 4-space-indented tag lines AND blank
 * lines between blocks. A CommonMark HTML block (type 6) ends at the first
 * blank line; the next 4-space-indented `<h2>` is then read as an INDENTED
 * CODE block, so the rest of the card renders as raw `<h2>…` TEXT. Two
 * consecutive replies proved the asymmetry: identical wrapper, column-0 tags
 * rendered, 4-space-indented tags did not.
 *
 * Stripping the leading indentation of every structural line puts each block
 * tag back at column 0, where it (re)starts an HTML block. Whitespace between
 * block-level tags is insignificant, so this changes PARSING only, never the
 * rendered card. Lines inside <pre>/<code> keep their indentation (there,
 * leading whitespace is meaningful). Scoped to content that STARTS with a
 * block-level HTML tag, so a Markdown answer's legitimate indented code block
 * is never touched.
 */
function stripHtmlBlockIndent(text: string): string {
  if (!isHtmlAnswer(text)) return text;
  let protectedDepth = 0;
  return text
    .split('\n')
    .map(line => {
      const out = protectedDepth === 0 ? line.replace(/^[ \t]+/, '') : line;
      const opens = (line.match(/<(?:pre|code)\b/gi) ?? []).length;
      const closes = (line.match(/<\/(?:pre|code)>/gi) ?? []).length;
      protectedDepth = Math.max(0, protectedDepth + opens - closes);
      return out;
    })
    .join('\n');
}

/**
 * Sanitize malformed HTML tags that contain emojis.
 * LLMs sometimes generate tags like `<li📧>` instead of `<li>📧`.
 * This regex fixes common patterns to prevent createElement errors.
 */
function sanitizeMalformedTags(text: string): string {
  // Fix tags with emojis attached: <li📧 -> <li>📧, </li📧> -> </li>
  // Matches: < followed by valid tag name, then emoji(s), then optional attributes/closing
  // Unicode emoji ranges: \u{1F300}-\u{1F9FF} covers most emojis
  return text.replace(
    /<(\/?)([a-zA-Z][a-zA-Z0-9]*)([\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]+)([^>]*)>/gu,
    (_, slash, tag, emoji, rest) => `<${slash}${tag}${rest}>${emoji}`
  );
}

// Regions where `$` must be left untouched: fenced code blocks, inline code
// (single/double backtick), `$$…$$` display math, and the code of an HTML
// answer. Escaping `$` inside a code span would surface a literal backslash
// (markdown does not unescape inside code), display math is already handled by
// remark-math, and a regex such as `/\(a\)/` in a `<pre>` is no formula.
const PROTECTED_SPAN_RE =
  /(```[\s\S]*?```|~~~[\s\S]*?~~~|``[\s\S]*?``|`[^`\n]*`|\$\$[\s\S]*?\$\$|<(?:pre|code)\b[^<>]*>[\s\S]*?(?:<\/(?:pre|code)\s*>|$))/gi;

const MATH_FENCE_OPEN_RE = /```(?:math|latex)\b[^\n]*\n/gi;
const FENCE_CLOSE_RE = /```[ \t]*(?=\n|$)/g;

/**
 * Turn each ```` ```math ```` / ```` ```latex ```` fence into a `$$` block.
 *
 * A scan rather than one regex, like {@link convertDelimited}: an opener with no
 * closer ends the search instead of re-reading the rest of the text for every
 * later opener (ADR-326). This runs on each streamed token.
 */
function convertMathFences(text: string): string {
  let out = '';
  let at = 0;
  for (;;) {
    MATH_FENCE_OPEN_RE.lastIndex = at;
    const open = MATH_FENCE_OPEN_RE.exec(text);
    if (!open) return out + text.slice(at);
    const body = open.index + open[0].length;
    FENCE_CLOSE_RE.lastIndex = body;
    const close = FENCE_CLOSE_RE.exec(text);
    if (!close) return out + text.slice(at);
    const formula = text.slice(body, close.index).trim();
    out += `${text.slice(at, open.index)}\n$$\n${formula}\n$$\n`;
    at = close.index + close[0].length;
  }
}

/**
 * Rewrite each `open … close` pair as a formula between `delimiter`s.
 *
 * Measured 2026-11-04: the regex this replaces was quadratic on unmatched
 * openers (`\( ` repeated: ×17 for ×4 the text) and killed the worker on one
 * opener followed by blanks, so a hostile text froze the tab on every token.
 * Each search here starts where the last one stopped.
 *
 * @param text - The prose, free of code spans.
 * @param open - The opening notation.
 * @param close - The closing notation.
 * @param delimiter - What replaces both.
 * @returns The prose, its pairs rewritten and an unmatched opener left as typed.
 */
function convertDelimited(text: string, open: string, close: string, delimiter: string): string {
  let out = '';
  let at = 0;
  for (;;) {
    const start = text.indexOf(open, at);
    const end = start < 0 ? -1 : text.indexOf(close, start + open.length);
    if (end < 0) return out + text.slice(at);
    const formula = text.slice(start + open.length, end).trim();
    out += text.slice(at, start) + delimiter + formula + delimiter;
    at = end + close.length;
  }
}

/**
 * Normalize every math notation an LLM emits into remark-math delimiters, so
 * a formula renders regardless of the style the model picked:
 *   - ```` ```math ```` / ```` ```latex ```` fenced block → `$$…$$` (display)
 *   - `\[ … \]` → `$$…$$` (display)
 *   - `\( … \)` → `$…$`  (inline)
 * Without this, a formula the model wrapped in a ```` ```latex ```` block
 * rendered as a literal code block instead of math. `\[`/`\(` conversion
 * skips code spans/blocks (so a regex `\(` in a code sample is preserved);
 * the fenced-block conversion only targets the `math`/`latex` languages, so
 * ```` ```python ```` etc. stay code.
 */
function normalizeMathDelimiters(text: string): string {
  // 1) Fenced ```math / ```latex → $$…$$ (run first: otherwise these blocks
  //    would be treated as protected code spans below).
  const out = convertMathFences(text);

  if (!out.includes('\\[') && !out.includes('\\(')) return out;

  // 2) \[…\] and \(…\) outside code / display-math regions.
  return out
    .split(PROTECTED_SPAN_RE)
    .map((part, i) => {
      if (i % 2 === 1) return part; // protected span (code or $$…$$)
      return convertDelimited(convertDelimited(part, '\\[', '\\]', '$$'), '\\(', '\\)', '$');
    })
    .join('');
}

/**
 * The text the Markdown parser reads for a message.
 *
 * @param content - The message as stored or streamed.
 * @param isUser - Whether a person typed it: only LIA's own output is repaired.
 * @returns The text to parse. Canonicalizes the math notations of both authors
 *   to `$`/`$$`; dollar delimiters then become KaTeX markers at the hast level
 *   (`rehypeMathInText`), which — unlike remark-math — also sees math inside
 *   the raw HTML the assistant emits. A REFERENCED dollar (`&#36;`, a card value
 *   drawn as itself) is never a delimiter: it waits as a marker until
 *   `rehypeRestoreDollars`.
 */
export function prepareMarkdownSource(content: string, isUser: boolean): string {
  const structured = isUser
    ? content
    : sanitizeMalformedTags(stripHtmlBlockIndent(protectPreformatted(content)));
  return normalizeMathDelimiters(protectReferencedDollars(structured));
}
