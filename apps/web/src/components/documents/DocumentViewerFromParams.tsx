'use client';

/**
 * Bridges the document route to the viewer: filename and type travel as
 * search params on the card link (`?name=…&type=…`), so the viewer can
 * label the page and pick its rendering before the fetch resolves.
 * Unknown/absent params degrade to safe defaults — the fetch itself is
 * ownership-checked server-side either way.
 */

import { useSearchParams } from 'next/navigation';

import { DocumentViewer } from './DocumentViewer';

const KNOWN_TYPES = new Set(['csv', 'xlsx', 'docx', 'pptx', 'pdf', 'md', 'txt']);

export function DocumentViewerFromParams({ attachmentId }: { attachmentId: string }) {
  const searchParams = useSearchParams();
  const rawType = (searchParams.get('type') ?? '').toLowerCase();
  const docType = KNOWN_TYPES.has(rawType) ? rawType : 'txt';
  const filename = searchParams.get('name') ?? `document.${docType}`;

  return <DocumentViewer attachmentId={attachmentId} filename={filename} docType={docType} />;
}
