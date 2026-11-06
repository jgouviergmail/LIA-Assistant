/**
 * A person's message is read as they wrote it: what looks like a tag is text.
 *
 * The chat parses raw HTML because LIA's answers are HTML, and the sanitizer
 * then drops what it does not allow. Applied to a person's bubble, that turned
 * `pas </script>, </body> et </html>` into `pas ,  et ` and `if a<b and c>d`
 * into `if ad`, while the database and the model held the words whole
 * (production, 2026-11-04). This plugin turns every `html` node of a person's
 * message into text before anything can read it as markup, and the rest of the
 * Markdown (emphasis, code, links) keeps working.
 *
 * Types are declared locally (structural subset of mdast), the idiom of
 * `rehype-math-in-text`: no `@types/mdast` devDependency for a few lines.
 */

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hChildren: MdNode[] };
}

/** Containers holding blocks: their HTML is a block, and a block needs a paragraph. */
const BLOCK_CONTAINERS: ReadonlySet<string> = new Set([
  'root',
  'blockquote',
  'listItem',
  'footnoteDefinition',
]);

function literal(node: MdNode, parent: MdNode): MdNode {
  const text: MdNode = { type: 'text', value: node.value ?? '' };
  if (!BLOCK_CONTAINERS.has(parent.type)) return text;
  // The paragraph keeps the line breaks of a pasted block on screen, and
  // `hChildren` its indentation: mdast-util-to-hast trims every line of a text
  // node it converts, and leaves these alone.
  return { type: 'paragraph', children: [text], data: { hChildren: [text] } };
}

function literalize(parent: MdNode): void {
  parent.children = parent.children?.map(child => {
    if (child.type === 'html') return literal(child, parent);
    literalize(child);
    return child;
  });
}

/** The unified plugin: every `html` node of the tree becomes text. */
export default function remarkLiteralHtml(): (tree: MdNode) => void {
  return literalize;
}
