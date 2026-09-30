/**
 * The `.md` an assistant answer leaves the chat as — « Download », « Send by
 * e-mail » (ADR-321) and a kept answer's export (ADR-282) all write THIS text.
 *
 * An answer is Markdown, a `lia-response` HTML document (`html` display mode),
 * or Markdown followed by the HTML the response node appends after the model's
 * words (data cards in `cards` mode, widget sentinels). Only the HTML is
 * rewritten, by `htmlToMarkdown`: the model's Markdown reaches the file byte
 * for byte — its hard breaks, its indentation, and a fenced block that QUOTES
 * HTML, which a flattening of the whole answer used to strip to text.
 *
 * Where the HTML is follows CommonMark's reading of an HTML block: a line
 * opening with a block-level tag, outside a code fence, opens it; it runs while
 * a tag it opened is still open (the `lia-response` document spans blank
 * lines), and a truncated document runs to the end.
 */

import { htmlToMarkdown, type MarkdownExportOptions } from './html-markdown';
import { looksLikeHtml } from './html-plain-text';

interface Segment {
  html: boolean;
  lines: string[];
}

/** A line opening a CommonMark HTML block of the kinds the response layer writes. */
const HTML_BLOCK_START =
  /^ {0,3}<\/?(?:address|article|aside|blockquote|details|div|dl|figure|footer|h[1-6]|header|hr|main|nav|ol|p|pre|section|style|script|table|ul)(?=[\s/>]|$)/i;

/** A fence opening a code block: three or more backticks or tildes. */
const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;

/** Any start or end tag, with its self-closing slash. */
const TAG = /<(\/?)([a-z][a-z0-9-]*)\b[^<>]*?(\/?)>/gi;

/** Elements that never close: they open nothing. */
const VOID_ELEMENTS = new Set([
  'area',
  'base',
  'br',
  'col',
  'embed',
  'hr',
  'img',
  'input',
  'link',
  'meta',
  'source',
  'track',
  'wbr',
]);

/** How many elements a line leaves open (negative when it closes more). */
function tagBalance(line: string): number {
  let balance = 0;
  for (const [, closing, name = '', selfClosing] of line.matchAll(TAG)) {
    if (selfClosing || VOID_ELEMENTS.has(name.toLowerCase())) continue;
    balance += closing ? -1 : 1;
  }
  return balance;
}

/** Whether a line closes the fence that `opening` opened. */
function closesFence(line: string, opening: string): boolean {
  const marker = line.trim();
  return marker.length >= opening.length && marker === opening[0].repeat(marker.length);
}

/** Splits an answer into its Markdown and HTML stretches, line by line. */
class Splitter {
  readonly segments: Segment[] = [];
  private fence: string | null = null;
  private depth = 0;
  private inHtml = false;

  read(line: string): void {
    if (this.inHtml) {
      this.continueHtml(line);
    } else if (this.fence !== null) {
      this.append(false, line);
      if (closesFence(line, this.fence)) this.fence = null;
    } else if (HTML_BLOCK_START.test(line)) {
      this.depth = 0;
      this.continueHtml(line);
    } else {
      this.fence = FENCE_OPEN.exec(line)?.[1] ?? null;
      this.append(false, line);
    }
  }

  private continueHtml(line: string): void {
    this.append(true, line);
    this.depth = Math.max(0, this.depth + tagBalance(line));
    this.inHtml = this.depth > 0;
  }

  private append(html: boolean, line: string): void {
    const last = this.segments.at(-1);
    if (last?.html === html) last.lines.push(line);
    else this.segments.push({ html, lines: [line] });
  }
}

/** A Markdown stretch without the blank lines around it (its first line's indent kept). */
function trimBlankLines(text: string): string {
  return text.replace(/^(?:[ \t]*\r?\n)+/, '').trimEnd();
}

/**
 * The Markdown file an assistant answer becomes.
 *
 * @param content - The answer as stored: Markdown, HTML, or both.
 * @param options - What the reader's locale decides (the label separator).
 * @returns The answer unchanged when it holds no HTML block; otherwise its
 *   Markdown kept verbatim and each HTML stretch written as Markdown, one
 *   blank line between them.
 */
export function messageToMarkdown(content: string, options: MarkdownExportOptions): string {
  if (!looksLikeHtml(content)) return content;
  const splitter = new Splitter();
  for (const line of content.split('\n')) splitter.read(line);
  if (!splitter.segments.some(segment => segment.html)) return content;
  return splitter.segments
    .map(({ html, lines }) =>
      html ? htmlToMarkdown(lines.join('\n'), options) : trimBlankLines(lines.join('\n'))
    )
    .filter(Boolean)
    .join('\n\n');
}
