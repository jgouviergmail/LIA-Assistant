/**
 * Restore the structured-image contract in saved v4 contact cards.
 *
 * Earlier cards emitted an unclassified <img> inside the illustration frame.
 * MarkdownImage treated it as a standalone photo and inserted a large wrapper,
 * which the 42px frame clipped. New cards declare lia-illus__image themselves;
 * this AST step repairs already-saved answers without rewriting their content.
 *
 * Runs after sanitization. It only adds one fixed class to an existing image,
 * never changes a URL/style, and never creates markup or widens the sanitizer.
 */
interface HastNode {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function classesOf(node: HastNode): string[] {
  const classes = node.properties?.className;
  if (Array.isArray(classes)) return classes.map(String);
  return typeof classes === 'string' ? classes.split(/\s+/) : [];
}

function restorePhotos(node: HastNode, inContact = false): void {
  const classes = classesOf(node);
  const contact = inContact || classes.includes('lia-contact');
  if (contact && node.tagName === 'div' && classes.includes('lia-illus')) {
    for (const child of node.children ?? []) {
      if (child.type !== 'element' || child.tagName !== 'img') continue;
      child.properties = {
        ...child.properties,
        className: ['lia-illus__image', ...classesOf(child).filter(c => c !== 'lia-illus__image')],
      };
    }
  }
  for (const child of node.children ?? []) restorePhotos(child, contact);
}

export default function rehypeContactPhotos() {
  return (tree: HastNode): void => restorePhotos(tree);
}
