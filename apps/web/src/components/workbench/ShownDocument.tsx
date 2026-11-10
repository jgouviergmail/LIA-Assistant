'use client';

/**
 * ShownDocument — what the API answered of a document, in its viewer (ADR-369, lot 14).
 *
 * An image is drawn, a PDF and a Word file have a viewer each, loaded when one is first shown, a
 * Markdown is laid out, a text is its words, tables come a sheet at a time; `large` lets it take a
 * window. Every part that scrolls is reachable by the keyboard, and a reading that stops before
 * the end says so. `ShownReading` adds what comes before: the wait, a refusal, the second try.
 *
 * DOM text in every viewer shares the application selection engine, including enlarged dialogs.
 * Opaque frames and canvas-only pages remain outside DOM selection.
 */
import dynamic from 'next/dynamic';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import type { ShownRead } from '@/hooks/useShownDocument';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { Shown, ShownSheet } from '@/lib/workbench/shown';

const LOADING_CLASS = 'h-40 w-full';

function ViewerLoading() {
  return <Skeleton className={LOADING_CLASS} />;
}

const PdfViewer = dynamic(() => import('./viewers/PdfViewer').then(module => module.PdfViewer), {
  ssr: false,
  loading: ViewerLoading,
});
const WordViewer = dynamic(() => import('./viewers/WordViewer').then(module => module.WordViewer), {
  ssr: false,
  loading: ViewerLoading,
});
const MarkdownViewer = dynamic(
  () => import('./viewers/MarkdownViewer').then(module => module.MarkdownViewer),
  { ssr: false, loading: ViewerLoading }
);

export interface ShownDocumentProps {
  lng: Language;
  shown: Shown;
  /** The document's name: what an image and a table are called. */
  name: string;
  /** Drawn in a window of its own rather than in a panel. */
  large?: boolean;
}

/** What grows with its content, up to a bound. */
const HEIGHT = { panel: 'max-h-96', window: 'max-h-[75dvh]' } as const;
/** What fills the height it is given: a viewer scrolls within it. */
const PAPER = { panel: 'h-96', window: 'h-[75dvh]' } as const;

function Sheet({ sheet, name, height }: { sheet: ShownSheet; name: string; height: string }) {
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={sheet.name || name}
      className={cn('overflow-auto rounded-md border', height)}
    >
      <table className="w-full border-collapse text-xs">
        <tbody>
          {sheet.rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="divide-x border-b last:border-b-0 first:sticky first:top-0 first:bg-card first:font-semibold"
            >
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="whitespace-nowrap px-2 py-1 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Sheets({
  lng,
  sheets,
  name,
  height,
}: {
  lng: Language;
  sheets: readonly ShownSheet[];
  name: string;
  height: string;
}) {
  const { t } = useTranslation(lng);
  const [picked, setPicked] = useState(0);
  const sheet = sheets[picked];
  if (!sheet) return null;
  return (
    <div className="space-y-2">
      {sheets.length > 1 && (
        <div role="group" aria-label={t('workbench.files.sheets')} className="flex flex-wrap gap-1">
          {sheets.map((each, index) => (
            <Button
              key={`${each.name}-${index}`}
              variant={index === picked ? 'secondary' : 'ghost'}
              size="sm"
              aria-pressed={index === picked}
              onClick={() => setPicked(index)}
            >
              {each.name}
            </Button>
          ))}
        </div>
      )}
      {sheet.rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('workbench.files.sheet_empty')}</p>
      ) : (
        <Sheet sheet={sheet} name={name} height={height} />
      )}
    </div>
  );
}

/** What travels as words: all three may stop before the end of the file. */
function Words({
  lng,
  shown,
  name,
  height,
}: {
  lng: Language;
  shown: Extract<Shown, { kind: 'text' | 'markdown' | 'sheets' }>;
  name: string;
  height: string;
}) {
  const { t } = useTranslation(lng);
  return (
    <figure data-selection-surface="document" className="min-w-0 space-y-1">
      {shown.kind === 'text' && (
        <>
          <pre
            tabIndex={0}
            className={cn(
              'overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/30 p-3 text-xs',
              height
            )}
          >
            {shown.text}
          </pre>
        </>
      )}
      {shown.kind === 'markdown' && (
        <>
          <MarkdownViewer text={shown.text} name={name} className={height} />
        </>
      )}
      {shown.kind === 'sheets' && (
        <Sheets lng={lng} sheets={shown.sheets} name={name} height={height} />
      )}
      {shown.cut && (
        <figcaption className="text-xs text-muted-foreground">
          {t('workbench.files.preview_cut')}
        </figcaption>
      )}
    </figure>
  );
}

export function ShownDocument({ lng, shown, name, large = false }: ShownDocumentProps) {
  const height = large ? HEIGHT.window : HEIGHT.panel;
  const paper = large ? PAPER.window : PAPER.panel;
  switch (shown.kind) {
    case 'image':
      return (
        // eslint-disable-next-line @next/next/no-img-element -- a blob of the API's own answer
        <img
          src={shown.url}
          alt={name}
          className={cn('w-full rounded-md bg-muted/30 object-contain', height)}
        />
      );
    case 'pdf':
      return <PdfViewer lng={lng} data={shown.data} name={name} className={paper} />;
    case 'word':
      return <WordViewer lng={lng} data={shown.data} name={name} className={paper} />;
    default:
      return <Words lng={lng} shown={shown} name={name} height={height} />;
  }
}

export interface ShownReadingProps extends Omit<ShownDocumentProps, 'shown'> {
  read: ShownRead;
}

/** What is known of a document so far: nothing yet, nothing to show, a failure, or the document. */
export function ShownReading({ lng, read: { state, retry }, name, large }: ShownReadingProps) {
  const { t } = useTranslation(lng);
  if (state.kind === 'loading') return <Skeleton className={LOADING_CLASS} />;
  if (state.kind === 'none') return <p className="text-sm">{t('workbench.files.reading_none')}</p>;
  if (state.kind === 'failed') {
    const refusal = state.refusal;
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm">
          {refusal ? t(refusal.key, refusal.values) : t('workbench.files.reading_failed')}
        </p>
        <Button variant="outline" size="sm" onClick={retry}>
          {t('workbench.files.retry')}
        </Button>
      </div>
    );
  }
  return <ShownDocument lng={lng} shown={state} name={name} large={large} />;
}
