'use client';

/**
 * DocumentViewer — HTML view of a generated document (ADR-226, amendment
 * 2026-08-18: a click on a document card opens THIS page in a new tab).
 *
 * Fetches the attachment with credentials (same pattern as
 * `download-image.ts`) and renders by type:
 * - csv  → a real table (RFC 4180 parse, horizontal scroll owned by the table);
 * - md   → the sanitized markdown pipeline shared with chat;
 * - txt  → preformatted text;
 * - xlsx / docx / pptx → an honest file panel (these formats open in their
 *   native applications) with a blob download action;
 * - pdf never lands here: its card opens the inline attachment URL directly
 *   (the browser's native viewer).
 *
 * Errors report; nothing spins forever. Text decoding strips the Excel BOM.
 */

import { createElement, useCallback, useEffect, useState } from 'react';
import { Download, FileWarning } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { MarkdownContent } from '@/components/chat/MarkdownContent';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { parseCsv } from '@/lib/csv-parse';
import { fetchAttachmentBlob } from '@/lib/utils/attachment-blob';
import { formatFileSize } from '@/lib/utils/image-compress';
import { documentTypeIcon } from '@/components/chat/document-card-icon';

interface DocumentViewerProps {
  /** Attachment id — the fetch target `/api/v1/attachments/{id}`. */
  attachmentId: string;
  /** Human filename shown as the page heading and used for downloads. */
  filename: string;
  /** DocumentType value (csv, xlsx, docx, pptx, md, txt — pdf never routes here). */
  docType: string;
}

type ViewerState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'text'; text: string }
  | { kind: 'table'; rows: string[][] }
  | { kind: 'file'; blob: Blob };

const RENDERABLE_AS_TEXT = new Set(['csv', 'md', 'txt']);

/** Per-type icon — `createElement` over the STABLE lucide references from
 *  `documentTypeIcon` (no component type is created during render). */
function DocumentIcon({ docType }: { docType: string }) {
  return createElement(documentTypeIcon(docType), {
    className: 'w-8 h-8 shrink-0 text-primary',
    'aria-hidden': true,
  });
}

export function DocumentViewer({ attachmentId, filename, docType }: DocumentViewerProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<ViewerState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const blob = await fetchAttachmentBlob(attachmentId, controller.signal);
        if (!RENDERABLE_AS_TEXT.has(docType)) {
          setState({ kind: 'file', blob });
          return;
        }
        const text = (await blob.text()).replace(/^﻿/, '');
        setState(docType === 'csv' ? { kind: 'table', rows: parseCsv(text) } : { kind: 'text', text });
      } catch {
        if (!controller.signal.aborted) setState({ kind: 'error' });
      }
    })();
    return () => controller.abort();
  }, [attachmentId, docType]);

  const downloadBlob = useCallback(
    (blob: Blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
    [filename]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <DocumentIcon docType={docType} />
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight truncate">{filename}</h1>
          <p className="text-sm text-muted-foreground">{docType.toUpperCase()}</p>
        </div>
      </div>

      {state.kind === 'loading' && <LoadingSpinner />}

      {state.kind === 'error' && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          <FileWarning className="w-4 h-4 shrink-0" aria-hidden="true" />
          {t('documents.viewer.error')}
        </div>
      )}

      {state.kind === 'table' && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                {state.rows[0]?.map((header, i) => (
                  <th key={i} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {state.rows.slice(1).map((row, r) => (
                <tr key={r} className="border-b last:border-0 hover:bg-muted/30">
                  {row.map((cell, c) => (
                    <td key={c} className="px-3 py-2 align-top">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {state.kind === 'text' &&
        (docType === 'md' ? (
          <div className="rounded-lg border p-4">
            <MarkdownContent content={state.text} />
          </div>
        ) : (
          <pre className="overflow-x-auto rounded-lg border p-4 text-sm whitespace-pre-wrap">
            {state.text}
          </pre>
        ))}

      {state.kind === 'file' && (
        <div className="rounded-lg border bg-card p-6 space-y-4 max-w-md">
          <p className="text-sm text-muted-foreground">
            {t('documents.viewer.not_renderable')}
          </p>
          <p className="text-sm">{formatFileSize(state.blob.size)}</p>
          <Button onClick={() => downloadBlob(state.blob)}>
            <Download className="w-4 h-4 mr-2" aria-hidden="true" />
            {t('documents.viewer.download')}
          </Button>
        </div>
      )}
    </div>
  );
}
