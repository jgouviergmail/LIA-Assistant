/**
 * Clickable FAQ examples (W1) — turning written phrases into a rail to the chat.
 *
 * The FAQ answers contain hundreds of ready-made instructions addressed to LIA,
 * authored and translated across six languages, rendered as inert italics. The
 * `?draft=` prefill rail already exists everywhere else in the product — the
 * onboarding examples, the briefing cards, the open-loop entries — but not on
 * the very page whose purpose is to show what LIA can do.
 *
 * ## What counts as a command
 *
 * NOT every `<em>`. Measured over the six locales: ~2 700 `<em>` in total, of
 * which 2 079 are preceded by a bullet. Those are the commands. The rest is
 * ordinary emphasis inside prose — "le premier", "mon frère", "la semaine
 * dernière" — and rendering those as buttons would be nonsense.
 *
 * ## Why splitting rather than post-processing the DOM
 *
 * FAQ answers are rendered through `dangerouslySetInnerHTML`, which the repo
 * charter allows for content compiled from the repository. Rather than attach
 * handlers to the produced DOM (imperative, fragile, invisible to React), the
 * answer is split into segments: the surrounding HTML keeps its existing
 * rendering path unchanged, and each command becomes a real React `<button>`
 * whose text is auto-escaped as children. The XSS posture is therefore strictly
 * unchanged, and the interactive parts are ordinary React elements — focusable,
 * nameable, testable.
 */

/** One piece of a FAQ answer. */
export type FaqSegment = { kind: 'html'; html: string } | { kind: 'example'; text: string };

/**
 * A bulleted instruction: a bullet, optional spaces, an optional opening quote
 * of any locale's flavour, then the emphasised phrase.
 *
 * The bullet and the quotes stay in the surrounding HTML — only the `<em>…</em>`
 * span is lifted out, so the rendered answer looks exactly as before.
 */
const BULLETED_EXAMPLE = /[•]\s*[«"“]?\s*<em>(.*?)<\/em>/g;

/** Entities that actually occur in the corpus, plus the unavoidable `&amp;`. */
const ENTITIES: ReadonlyArray<[RegExp, string]> = [
  [/&quot;/g, '"'],
  [/&#39;|&apos;/g, "'"],
  [/&laquo;/g, '«'],
  [/&raquo;/g, '»'],
  [/&nbsp;/g, ' '],
  [/&lt;/g, '<'],
  [/&gt;/g, '>'],
  // `&amp;` LAST: decoding it first would let "&amp;quot;" become a quote.
  [/&amp;/g, '&'],
];

/**
 * Decode the entities of an authored phrase.
 *
 * The text goes into the chat composer, so `&#39;` must reach the model as an
 * apostrophe, not as five literal characters. Done with an explicit table
 * rather than by round-tripping through the DOM: this module is pure and runs
 * in tests and on the server as well as in the browser.
 */
function decodeEntities(raw: string): string {
  return ENTITIES.reduce((text, [pattern, char]) => text.replace(pattern, char), raw);
}

/**
 * Split a FAQ answer into renderable segments.
 *
 * Args:
 *   answer: The authored HTML of one answer.
 *
 * Returns:
 *   Segments in document order. HTML segments are handed to the existing
 *   rendering path untouched; example segments carry the decoded phrase to
 *   prefill the composer with.
 *
 *   A phrase containing markup is deliberately NOT extracted: lifting it would
 *   drop its inner tags (or send them as text), so it stays inert rather than
 *   misrepresent what was written. Empty and whitespace-only phrases likewise.
 */
export function splitFaqAnswer(answer: string): FaqSegment[] {
  if (!answer) return [];

  const segments: FaqSegment[] = [];
  let cursor = 0;

  // `matchAll` on a fresh regex: the module-level literal carries `lastIndex`
  // state, and sharing it across calls would make the function non-pure.
  for (const match of answer.matchAll(new RegExp(BULLETED_EXAMPLE))) {
    const inner = match[1];
    const text = decodeEntities(inner).trim();
    // Markup inside, or nothing to send: leave this one in the HTML stream.
    if (!text || inner.includes('<')) continue;

    const emStart = match.index + match[0].length - `<em>${inner}</em>`.length;
    if (emStart > cursor) {
      segments.push({ kind: 'html', html: answer.slice(cursor, emStart) });
    }
    segments.push({ kind: 'example', text });
    cursor = match.index + match[0].length;
  }

  if (cursor < answer.length) {
    segments.push({ kind: 'html', html: answer.slice(cursor) });
  }
  return segments;
}

/** How many clickable commands an answer offers (0 when it is pure prose). */
export function faqExampleCount(answer: string): number {
  return splitFaqAnswer(answer).filter(segment => segment.kind === 'example').length;
}
