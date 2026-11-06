/**
 * What the API shows of a document (ADR-369, lot 14), read the same way on the mail and files
 * screens: its type says which viewer reads it. An image is a blob of an image type, a PDF and a
 * Word file are bytes for their viewers, a Markdown, a text and tables are words: a sender's
 * bytes never reach the page as anything that runs here.
 */
import apiClient, { type QueryParamValue } from '@/lib/api-client';

/** One table of a workbook or a CSV: a CSV's has no name. */
export interface ShownSheet {
  name: string;
  rows: string[][];
  /** It holds more than these rows and columns. */
  cut: boolean;
}

export type Shown =
  | { kind: 'image'; url: string }
  | { kind: 'pdf'; data: Blob }
  | { kind: 'word'; data: Blob }
  | { kind: 'markdown'; text: string; cut: boolean }
  | { kind: 'text'; text: string; cut: boolean }
  | { kind: 'sheets'; sheets: ShownSheet[]; cut: boolean };

const PDF_TYPE = 'application/pdf';
const WORD_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const MARKDOWN_TYPE = 'text/markdown';
const SHEETS_TYPE = 'application/json';

/**
 * @param path - Where it is read.
 * @param params - What names it.
 * @param signal - Stops the read when another document takes its place.
 * @returns What the API answered: an image's blob address is the caller's to revoke.
 */
export async function shownOf(
  path: string,
  params: Readonly<Record<string, QueryParamValue>>,
  signal: AbortSignal
): Promise<Shown> {
  const response = await apiClient.getResponse(path, { params: { ...params }, signal });
  const type = response.headers.get('Content-Type') ?? '';
  if (type.startsWith('image/')) {
    return { kind: 'image', url: URL.createObjectURL(await response.blob()) };
  }
  if (type.startsWith(PDF_TYPE)) return { kind: 'pdf', data: await response.blob() };
  if (type.startsWith(WORD_TYPE)) return { kind: 'word', data: await response.blob() };
  const cut = response.headers.get('X-Preview-Truncated') === 'true';
  if (type.startsWith(SHEETS_TYPE)) {
    const { sheets } = (await response.json()) as { sheets: ShownSheet[] };
    return { kind: 'sheets', sheets, cut };
  }
  const text = await response.text();
  return { kind: type.startsWith(MARKDOWN_TYPE) ? 'markdown' : 'text', text, cut };
}
