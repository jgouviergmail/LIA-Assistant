/**
 * HTML → Markdown for an assistant answer that leaves the chat as a FILE.
 *
 * `html-plain-text.ts` flattens an answer to TEXT — the clipboard's plain
 * flavour, the share sheet, a voice: no heading, no emphasis, no link target,
 * no table. A `.md` file is read in a Markdown viewer, so it gets Markdown: the
 * structure the person read in the chat, written the way Markdown writes it
 * (ATX headings, GFM tables and alerts, fenced code), and the LIA components —
 * the ADR-177 vocabulary and the data cards — drawn as their nearest Markdown
 * equivalent. What exists only on a screen never reaches the file: icons (a
 * Material Symbols ligature is a glyph name, never prose), avatars, action
 * buttons, a fold's « see more », widget sentinels, and images (a card's image
 * is a proxied, expiring URL a file cannot follow).
 *
 * The markup is parsed by the browser's `DOMParser` into an inert document (no
 * script runs, no resource loads) and only READ: nothing here is rendered, so
 * it is no sanitizer and never feeds `dangerouslySetInnerHTML`.
 */

import { htmlToPlainText } from './html-plain-text';

/** What the conversion needs from the reader's locale. */
export interface MarkdownExportOptions {
  /** What joins a label to its value, in the reader's punctuation (« : » in French). */
  labelSeparator: string;
}

/** How a block joins its neighbours: list items stay tight, rules collapse. */
type BlockKind = 'paragraph' | 'item' | 'list' | 'rule' | 'other';

interface Block {
  kind: BlockKind;
  text: string;
}

interface Walk {
  options: MarkdownExportOptions;
  /** Elements already written elsewhere (a card's title, hoisted to its head). */
  written: Set<Element>;
  /** Inside a table cell: a pipe is escaped. */
  inCell: boolean;
  /** Inside a link's text: a bracket is escaped, or it ends the text early. */
  inLink: boolean;
  /** What a `<br>` becomes: a hard break in prose, `<br>` in a cell, a space on one line. */
  lineBreak: string;
}

/** A Markdown hard line break: two trailing spaces. */
const HARD_BREAK = '  \n';
/** What joins two chips or badges on one line. */
const CHIP_JOIN = ' · ';

/** Screen-only elements: dropped with everything they hold. */
const SCREEN_ONLY = [
  'script',
  'style',
  'template',
  'noscript',
  'img',
  'picture',
  'svg',
  'canvas',
  'video',
  'audio',
  'iframe',
  'object',
  'embed',
  'button',
  'input',
  'select',
  'textarea',
  '.material-symbols-outlined',
  '.lia-icon',
  '.lia-illus',
  '.lia-illus-sm',
  '.lia-att-row__avatars',
  '.lia-suggested-actions',
  '.lia-action-btn',
  '.lia-skill-app',
  '.lia-mcp-app',
  '.lia-email__status-icons',
  '.lia-indicator-unread',
  '.lia-collapsible__trigger',
  'hr.lia-separator',
].join(',');

/** Inline tags (chips, badges) read as a list on one line. */
const CHIP = [
  '.lia-chip',
  '.lia-badge',
  '.lia-tbadge',
  '.lia-label',
  '.lia-web-search__source',
  '.lia-web-search__result-domain',
].join(',');

/**
 * Chips whose meaning is carried by their icon alone (« 1 » is an attachment
 * count only beside a paperclip): the icon goes, a text glyph says it instead.
 */
const ICON_MEANING: ReadonlyArray<readonly [string, string]> = [
  ['.lia-chip--attach', '📎 '],
  ['.lia-chip--stars', '★ '],
];

/** A card's title — written first, as a heading, wherever the card draws it. */
const CARD_TITLE = ['.lia-card-top__title', '.lia-card__title', '.lia-weather__city'].join(',');

/** A card's detail row: one bullet, on one line. */
const ITEM = [
  '.lia-d-row',
  '.lia-d-item',
  '.lia-detail-item',
  '.lia-part-item',
  '.lia-attachment',
  '.lia-kv-row',
  '.lia-att-row',
  '.lia-file-meta',
  '.lia-file__detail-item',
  '.lia-task__detail-item',
  '.lia-task__subtask',
  '.lia-route__step',
  '.lia-route__endpoint',
  '.lia-route__waypoint',
  '.lia-weather__day',
  '.lia-weather__hour',
  '.lia-weather__stat',
  '.lia-fallback__item',
].join(',');

/** The label half of a label/value pair, joined to its value by the reader's separator. */
const LABEL = ['.lia-kv-row__key', '.lia-route__endpoint-label', '.lia-weather__stat-label'].join(
  ','
);

/** A section or callout title: a bold line of its own. */
const SECTION_LABEL = [
  '.lia-sec__label',
  '.lia-section__title',
  '.lia-task__subtasks-header',
  '.lia-callout__title',
].join(',');

/** Class-driven elements that are blocks whatever their tag. */
const BLOCK_CLASSES = [CARD_TITLE, ITEM, SECTION_LABEL, '.lia-quote-block'].join(',');

const BLOCK_TAGS = new Set([
  'ADDRESS',
  'ARTICLE',
  'ASIDE',
  'BLOCKQUOTE',
  'CAPTION',
  'DD',
  'DETAILS',
  'DIV',
  'DL',
  'DT',
  'FIELDSET',
  'FIGCAPTION',
  'FIGURE',
  'FOOTER',
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'HEADER',
  'HR',
  'LI',
  'MAIN',
  'NAV',
  'OL',
  'P',
  'PRE',
  'SECTION',
  'SUMMARY',
  'TABLE',
  'TBODY',
  'TD',
  'TFOOT',
  'TH',
  'THEAD',
  'TR',
  'UL',
]);

/** A callout's severity as the GFM alert that says the same thing. */
const ALERTS: ReadonlyArray<readonly [string, string]> = [
  ['lia-callout-success', 'TIP'],
  ['lia-callout-warning', 'WARNING'],
  ['lia-callout-error', 'CAUTION'],
  ['lia-callout-info', 'NOTE'],
];

/** The link targets a file can follow; anything else keeps its text only. */
const FOLLOWABLE_HREF = /^(?:https?:|mailto:|tel:)/i;

/** A `$…$` or `$$…$$` span: math the chat renders, never escaped. */
const MATH = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/;

/** A letter or digit of any script: an underscore between two is not emphasis. */
const WORD = /[\p{L}\p{N}]/u;

/**
 * CommonMark's ASCII punctuation: what a backslash escapes. Before anything
 * else (a letter, a space, the end) a backslash is a literal backslash, so
 * « C:\Users » travels untouched while « a\*b » is written `a\\\*b` — left as
 * it was, the reader's backslash escaped the mark and vanished.
 */
const PUNCTUATION = /[!-/:-@[-`{-~]/;

/** What would open a Markdown block at the start of a line of text. */
const LINE_STARTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(#{1,6})(?=\s|$)/, '\\$1'],
  [/^([-+])(?=\s)/, '\\$1'],
  [/^(\d{1,9})([.)])(?=\s|$)/, '$1\\$2'],
  [/^>/, '\\>'],
  // A setext underline of any length turns the line above into a heading.
  [/^(=+|-+)\s*$/, '\\$1'],
  [/^~{3,}/, '\\$&'],
];

function isElement(node: Node): node is Element {
  return node.nodeType === Node.ELEMENT_NODE;
}

function isSkipped(node: Node, walk: Walk): boolean {
  return isElement(node) && (walk.written.has(node) || node.matches(SCREEN_ONLY));
}

function isBlock(element: Element): boolean {
  return BLOCK_TAGS.has(element.tagName) || element.matches(BLOCK_CLASSES);
}

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------

function shouldEscape(
  mark: string,
  before: string,
  after: string,
  walk: Pick<Walk, 'inCell' | 'inLink'>
): boolean {
  switch (mark) {
    case '*':
      return !(before === ' ' && after === ' ');
    case '_':
      return !(WORD.test(before) && WORD.test(after));
    case '<':
      return /[A-Za-z/!?]/.test(after);
    case '|':
      return walk.inCell;
    case '[':
    case ']':
      return walk.inLink;
    case '\\':
      return PUNCTUATION.test(after);
    default:
      return true;
  }
}

/**
 * Escape what Markdown would read as markup, and nothing a reader types every
 * day. ONE place for every mark, the backslash included: escaped later, in a
 * link's own replace, a backslash before a bracket was doubled after the
 * bracket had been escaped and the text read as `\\]` — a literal backslash,
 * then the bracket ending the link (CodeQL js/incomplete-sanitization).
 */
function escapeMarks(text: string, walk: Pick<Walk, 'inCell' | 'inLink'>): string {
  return text.replace(/[`*_<|[\]\\]/g, (mark: string, offset: number) =>
    shouldEscape(mark, text[offset - 1] ?? '', text[offset + 1] ?? '', walk) ? `\\${mark}` : mark
  );
}

/** A text node as Markdown: HTML whitespace folded, marks escaped outside math. */
function textOf(raw: string, walk: Walk): string {
  // Not `\s`: a no-break space is typography (« Prix : 5 € »), not layout.
  const folded = raw.replace(/[ \t\n\r\f]+/g, ' ');
  return folded
    .split(MATH)
    .map((part, index) => (index % 2 === 1 ? part : escapeMarks(part, walk)))
    .join('');
}

function escapeLineStart(line: string): string {
  for (const [pattern, replacement] of LINE_STARTS) {
    if (pattern.test(line)) return line.replace(pattern, replacement);
  }
  return line;
}

/** Fold the spaces an inline run gathered, keeping every hard break. */
function tidy(raw: string): string {
  return raw
    .replace(/ {2,}(?!\n)/g, ' ')
    .replace(/\n +/g, '\n')
    .trim();
}

function longestRun(text: string, mark: string): number {
  return Math.max(
    0,
    ...Array.from(text.matchAll(new RegExp(`\\${mark}+`, 'g')), run => run[0].length)
  );
}

function bold(text: string): string {
  return /^\*\*[\s\S]*\*\*$/.test(text) ? text : `**${text}**`;
}

// ---------------------------------------------------------------------------
// Inline
// ---------------------------------------------------------------------------

/** Emphasis marks hug the words: surrounding spaces go outside, emptiness goes. */
function wrap(inner: string, mark: string): string {
  const [, lead = '', core = '', trail = ''] = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner) ?? [];
  return core ? `${lead}${mark}${core}${mark}${trail}` : `${lead}${trail}`;
}

function inlineCode(element: Element, walk: Walk): string {
  const code = (element.textContent ?? '').replace(/[\r\n]+/g, ' ');
  if (!code) return '';
  const fence = '`'.repeat(longestRun(code, '`') + 1);
  const pad = code.startsWith('`') || code.endsWith('`') ? ' ' : '';
  const body = walk.inCell ? code.replaceAll('|', '\\|') : code;
  return `${fence}${pad}${body}${pad}${fence}`;
}

function link(element: Element, walk: Walk): string {
  const href = (element.getAttribute('href') ?? '').trim();
  const followable = FOLLOWABLE_HREF.test(href);
  // The brackets of a link's text are escaped as its text is written (`inLink`).
  const text = tidy(
    joinInline(element.childNodes, { ...walk, lineBreak: ' ', inLink: followable })
  );
  if (!text) return '';
  if (!followable) return text;
  if ((element.textContent ?? '').trim() === href) return `<${href}>`;
  // A pipe in a cell's link would end the cell: percent-encoded, it is the same URL.
  const url = walk.inCell ? href.replaceAll('|', '%7C') : href;
  const target = /[\s()<>]/.test(url) ? `<${url.replace(/[<>]/g, encodeURIComponent)}>` : url;
  return `[${text}](${target})`;
}

const INLINE_RULES: Readonly<Record<string, (element: Element, walk: Walk) => string>> = {
  A: link,
  B: (element, walk) => wrap(joinInline(element.childNodes, walk), '**'),
  BR: (_element, walk) => walk.lineBreak,
  CODE: inlineCode,
  DEL: (element, walk) => wrap(joinInline(element.childNodes, walk), '~~'),
  EM: (element, walk) => wrap(joinInline(element.childNodes, walk), '*'),
  I: (element, walk) => wrap(joinInline(element.childNodes, walk), '*'),
  KBD: inlineCode,
  S: (element, walk) => wrap(joinInline(element.childNodes, walk), '~~'),
  SAMP: inlineCode,
  STRONG: (element, walk) => wrap(joinInline(element.childNodes, walk), '**'),
};

function inlineOf(node: ChildNode, walk: Walk): string {
  if (node.nodeType === Node.TEXT_NODE) return textOf(node.textContent ?? '', walk);
  if (!isElement(node) || isSkipped(node, walk)) return '';
  const rule = INLINE_RULES[node.tagName];
  if (rule) return rule(node, walk);
  const glyph = ICON_MEANING.find(([selector]) => node.matches(selector))?.[1];
  const inner = glyph
    ? glyph + joinInline(node.childNodes, walk).trimStart()
    : joinInline(node.childNodes, walk);
  if (node.matches(LABEL)) return `${tidy(inner)}${walk.options.labelSeparator}`;
  // A block flattened onto a line (a card row) stays apart from its neighbours.
  return isBlock(node) ? ` ${inner} ` : inner;
}

/** Two spans side by side draw apart on screen (a value and its label): keep them apart. */
function drawnApart(previous: ChildNode | null, node: ChildNode): boolean {
  return (
    previous !== null &&
    isElement(previous) &&
    isElement(node) &&
    (previous.tagName === 'SPAN' || node.tagName === 'SPAN')
  );
}

function glue(out: string, piece: string, previous: ChildNode | null, node: ChildNode): string {
  // A chip joins the chip before it on ITS line: never across a line break.
  if (isElement(node) && node.matches(CHIP) && out.trim() && !out.endsWith('\n')) {
    return `${out.trimEnd()}${CHIP_JOIN}${piece.trimStart()}`;
  }
  if (drawnApart(previous, node) && !/\s$/.test(out) && !/^\s/.test(piece)) {
    return `${out} ${piece}`;
  }
  return out + piece;
}

function joinInline(nodes: Iterable<ChildNode>, walk: Walk): string {
  let out = '';
  let previous: ChildNode | null = null;
  for (const node of nodes) {
    const piece = inlineOf(node, walk);
    if (!piece) continue;
    out = glue(out, piece, previous, node);
    previous = node;
  }
  return out;
}

/** An element's inline content on ONE line (a heading, a bullet, a term). */
function inlineLine(element: Element, walk: Walk): string {
  return tidy(joinInline(element.childNodes, { ...walk, lineBreak: ' ' }).replace(/\n/g, ' '));
}

// ---------------------------------------------------------------------------
// Blocks
// ---------------------------------------------------------------------------

function paragraph(raw: string): Block[] {
  const text = tidy(raw);
  return text
    ? [{ kind: 'paragraph', text: text.split('\n').map(escapeLineStart).join('\n') }]
    : [];
}

function quote(text: string): string {
  return text
    .split('\n')
    .map(line => (line ? `> ${line}` : '>'))
    .join('\n');
}

/** Indent every non-empty line by `width` columns. */
function indent(text: string, width: number): string {
  const pad = ' '.repeat(width);
  return text
    .split('\n')
    .map(line => (line ? pad + line : line))
    .join('\n');
}

/** A marker, then the body indented under it so every continuation stays in the item. */
function indentUnder(marker: string, body: string): string {
  const [first = '', ...rest] = body.split('\n');
  // An empty item is its marker alone; a first line keeps its trailing hard break.
  const head = first ? `${marker} ${first}` : marker;
  return rest.length ? `${head}\n${indent(rest.join('\n'), marker.length + 1)}` : head;
}

/** Leading, trailing and repeated rules say nothing (the separators around each card). */
function withoutStrayRules(blocks: readonly Block[]): Block[] {
  const kept: Block[] = [];
  for (const block of blocks) {
    const last = kept.at(-1);
    if (block.kind === 'rule' && (!last || last.kind === 'rule')) continue;
    kept.push(block);
  }
  if (kept.at(-1)?.kind === 'rule') kept.pop();
  return kept;
}

function separator(previous: Block, next: Block, inItem: boolean): string {
  if (previous.kind === 'item' && next.kind === 'item') return '\n';
  if (inItem && next.kind === 'list') return '\n';
  return '\n\n';
}

function joinBlocks(blocks: readonly Block[], inItem = false): string {
  let out = '';
  let previous: Block | undefined;
  for (const block of withoutStrayRules(blocks)) {
    if (previous) out += separator(previous, block, inItem);
    out += block.text;
    previous = block;
  }
  return out;
}

/** The blocks of a container: runs of inline content become paragraphs. */
function childBlocks(parent: Node, walk: Walk): Block[] {
  const blocks: Block[] = [];
  let run: ChildNode[] = [];
  const flush = () => {
    blocks.push(...paragraph(joinInline(run, walk)));
    run = [];
  };
  for (const child of parent.childNodes) {
    if (isSkipped(child, walk)) continue;
    if (isElement(child) && isBlock(child)) {
      flush();
      blocks.push(...blocksOf(child, walk));
    } else {
      run.push(child);
    }
  }
  flush();
  return blocks;
}

function headingBlock(level: number, text: string): Block[] {
  return text ? [{ kind: 'other', text: `${'#'.repeat(level)} ${text}` }] : [];
}

function heading(level: number, element: Element, walk: Walk): Block[] {
  return headingBlock(level, inlineLine(element, walk));
}

/** A card's title is often the LINK itself (`<a class="…__title">`): written whole, target kept. */
function cardTitle(element: Element, walk: Walk): Block[] {
  const line = { ...walk, lineBreak: ' ' };
  return headingBlock(3, tidy(inlineOf(element, line).replace(/\n/g, ' ')));
}

function itemBlocks(element: Element, walk: Walk): Block[] {
  const text = inlineLine(element, walk);
  return text ? [{ kind: 'item', text: `- ${escapeLineStart(text)}` }] : [];
}

function sectionLabelBlocks(element: Element, walk: Walk): Block[] {
  const text = inlineLine(element, walk);
  return text ? [{ kind: 'paragraph', text: bold(text) }] : [];
}

function quoteBlocks(element: Element, walk: Walk): Block[] {
  const body = joinBlocks(childBlocks(element, walk));
  return body ? [{ kind: 'other', text: quote(body) }] : [];
}

const NESTED_LIST = new Set(['UL', 'OL']);

function listBlocks(element: Element, walk: Walk): Block[] {
  const ordered = element.tagName === 'OL';
  const start = Number.parseInt(element.getAttribute('start') ?? '', 10);
  let number = Number.isNaN(start) ? 1 : start;
  const items: string[] = [];
  let width = 0;
  for (const child of element.children) {
    if (isSkipped(child, walk)) continue;
    if (child.tagName === 'LI') {
      const marker = ordered ? `${number++}.` : '-';
      items.push(indentUnder(marker, joinBlocks(childBlocks(child, walk), true)));
      width = marker.length + 1;
    } else if (NESTED_LIST.has(child.tagName)) {
      // `<ul><li>A</li><ul>…</ul></ul>` is invalid HTML a model writes anyway:
      // the stray list belongs to the item before it (or stands alone).
      const nested = joinBlocks(listBlocks(child, walk));
      if (nested) items.push(indent(nested, width));
    }
  }
  return items.length ? [{ kind: 'list', text: items.join('\n') }] : [];
}

function codeBlocks(element: Element): Block[] {
  const code = element.querySelector('code');
  const language = /(?:^|\s)language-([\w#+.-]+)/.exec(code?.className ?? '')?.[1] ?? '';
  const text = ((code ?? element).textContent ?? '').replace(/\n+$/, '');
  const fence = '`'.repeat(Math.max(3, longestRun(text, '`') + 1));
  return [{ kind: 'other', text: `${fence}${language}\n${text}\n${fence}` }];
}

/** A GFM table; rows shorter than the widest are padded, so every column holds. */
function gfmTable(header: readonly string[], rows: readonly (readonly string[])[]): Block {
  const width = Math.max(header.length, ...rows.map(row => row.length));
  const line = (cells: readonly string[]) =>
    `| ${Array.from({ length: width }, (_, index) => cells[index] ?? '').join(' | ')} |`;
  return {
    kind: 'other',
    text: [line(header), line(Array<string>(width).fill('---')), ...rows.map(line)].join('\n'),
  };
}

function cellText(cell: Element, walk: Walk): string {
  return tidy(joinInline(cell.childNodes, { ...walk, inCell: true, lineBreak: '<br>' })).replace(
    /\n/g,
    ' '
  );
}

function rowCells(row: Element, walk: Walk): string[] {
  const cells: string[] = [];
  for (const cell of row.querySelectorAll(':scope > th, :scope > td')) {
    // HTML reads a missing, malformed or zero colspan as 1 and caps it at 1000.
    const span = Math.min(Number.parseInt(cell.getAttribute('colspan') ?? '', 10) || 1, 1000);
    cells.push(cellText(cell, walk), ...Array<string>(Math.max(0, span - 1)).fill(''));
  }
  return cells;
}

function tableBlocks(element: Element, walk: Walk): Block[] {
  const rows = element.querySelectorAll(
    ':scope > tr, :scope > thead > tr, :scope > tbody > tr, :scope > tfoot > tr'
  );
  // GFM has no headerless table: the first row is the header, as the chat draws it.
  const cells = Array.from(rows, row => rowCells(row, walk));
  const [header, ...body] = cells;
  if (!header || cells.every(row => row.length === 0)) return childBlocks(element, walk);
  const caption = element.querySelector(':scope > caption');
  const title = caption ? sectionLabelBlocks(caption, walk) : [];
  return [...title, gfmTable(header, body)];
}

function statsBlocks(element: Element, walk: Walk): Block[] {
  const tiles = Array.from(element.querySelectorAll('.lia-stat'));
  if (tiles.length === 0) return childBlocks(element, walk);
  const part = (tile: Element, selector: string) => {
    const found = tile.querySelector(selector);
    return found ? cellText(found, walk) : '';
  };
  return [
    gfmTable(
      tiles.map(tile => part(tile, '.lia-stat__label')),
      [tiles.map(tile => part(tile, '.lia-stat__value'))]
    ),
  ];
}

function definitionBlocks(element: Element, walk: Walk): Block[] {
  const items: Block[] = [];
  const add = (text: string) => items.push({ kind: 'item', text: `- ${escapeLineStart(text)}` });
  let term = '';
  // HTML5 lets a `div` group a term with its values: read through it.
  for (const child of element.querySelectorAll(
    ':scope > dt, :scope > dd, :scope > div > dt, :scope > div > dd'
  )) {
    if (child.tagName === 'DT') {
      if (term) add(bold(term));
      term = inlineLine(child, walk);
    } else if (child.tagName === 'DD') {
      const value = inlineLine(child, walk);
      add(term ? `${bold(term)}${walk.options.labelSeparator}${value}` : value);
      term = '';
    }
  }
  if (term) add(bold(term));
  return items;
}

function detailsBlocks(element: Element, walk: Walk): Block[] {
  const summary = element.querySelector(':scope > summary');
  // An authored summary names the fold's content; a card's trigger (« See
  // more ») is screen-only and already skipped.
  if (!summary || isSkipped(summary, walk)) return childBlocks(element, walk);
  walk.written.add(summary);
  return [...sectionLabelBlocks(summary, walk), ...childBlocks(element, walk)];
}

function calloutBlocks(element: Element, walk: Walk): Block[] {
  const alert = ALERTS.find(([name]) => element.classList.contains(name))?.[1] ?? 'NOTE';
  const body = joinBlocks(childBlocks(element, walk));
  return body ? [{ kind: 'other', text: quote(`[!${alert}]\n${body}`) }] : [];
}

function cardBlocks(element: Element, walk: Walk): Block[] {
  const title = element.querySelector(CARD_TITLE);
  if (!title) return childBlocks(element, walk);
  const head = cardTitle(title, walk);
  walk.written.add(title);
  return [...head, ...childBlocks(element, walk)];
}

/** Class rules first: a component is recognised by its class, whatever its tag. */
const CLASS_BLOCKS: ReadonlyArray<readonly [string, (element: Element, walk: Walk) => Block[]]> = [
  ['.lia-card', cardBlocks],
  ['.lia-callout', calloutBlocks],
  ['.lia-stats', statsBlocks],
  [CARD_TITLE, cardTitle],
  [ITEM, itemBlocks],
  [SECTION_LABEL, sectionLabelBlocks],
  ['.lia-quote-block', quoteBlocks],
];

const TAG_BLOCKS: Readonly<Record<string, (element: Element, walk: Walk) => Block[]>> = {
  H1: (element, walk) => heading(1, element, walk),
  H2: (element, walk) => heading(2, element, walk),
  H3: (element, walk) => heading(3, element, walk),
  H4: (element, walk) => heading(4, element, walk),
  H5: (element, walk) => heading(5, element, walk),
  H6: (element, walk) => heading(6, element, walk),
  HR: () => [{ kind: 'rule', text: '---' }],
  UL: listBlocks,
  OL: listBlocks,
  LI: itemBlocks,
  PRE: codeBlocks,
  BLOCKQUOTE: quoteBlocks,
  TABLE: tableBlocks,
  DL: definitionBlocks,
  DETAILS: detailsBlocks,
};

function blocksOf(element: Element, walk: Walk): Block[] {
  const byClass = CLASS_BLOCKS.find(([selector]) => element.matches(selector));
  if (byClass) return byClass[1](element, walk);
  const byTag = TAG_BLOCKS[element.tagName];
  return byTag ? byTag(element, walk) : childBlocks(element, walk);
}

/**
 * Write an HTML fragment of an assistant answer as Markdown.
 *
 * @param html - The markup: a `lia-response` document, data cards, or both.
 * @param options - What the reader's locale decides (the label separator).
 * @returns GFM Markdown, trimmed; empty when the markup holds nothing a file
 *   can show. Without a DOM parser (never the case in a browser) the answer is
 *   flattened to plain text rather than lost.
 */
export function htmlToMarkdown(html: string, options: MarkdownExportOptions): string {
  if (typeof DOMParser === 'undefined') return htmlToPlainText(html);
  const { body } = new DOMParser().parseFromString(html, 'text/html');
  const walk: Walk = {
    options,
    written: new Set(),
    inCell: false,
    inLink: false,
    lineBreak: HARD_BREAK,
  };
  return joinBlocks(childBlocks(body, walk)).trim();
}
