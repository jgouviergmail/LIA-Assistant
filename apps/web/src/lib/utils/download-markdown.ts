/**
 * Client-side Markdown export (UX P4).
 *
 * Builds a UTF-8 markdown blob in memory and triggers a download through a
 * programmatic anchor click — the same protocol as `download-image`, minus
 * the fetch (the content is already local).
 */

import { sanitiseFilename } from './filename';

/**
 * Download `content` as a `.md` file.
 *
 * Args:
 *   content: Raw markdown text (UTF-8, accents preserved).
 *   baseName: Desired filename without extension; sanitised, with a `lia`
 *     fallback when nothing survives sanitisation.
 */
export function downloadMarkdown(content: string, baseName: string): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const blobUrl = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = `${sanitiseFilename(baseName) || 'lia'}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(blobUrl);
}
