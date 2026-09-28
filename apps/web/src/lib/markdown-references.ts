/**
 * Character references read as the chat reads them — the browser's twin of
 * `read_as_markdown` (`apps/api/src/domains/shared/markdown_literal.py`),
 * pinned to it by the shared voice projection corpus.
 *
 * A surface that renders no Markdown (the voice, a toast) reads the text the
 * chat draws: outside code every valid reference is its character; inside a
 * code span or block the text stays as typed; an `&` that opens no valid
 * reference (« &copy=2 », which HTML5 would decode) is an `&`; and a bare URL
 * keeps its `*`, `_` and `~`, as the chat's autolink does. What the reading
 * produces is kept out of the flattener's reach — each character waits as a
 * private-use shield no rule reads — and written back after it, so nothing it
 * spells is read as markup and nothing is decoded twice. Its code is
 * Markdown's: inside raw HTML the chat reads no code span, where the reader
 * reads one wherever two backticks pair — an HTML card references its
 * backticks (`escape_html`), and LIA's HTML documents are told to write code
 * in `<code>`, never between backticks (`html_response_directive.txt`).
 *
 * One divergence from the server twin is deliberate: a named reference outside
 * the six below (`&eacute;`) is read there and kept as typed here — a table of
 * two thousand names is not worth a reference LIA never writes. The corpus
 * holds none.
 */

/** The named references the browser reads. */
const NAMED: Readonly<Record<string, string>> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
};

const SHIELD_BASE = 0xf0000;
const ESCAPE = String.fromCodePoint(SHIELD_BASE + 0x80);
const BLOCK_END = SHIELD_BASE + 0xff;
const SHIFT = 0x100;
const REPLACEMENT_CHARACTER = '�';

/** A character reference as CommonMark reads it (the `;` is required). */
const CHARACTER_REFERENCE = /&(?:#([0-9]{1,7})|#[xX]([0-9A-Fa-f]{1,6})|([A-Za-z][A-Za-z0-9]{0,31}));/y;
/**
 * A fenced block's opening line (group 1, its fence group 2) or a code span
 * (its backticks group 3, its content group 4; never across a blank line).
 */
const CODE = /^([ \t]{0,3}(`{3,}|~{3,})[^\n]*\n)|(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n)[\s\S])*?)(?<!`)\3(?!`)/gm;
/** A bare URL the chat autolinks — the server's `_URL`, rule for rule. */
const BARE_URL =
  /(?<![^\s(*_~])(?:https?:\/\/|www\.)(?:[\p{L}\p{N}]|-)+(?:\.(?:[\p{L}\p{N}]|-)+)*(?![\p{L}\p{N}_-])[^\s<>"']*/gu;
/** The ASCII punctuation a flattener's rules could read. */
const PUNCTUATION = /[!-/:-@[-`{-~]/g;
/** The marks a bare URL owns and a flattener's emphasis rules would take. */
const URL_MARKS = /[*_~]/g;

const RAW_RESERVED = new RegExp(
  `[${String.fromCodePoint(SHIELD_BASE)}-${String.fromCodePoint(BLOCK_END)}]`,
  'gu'
);
const SHIELDED = new RegExp(
  `${ESCAPE}([${String.fromCodePoint(SHIELD_BASE + SHIFT)}-${String.fromCodePoint(BLOCK_END + SHIFT)}])` +
    `|[${String.fromCodePoint(SHIELD_BASE)}-${String.fromCodePoint(SHIELD_BASE + 0x7f)}]`,
  'gu'
);

/** One character, kept out of a flattener's reach where it could act. */
function shielded(char: string): string {
  const code = char.codePointAt(0) ?? 0;
  if (code < 0x80) return String.fromCodePoint(SHIELD_BASE + code);
  if (code >= SHIELD_BASE && code <= BLOCK_END) return ESCAPE + String.fromCodePoint(code + SHIFT);
  return char;
}

function shieldPunctuation(text: string): string {
  return text.replace(PUNCTUATION, shielded);
}

/**
 * What a reference stands for, or null when it names no character: a
 * numeric one outside Unicode (or a surrogate, or zero) is the replacement
 * character, as CommonMark reads it.
 */
export function decodeReference(
  decimal: string | undefined,
  hexadecimal: string | undefined,
  name: string | undefined
): string | null {
  if (name !== undefined) return Object.hasOwn(NAMED, name) ? NAMED[name] : null;
  const code = decimal !== undefined ? Number(decimal) : parseInt(hexadecimal ?? '', 16);
  if (!code || (code >= 0xd800 && code <= 0xdfff) || code > 0x10ffff) return REPLACEMENT_CHARACTER;
  return String.fromCodePoint(code);
}

/** Every valid reference decoded and shielded; every other `&` shielded. */
function readReferences(text: string): string {
  let out = '';
  let position = 0;
  for (let ampersand = text.indexOf('&'); ampersand !== -1; ampersand = text.indexOf('&', position)) {
    out += text.slice(position, ampersand);
    CHARACTER_REFERENCE.lastIndex = ampersand;
    const reference = CHARACTER_REFERENCE.exec(text);
    const decoded = reference ? decodeReference(reference[1], reference[2], reference[3]) : null;
    if (reference === null || decoded === null) {
      out += shielded('&');
      position = ampersand + 1;
    } else {
      for (const char of decoded) out += shielded(char);
      position = ampersand + reference[0].length;
    }
  }
  return out + text.slice(position);
}

/** Prose: its references read, the marks of its bare URLs kept as typed. */
function readProse(text: string): string {
  let out = '';
  let position = 0;
  for (const url of text.matchAll(BARE_URL)) {
    const start = url.index ?? 0;
    out += readReferences(text.slice(position, start));
    out += readReferences(url[0].replace(URL_MARKS, shielded));
    position = start + url[0].length;
  }
  return out + readReferences(text.slice(position));
}

/** A code block or span: its delimiters as typed, its content shielded whole. */
function readCode(match: RegExpExecArray, text: string): [string, number] {
  const end = match.index + match[0].length;
  if (match[1] !== undefined) {
    const fence = match[2];
    const escaped = fence[0] === '`' ? '`' : '~';
    const closing = new RegExp(`^[ \\t]{0,3}${escaped}{${fence.length},}[ \\t]*$`, 'gm');
    closing.lastIndex = end;
    const close = closing.exec(text);
    const bodyEnd = close ? close.index : text.length;
    const resume = close ? close.index + close[0].length : text.length;
    return [match[1] + shieldPunctuation(text.slice(end, bodyEnd)) + (close ? close[0] : ''), resume];
  }
  return [match[3] + shieldPunctuation(match[4]) + match[3], end];
}

/** The text as a flattener may read it: nothing it holds can act there. */
function shield(raw: string): string {
  const text = raw.replace(RAW_RESERVED, shielded);
  let out = '';
  let position = 0;
  CODE.lastIndex = 0;
  for (let code = CODE.exec(text); code !== null; code = CODE.exec(text)) {
    out += readProse(text.slice(position, code.index));
    const [kept, resume] = readCode(code, text);
    out += kept;
    position = resume;
    CODE.lastIndex = resume;
  }
  return out + readProse(text.slice(position));
}

/**
 * Flatten text the way the chat reads its character references.
 *
 * @param text - Text holding character references (LIA's words, a card's values).
 * @param flatten - The flattener (Markdown or HTML to what a surface renders); none
 *   reads the references alone.
 * @param restore - How a kept character is written back (the character itself by default).
 * @returns What `flatten` makes of the text, each kept character written back.
 */
export function readAsMarkdown(
  text: string,
  flatten: (shieldedText: string) => string = shieldedText => shieldedText,
  restore: (char: string) => string = char => char
): string {
  return flatten(shield(text)).replace(SHIELDED, (whole: string, escaped: string | undefined) => {
    if (escaped !== undefined) return String.fromCodePoint((escaped.codePointAt(0) ?? SHIFT) - SHIFT);
    return restore(String.fromCodePoint((whole.codePointAt(0) ?? SHIELD_BASE) - SHIELD_BASE));
  });
}
