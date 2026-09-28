/**
 * A REFERENCED dollar is a literal dollar, in the chat as in CommonMark.
 *
 * A value a card draws as itself references its `$` (`&#36;`,
 * `markdown_data_literal` on the server) because the chat's math step reads
 * dollar delimiters on DECODED text (`rehypeMathInText`, which must see the
 * math inside raw HTML): measured, `rm -rf $BACKUP_DIR/$OLD` drew a formula,
 * and `&#92;&#36;` — a backslash then a dollar — read as an escaped dollar and
 * lost its backslash (review 14). CommonMark never reads a reference as a
 * delimiter, so the chat honours it: the string step turns every referenced
 * dollar outside code into a private-use marker no math rule reads
 * (`protectReferencedDollars`), and a rehype step writes it back
 * (`rehypeRestoreDollars`) — `\$` inside a formula, where a raw `$` would end
 * it, `$` everywhere else, attribute values included.
 */

/** The marker a referenced dollar waits as while the math steps run. */
export const DOLLAR_MARKER = '';

/** Code spans and fenced blocks, where a reference is shown as typed. */
const CODE_SPAN_RE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|``[\s\S]*?``|`[^`\n]*`)/g;
/** A reference to `$`: `&#36;`, `&#x24;`, leading zeros allowed. */
const REFERENCED_DOLLAR_RE = /&#(?:0*36|[xX]0*24);/g;

/**
 * Turn every referenced dollar outside code into {@link DOLLAR_MARKER}.
 *
 * @param text - The Markdown the chat is about to parse.
 * @returns The same Markdown, each referenced dollar outside code a marker.
 */
export function protectReferencedDollars(text: string): string {
  if (!text.includes('&#')) return text;
  return text
    .split(CODE_SPAN_RE)
    .map((part, index) =>
      index % 2 === 1 ? part : part.replace(REFERENCED_DOLLAR_RE, DOLLAR_MARKER)
    )
    .join('');
}

interface HastLike {
  type: string;
  value?: string;
  properties?: Record<string, unknown> | null;
  children?: HastLike[];
}

/** Classes marking a formula the math step produced (`rehypeMathInText`). */
const MATH_CLASSES = new Set(['math-inline', 'math-display']);
/**
 * The marker in an attribute: a URL the chat autolinks runs to the next space,
 * so it can hold one, which the URL normaliser has percent-encoded by then.
 */
const MARKER_IN_ATTRIBUTE_RE = new RegExp(
  `${DOLLAR_MARKER}|${encodeURIComponent(DOLLAR_MARKER)}`,
  'gi'
);

function classesOf(node: HastLike): string[] {
  const className = node.properties?.className;
  return Array.isArray(className) ? className.map(String) : [];
}

function restore(node: HastLike, inMath: boolean): void {
  if (node.type === 'text' && node.value?.includes(DOLLAR_MARKER)) {
    node.value = node.value.replaceAll(DOLLAR_MARKER, inMath ? '\\$' : '$');
  }
  const properties = node.properties;
  if (properties) {
    for (const [key, value] of Object.entries(properties)) {
      if (typeof value === 'string') {
        properties[key] = value.replace(MARKER_IN_ATTRIBUTE_RE, '$');
      }
    }
  }
  const math = inMath || classesOf(node).some(name => MATH_CLASSES.has(name));
  for (const child of node.children ?? []) restore(child, math);
}

/**
 * Write every {@link DOLLAR_MARKER} back — runs after the math step, before
 * KaTeX renders the formulas it marked.
 */
export default function rehypeRestoreDollars() {
  return (tree: HastLike): void => restore(tree, false);
}
