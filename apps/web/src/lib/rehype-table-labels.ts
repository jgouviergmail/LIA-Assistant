/**
 * rehype-table-labels — every body cell names its column (B2).
 *
 * WHY THIS EXISTS
 * ---------------
 * On a narrow screen an overflowing table is drawn as stacked cards, one per
 * row (owner arbitration 2026-09-25). The header row is then hidden, so each
 * value must say which column it belongs to: this plugin writes that name on
 * the cell (`data-label`), and the stylesheet prints it above the value
 * (`content: attr(data-label)`). A wide table keeps its header row and ignores
 * the attribute.
 *
 * It also states the table's semantics as explicit ARIA roles: a table whose
 * parts are `display: block` loses its implicit table semantics in some
 * engines (WebKit), and the stacked cards are exactly that. The roles are the
 * ones the elements carry natively, so a table drawn as a table is unchanged.
 *
 * CONTRACT
 * --------
 * - The header is the first row of `<thead>`, else a first body row made only
 *   of `<th>`. No header, no label — a card without names still reads.
 * - Columns follow `colspan` and `rowspan` on a grid, the way the browser lays
 *   them out. Both are clamped (a model can write `rowspan="65534"`), so a
 *   hostile value costs nothing.
 * - A label is the cell's text, whitespace collapsed, bounded; an icon
 *   ligature (`material-symbols-outlined`) is not text, and a formula reads as
 *   its TeX source.
 * - A nested table is labelled on its own terms, never with the outer headers.
 *
 * SECURITY
 * --------
 * Runs AFTER the sanitize boundary and only writes attribute VALUES computed
 * from already-sanitized text — React escapes them, and CSS `attr()` renders
 * them as text. The XSS posture is that of `rehype-search-highlight`.
 */

/** The structural subset of hast this plugin reads and writes. */
export interface HastNodeLike {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNodeLike[];
  value?: string;
}

/** A node that has children (a root or an element). */
export interface HastParent extends HastNodeLike {
  children: HastNodeLike[];
}

/** Longest label written on a cell — a column NAME, not a paragraph. */
export const TABLE_LABEL_MAX_CHARS = 80;

/** Largest span honoured: the HTML parser's own colspan ceiling is 1000. */
const MAX_COL_SPAN = 64;

const ROW_GROUPS = new Set(['thead', 'tbody', 'tfoot']);
const CELLS = new Set(['td', 'th']);
const ICON_CLASS = 'material-symbols-outlined';

function isElement(node: HastNodeLike, tagName?: string): node is HastParent {
  return (
    node.type === 'element' &&
    Array.isArray(node.children) &&
    (tagName === undefined || node.tagName === tagName)
  );
}

function classesOf(node: HastNodeLike): string[] {
  const className = node.properties?.className;
  if (Array.isArray(className)) return className.map(String);
  return typeof className === 'string' ? className.split(/\s+/) : [];
}

function setProperty(node: HastNodeLike, key: string, value: string): void {
  node.properties = { ...(node.properties ?? {}), [key]: value };
}

/** The TeX source of a rendered formula, or '' when it carries none. */
function formulaSource(katex: HastParent): string {
  for (const child of katex.children) {
    if (isElement(child, 'annotation')) return textOf(child);
    if (isElement(child)) {
      const found = formulaSource(child);
      if (found) return found;
    }
  }
  return '';
}

/** The readable text of a cell: icons skipped, formulas as their source. */
function textOf(node: HastNodeLike): string {
  if (node.type === 'text') return node.value ?? '';
  if (!isElement(node)) return '';
  const classes = classesOf(node);
  if (classes.includes(ICON_CLASS)) return '';
  if (classes.includes('katex')) return formulaSource(node);
  if (node.tagName === 'table') return '';
  return node.children.map(textOf).join('');
}

function labelOf(cell: HastNodeLike): string {
  const collapsed = textOf(cell).replace(/\s+/g, ' ').trim();
  if (collapsed.length <= TABLE_LABEL_MAX_CHARS) return collapsed;
  return `${collapsed.slice(0, TABLE_LABEL_MAX_CHARS - 1).trimEnd()}…`;
}

function spanOf(cell: HastNodeLike, key: 'colSpan' | 'rowSpan', max: number): number {
  const raw = Number(cell.properties?.[key]);
  if (!Number.isFinite(raw) || raw < 1) return 1;
  return Math.min(Math.floor(raw), Math.max(1, max));
}

function cellsOf(tr: HastParent): HastParent[] {
  return tr.children.filter((child): child is HastParent =>
    CELLS.has((child as HastNodeLike).tagName ?? '')
  );
}

/** One row, the tag of its row group, and the group itself (its identity). */
interface PlacedRow {
  tr: HastParent;
  group: string;
  groupNode: HastNodeLike;
}

/** Rows of a table, in order. Rows written directly under <table> form one group. */
function rowsOf(table: HastParent): PlacedRow[] {
  const rows: PlacedRow[] = [];
  for (const child of table.children) {
    if (isElement(child, 'tr')) rows.push({ tr: child, group: 'tbody', groupNode: table });
    else if (isElement(child) && ROW_GROUPS.has(child.tagName ?? '')) {
      for (const tr of child.children) {
        if (isElement(tr, 'tr')) {
          rows.push({ tr, group: child.tagName ?? 'tbody', groupNode: child });
        }
      }
    }
  }
  return rows;
}

/**
 * Lay the rows of ONE row group on a grid and hand each cell its column index.
 *
 * `occupied` records, for the rows still ahead, the columns a rowspan above
 * holds. A rowspan never reaches past the last row of its group — the HTML
 * layout rule, and the bound that keeps `rowspan="65534"` free — and a colspan
 * is clamped, so the grid is bounded by the table the model actually wrote.
 */
function placeGroup(rows: HastParent[], columns: Map<HastNodeLike, number>): void {
  const occupied: Set<number>[] = rows.map(() => new Set<number>());
  rows.forEach((tr, rowIndex) => {
    let column = 0;
    for (const cell of cellsOf(tr)) {
      while (occupied[rowIndex].has(column)) column += 1;
      columns.set(cell, column);
      const colSpan = spanOf(cell, 'colSpan', MAX_COL_SPAN);
      const rowSpan = spanOf(cell, 'rowSpan', rows.length - rowIndex);
      for (let r = rowIndex + 1; r < rowIndex + rowSpan; r += 1) {
        for (let c = column; c < column + colSpan; c += 1) occupied[r].add(c);
      }
      column += colSpan;
    }
  });
}

/** Column index of every cell of the table, group by group. */
function placeCells(rows: PlacedRow[]): Map<HastNodeLike, number> {
  const columns = new Map<HastNodeLike, number>();
  const groups = new Map<HastNodeLike, HastParent[]>();
  for (const { tr, groupNode } of rows) {
    const groupRows = groups.get(groupNode);
    if (groupRows) groupRows.push(tr);
    else groups.set(groupNode, [tr]);
  }
  for (const groupRows of groups.values()) placeGroup(groupRows, columns);
  return columns;
}

/** Column index → header name, following the header row's own colspans. */
function headerNames(header: HastParent): string[] {
  const names: string[] = [];
  for (const cell of cellsOf(header)) {
    const label = labelOf(cell);
    const colSpan = spanOf(cell, 'colSpan', MAX_COL_SPAN);
    for (let i = 0; i < colSpan; i += 1) names.push(label);
  }
  return names;
}

/** The header row: first row of <thead>, else a first row made only of <th>. */
function findHeader(rows: PlacedRow[]): HastParent | null {
  const inHead = rows.find(row => row.group === 'thead');
  if (inHead) return inHead.tr;
  const first = rows[0]?.tr;
  if (!first) return null;
  const cells = cellsOf(first);
  return cells.length > 0 && cells.every(cell => cell.tagName === 'th') ? first : null;
}

function roleOfCell(cell: HastNodeLike, group: string): string {
  if (cell.tagName === 'td') return 'cell';
  return group === 'thead' ? 'columnheader' : 'rowheader';
}

function labelTable(table: HastParent): void {
  const rows = rowsOf(table);
  const header = findHeader(rows);
  const names = header ? headerNames(header) : [];
  const columns = placeCells(rows);

  setProperty(table, 'role', 'table');
  for (const child of table.children) {
    if (isElement(child) && ROW_GROUPS.has(child.tagName ?? '')) {
      setProperty(child, 'role', 'rowgroup');
    }
  }
  for (const { tr, group } of rows) {
    setProperty(tr, 'role', 'row');
    for (const cell of cellsOf(tr)) {
      const isHeaderCell = tr === header;
      setProperty(cell, 'role', isHeaderCell ? 'columnheader' : roleOfCell(cell, group));
      const name = isHeaderCell ? '' : (names[columns.get(cell) ?? -1] ?? '');
      if (name) setProperty(cell, 'dataLabel', name);
    }
  }
}

function visit(node: HastNodeLike): void {
  if (!isElement(node) && node.type !== 'root') return;
  for (const child of node.children ?? []) {
    // Depth first: a nested table is labelled with its own headers.
    visit(child);
  }
  if (isElement(node, 'table')) labelTable(node);
}

/**
 * rehype plugin factory. Place AFTER `rehypeKatex` so a formula in a header is
 * read from its rendered markup (its TeX source), and BEFORE
 * `rehypeSearchHighlight`, whose marks are presentation, not column names.
 */
export default function rehypeTableLabels() {
  return (tree: HastParent): void => {
    visit(tree);
  };
}
