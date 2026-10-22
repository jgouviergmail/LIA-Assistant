import { formatPhonesInText } from '@/lib/format';

interface TextTree {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: TextTree[];
}

const LITERAL_TAGS = new Set(['code', 'pre', 'script', 'style', 'kbd', 'samp']);

function literalContent(node: TextTree) {
  if (node.tagName && LITERAL_TAGS.has(node.tagName)) return true;
  const value = node.properties?.className;
  const classes = Array.isArray(value) ? value.map(String) : String(value ?? '').split(/\s+/);
  return classes.some(name =>
    /^(?:katex(?:-|$)|math-inline$|math-display$|language-math$)/.test(name)
  );
}

function formatText(node: TextTree): void {
  if (literalContent(node)) return;
  if (node.type === 'text' && typeof node.value === 'string') {
    node.value = formatPhonesInText(node.value);
  }
  for (const child of node.children ?? []) formatText(child);
}

/** Format visible sanitized text; attributes and opaque widget data stay byte-exact. */
export default function rehypePhoneText() {
  return (tree: TextTree): void => formatText(tree);
}
