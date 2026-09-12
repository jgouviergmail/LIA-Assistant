/**
 * The Markdown a bookmark exports to (ADR-282).
 *
 * The chat's own path (`ShareResponseMenu`): the answer flattened by
 * `messageToPlainText` when it is a `lia-response` HTML document, verbatim
 * when it is markdown — and, above it, what the chat cannot know about a
 * bookmark: the request that produced the answer, as a quotation, and the
 * answer's date. Pure: the download itself goes through `downloadMarkdown`.
 */

import { messageToPlainText } from '@/lib/message-clipboard';
import type { Bookmark } from '@/types/bookmarks';

/** The translated words the export needs; resolved by the caller. */
export interface BookmarkExportLabels {
  /** « Request » — the heading over the quotation. */
  request: string;
  /** « Answer » — the heading over the answer. */
  answer: string;
  /** « Kept from LIA — answered on {date} », already interpolated. */
  kept: string;
}

/** Two-digit zero-pad for the filename date components. */
function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/**
 * The text of the `.md` file.
 *
 * @param bookmark - The kept answer.
 * @param labels - Its headings, in the reader's language.
 * @returns Markdown: a dated line, the request quoted, the answer.
 */
export function bookmarkToMarkdown(bookmark: Bookmark, labels: BookmarkExportLabels): string {
  const lines: string[] = [`> ${labels.kept}`, ''];
  if (bookmark.request_content) {
    lines.push(`## ${labels.request}`, '');
    // Every line of the request is quoted: a request spanning paragraphs
    // must not have its second paragraph read as part of the answer.
    for (const line of bookmark.request_content.split(/\r?\n/)) {
      lines.push(line ? `> ${line}` : '>');
    }
    lines.push('');
  }
  lines.push(`## ${labels.answer}`, '', messageToPlainText(bookmark.content).trimEnd(), '');
  return lines.join('\n');
}

/**
 * `lia-bookmark-YYYY-MM-DD-HH-mm`, stamped from the answer's instant in the
 * reader's local clock — the same convention as the chat's export.
 *
 * @param bookmark - The kept answer.
 * @returns The filename without its extension.
 */
export function bookmarkExportBaseName(bookmark: Bookmark): string {
  const at = new Date(bookmark.answered_at);
  const date = `${at.getFullYear()}-${pad2(at.getMonth() + 1)}-${pad2(at.getDate())}`;
  return `lia-bookmark-${date}-${pad2(at.getHours())}-${pad2(at.getMinutes())}`;
}
