'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiImageProps } from '@/lib/utils/api-resource-url';
import { documentPreviewUrl, fetchDocumentPreview } from '@/lib/document-preview';
import { parseCsv } from '@/lib/csv-parse';
import { ImageLightbox } from '@/components/ui/image-lightbox';
import { Button } from '@/components/ui/button';

type PreviewState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'text'; text: string; truncated: boolean };
const TEXT_FORMATS = new Set(['csv', 'txt', 'md', 'docx', 'pptx', 'xlsx']);

function PreviewFailure({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 p-3">
      <p className="m-0 flex-1 text-xs text-muted-foreground">
        {t('chat.document_card.preview_unavailable')}
      </p>
      <Button type="button" variant="ghost" className="min-h-11 shrink-0" onClick={onRetry}>
        {t('common.retry')}
      </Button>
    </div>
  );
}

/** Viewport-lazy small excerpts. Source content never enters markdown/widgets. */
function TextPreview({ url, docType }: { url: string; docType: string }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<PreviewState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let started = false;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      if (started) return;
      started = true;
      timer = setTimeout(() => {
        controller.abort();
        if (active) setState({ kind: 'error' });
      }, 10000);
      fetchDocumentPreview(url, controller.signal)
        .then(value => {
          if (active && !controller.signal.aborted) setState({ kind: 'text', ...value });
        })
        .catch(() => {
          if (active) setState({ kind: 'error' });
        })
        .finally(() => clearTimeout(timer));
    };
    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          observer.disconnect();
          load();
        }
      },
      { rootMargin: '100px' }
    );
    if (ref.current) observer.observe(ref.current);
    return () => {
      active = false;
      observer.disconnect();
      controller.abort();
      clearTimeout(timer);
    };
  }, [url, attempt]);
  return (
    <div ref={ref} className="lia-document-preview" aria-busy={state.kind === 'loading'}>
      <p className="m-0 px-3 py-1 text-px-11 text-muted-foreground">
        {t('chat.document_card.excerpt')}
      </p>
      {state.kind === 'loading' && <div className="min-h-20 bg-muted/30" aria-hidden="true" />}
      {state.kind === 'error' && (
        <PreviewFailure
          onRetry={() => {
            setState({ kind: 'loading' });
            setAttempt(value => value + 1);
          }}
        />
      )}
      {state.kind === 'text' && (
        <PreviewContent docType={docType} text={state.text} truncated={state.truncated} />
      )}
    </div>
  );
}

function PreviewContent({
  docType,
  text,
  truncated,
}: {
  docType: string;
  text: string;
  truncated: boolean;
}) {
  const { t } = useTranslation();
  if (docType !== 'csv' && docType !== 'xlsx')
    return (
      <pre className="m-0 p-3 text-xs whitespace-pre-wrap break-words">{text.slice(0, 4096)}</pre>
    );
  const parsed = parseCsv(text);
  // A byte budget may cut the final record: withhold it, never offer a partial fact.
  const rows = (truncated && docType === 'csv' ? parsed.slice(0, -1) : parsed).slice(0, 7);
  return (
    <div
      className="overflow-x-auto"
      tabIndex={0}
      role="region"
      aria-label={t('chat.document_card.preview')}
    >
      <table className="w-full text-xs">
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b last:border-0">
              {row.slice(0, 8).map((cell, column) =>
                index === 0 ? (
                  <th
                    key={column}
                    scope="col"
                    className="px-3 py-1 text-start font-medium bg-muted/30"
                  >
                    {cell.slice(0, 256)}
                  </th>
                ) : (
                  <td key={column} className="px-3 py-1 align-middle">
                    {cell.slice(0, 256)}
                  </td>
                )
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PdfPreview({ url, filename }: { url: string; filename: string }) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const props = apiImageProps(url);
  const alt = t('chat.document_card.first_page', { name: filename });
  return (
    <>
      <button
        type="button"
        onClick={() => (failed ? setFailed(false) : setOpen(true))}
        aria-label={failed ? t('common.retry') : alt}
        aria-haspopup={failed ? undefined : 'dialog'}
        className="lia-document-preview block w-full bg-muted/30 p-3 rounded-b-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        {failed ? (
          <span className="flex min-h-20 items-center justify-center gap-2 text-xs text-muted-foreground">
            <span>{t('chat.document_card.preview_unavailable')}</span>
            <span className="font-medium text-foreground">{t('common.retry')}</span>
          </span>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            {...props}
            loading="lazy"
            referrerPolicy="no-referrer"
            alt={alt}
            onError={() => setFailed(true)}
            className="block w-full h-48 object-contain"
          />
        )}
      </button>
      <ImageLightbox {...props} alt={alt} isOpen={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function GeneratedDocumentPreview({
  url,
  docType,
  filename,
}: {
  url: string;
  docType: string;
  filename: string;
}) {
  const wire = documentPreviewUrl(url);
  if (!wire) return null;
  if (docType === 'pdf') return <PdfPreview key={wire} url={wire} filename={filename} />;
  if (TEXT_FORMATS.has(docType)) return <TextPreview key={wire} url={wire} docType={docType} />;
  return null;
}
