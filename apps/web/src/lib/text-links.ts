/**
 * The addresses a plain text holds, ready to be followed (ADR-369).
 *
 * Two shapes reach a text view. The API writes a long link of a mail as
 * `[link](address)`, the reader's and the model's one form: drawn here by its
 * host, never as its markup. An address a person wrote keeps their words.
 *
 * Only `http`, `https`, `mailto` and `tel` are ever followed, and an address
 * carrying credentials never is (`https://bank.example@evil.example/` goes to
 * `evil.example`). A written link that may not be followed is removed, because
 * its markup means nothing to a reader; anything else stays the words it was.
 *
 * One pass over the text (ADR-326): an opener's span is read once, and no opener
 * inside a span already read is looked at again, whatever became of that span.
 */

/** The word `html_text.py` writes between the brackets (`HTML_TEXT_LINK_LABEL`). */
export const WRITTEN_LINK_LABEL = 'link';

export interface TextLink {
  kind: 'link';
  /** What the reader sees. */
  text: string;
  /** Where it goes: an address `safeAddress` accepted. */
  href: string;
}

export type TextSegment = { kind: 'text'; text: string } | TextLink;

const WRITTEN_OPENER = `[${WRITTEN_LINK_LABEL}](`;
const OPENERS = new RegExp(
  String.raw`\[${WRITTEN_LINK_LABEL}\]\(|https?://|www\.|mailto:|tel:`,
  'gi'
);
/** Everything up to what cannot sit in an address; sticky, read from an opener. */
const ADDRESS_BODY = /[^\s<>"]*/y;
/** What, just before an opener, says it is the middle of a word, a host or an address. */
const INSIDE_A_WORD = /[\p{L}\p{N}_.\-/@]/u;
const CLOSING_MARKS = new Set('.,;:!?\'’”»]}');
const WWW = 'www.';
/** `www.example.org`: fewer labels than this is a word that starts with « www. ». */
const WWW_HOST_MIN_LABELS = 3;

function addressBody(text: string, from: number): string {
  ADDRESS_BODY.lastIndex = from;
  return ADDRESS_BODY.exec(text)?.[0] ?? '';
}

/** Where a written link closes, its own parentheses counted; -1 when it never does. */
function closingParenthesis(body: string): number {
  let depth = 1;
  for (let index = 0; index < body.length; index += 1) {
    if (body[index] === '(') {
      depth += 1;
    } else if (body[index] === ')') {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

/** The address without the sentence's closing marks; a parenthesis it opened stays. */
function withoutClosingMarks(body: string): string {
  let unmatched = 0;
  for (const character of body) {
    if (character === '(') unmatched -= 1;
    else if (character === ')') unmatched += 1;
  }
  let end = body.length;
  while (end > 0) {
    const last = body.charAt(end - 1);
    if (last === ')' && unmatched > 0) unmatched -= 1;
    else if (!CLOSING_MARKS.has(last)) break;
    end -= 1;
  }
  return body.slice(0, end);
}

/** @returns Where an address leads and what names it; null when it may not be followed. */
export function safeAddress(raw: string): { href: string; name: string } | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  switch (url.protocol) {
    case 'http:':
    case 'https:':
      return url.username || url.password ? null : { href: url.href, name: url.hostname };
    case 'mailto:':
      return url.pathname.includes('@') ? { href: url.href, name: url.pathname } : null;
    case 'tel:':
      return /\d/.test(url.pathname) ? { href: url.href, name: url.pathname } : null;
    default:
      return null;
  }
}

/** An address as a person wrote it: `www.` reads as https, and needs a whole host. */
function writtenAddress(candidate: string): string | null {
  if (!candidate.toLowerCase().startsWith(WWW)) return safeAddress(candidate)?.href ?? null;
  const address = safeAddress(`https://${candidate}`);
  if (address === null) return null;
  const labels = address.name.split('.').filter(Boolean);
  return labels.length >= WWW_HOST_MIN_LABELS ? address.href : null;
}

/**
 * @param text - A plain text.
 * @returns It in order, as words and links; together they read as the text, less
 *   a written link that may not be followed.
 */
export function linkSegments(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  let shown = 0;
  let cursor = 0;
  const showUpTo = (end: number) => {
    if (end > shown) segments.push({ kind: 'text', text: text.slice(shown, end) });
    shown = end;
  };

  for (const opener of text.matchAll(OPENERS)) {
    const start = opener.index;
    if (start < cursor) continue;
    const word = opener[0];

    if (word.toLowerCase() === WRITTEN_OPENER) {
      const from = start + word.length;
      const body = addressBody(text, from);
      const close = closingParenthesis(body);
      if (close < 0) {
        cursor = from + body.length;
        continue;
      }
      const address = safeAddress(body.slice(0, close));
      showUpTo(start);
      shown = from + close + 1;
      cursor = shown;
      if (address) segments.push({ kind: 'link', text: address.name, href: address.href });
      continue;
    }

    if (start > 0 && INSIDE_A_WORD.test(text.charAt(start - 1))) continue;
    const body = addressBody(text, start);
    cursor = start + body.length;
    const candidate = withoutClosingMarks(body);
    const href = writtenAddress(candidate);
    if (href === null) continue;
    showUpTo(start);
    shown = start + candidate.length;
    segments.push({ kind: 'link', text: candidate, href });
  }

  showUpTo(text.length);
  return segments;
}

/**
 * @param text - A plain text.
 * @returns Its links alone, for a place that cannot draw them in the words (a text area).
 */
export function linksOf(text: string): TextLink[] {
  return linkSegments(text).filter(segment => segment.kind === 'link');
}
