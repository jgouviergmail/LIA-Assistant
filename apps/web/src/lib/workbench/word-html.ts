/**
 * A Word file as HTML, through docx-preview (ADR-369, lot 14).
 *
 * The library lays the file out on nodes nothing attaches, and sanitises nothing: what it builds
 * leaves here as text, for `AuthoredHtmlFrame`, which disarms it and shows it in a sealed frame.
 * Everything travels inside that text, images as `data:` addresses. What would reach further is
 * left out: an alternative chunk (HTML the library draws in a frame of its own), and the fonts a
 * file embeds, a third party's bytes for the browser's font parser. The page follows the width it
 * is given, so a phone reads it without scrolling sideways.
 */
import type { Options } from 'docx-preview';

const WORD_OPTIONS = {
  inWrapper: false,
  ignoreWidth: true,
  ignoreHeight: true,
  ignoreFonts: true,
  breakPages: false,
  useBase64URL: true,
  renderAltChunks: false,
} satisfies Partial<Options>;

/** A sheet of paper in a frame: the file's own margins would take a phone's whole width. */
const PAPER =
  '<style>body{margin:0}' +
  'section.docx{box-sizing:border-box;max-width:56rem;margin:0 auto;' +
  'padding:clamp(1rem,5vw,3.5rem)!important}</style>';

function markupOf(node: Node): string {
  return node instanceof Element ? node.outerHTML : '';
}

/**
 * @param data - The file: somebody else's.
 * @returns Its HTML, to be shown in a sealed frame and nowhere else.
 * @throws When it is no Word file.
 */
export async function wordHtml(data: Blob): Promise<string> {
  const { parseAsync, renderDocument } = await import('docx-preview');
  const nodes: Node[] = await renderDocument(await parseAsync(data, WORD_OPTIONS), WORD_OPTIONS);
  return nodes.map(markupOf).join('') + PAPER;
}
