/**
 * What a `<pre>` holds, read from the hast node react-markdown hands its
 * `pre` component.
 *
 * The block is the unit: a fence with a language, a fence without one, a
 * 4-space-indented block and a raw `<pre><code>` all produce the same
 * `pre > code` shape, and every one of them must reach CodeBlock. Routing on
 * the `code` element alone cannot tell a block from an inline chip once the
 * `language-*` class is missing, so the decision is taken one level up.
 *
 * Types are declared locally (structural subset of hast), the idiom of
 * `rehype-math-in-text`: no `@types/hast` devDependency for a few lines.
 */

interface TextNode {
  type: 'text';
  value: string;
}

interface ElementNode {
  type: 'element';
  tagName: string;
  properties?: Record<string, unknown> | null;
  children: HastNode[];
}

type HastNode = TextNode | ElementNode | { type: string; children?: HastNode[]; value?: string };

/** The language a block shows when nothing announced one. */
export const DEFAULT_CODE_LANGUAGE = 'text';

/** A block of code as CodeBlock wants it. */
export interface CodeBlockSource {
  language: string;
  text: string;
}

function isElement(n: HastNode): n is ElementNode {
  return n.type === 'element' && typeof (n as ElementNode).tagName === 'string';
}

function textOf(node: HastNode): string {
  if (node.type === 'text') return (node as TextNode).value;
  const children = (node as { children?: HastNode[] }).children;
  return children ? children.map(textOf).join('') : '';
}

function languageOf(code: ElementNode): string {
  const cn = code.properties?.className;
  const classes = Array.isArray(cn) ? cn.map(String) : typeof cn === 'string' ? cn.split(/\s+/) : [];
  const tag = classes.find(c => c.startsWith('language-'));
  const language = tag ? tag.slice('language-'.length) : '';
  return language || DEFAULT_CODE_LANGUAGE;
}

/**
 * The code block a `<pre>` node carries, or null when it holds no `<code>`
 * (a `<pre>` of plain text is left to the default renderer).
 *
 * @param node - The hast `pre` element, as react-markdown passes it.
 * @returns The language and the text, the fence's trailing newline dropped.
 */
export function codeBlockOf(node: unknown): CodeBlockSource | null {
  const pre = node as HastNode | undefined;
  if (!pre || !isElement(pre)) return null;
  const code = pre.children.find((c): c is ElementNode => isElement(c) && c.tagName === 'code');
  if (!code) return null;
  return { language: languageOf(code), text: textOf(code).replace(/\n$/, '') };
}
