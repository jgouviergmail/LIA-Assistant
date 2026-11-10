'use client';

/**
 * PdfViewer — a PDF read in the page, every page of it (ADR-369, lot 14).
 *
 * It works where a browser's own viewer does not: the page's policy admits no frame of a PDF, and
 * a WebView has no viewer at all. Pages are drawn as they come near the screen and given back
 * when they leave, so a long document costs what is on screen. The words lie above the picture,
 * for a reader to select and a screen reader to read. The reader chooses the size; nothing else
 * here acts, and a link in the file is not followed: its download stays beside it.
 */
import { Minus, Plus } from '@/lib/icons';
import { useEffect, useRef, useState } from 'react';

import './pdf-text-layer.css';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { isLockedPdf, openPdf, type PdfDocument } from '@/lib/workbench/pdf-document';

export interface PdfViewerProps {
  lng: Language;
  data: Blob;
  /** The document's name: what the region is called. */
  name: string;
  /** Its height. */
  className?: string;
}

interface PageProps {
  lng: Language;
  pdf: PdfDocument;
  number: number;
  width: number;
  root: HTMLElement | null;
}

/** The sizes a reader steps through; a document opens at the width of the screen. */
const ZOOMS = [0.5, 0.75, 1, 1.5, 2, 3] as const;
const OPENING_STEP = ZOOMS.indexOf(1);
/** How far beyond the screen a page counts as near. */
const NEAR = '100% 0px';
/** A sheet's shape, until a page says its own. */
const SHEET_RATIO = Math.SQRT2;

function PdfPage({ lng, pdf, number, width, root }: PageProps) {
  const { t } = useTranslation(lng);
  const sheet = useRef<HTMLDivElement>(null);
  const picture = useRef<HTMLCanvasElement>(null);
  const words = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const [ratio, setRatio] = useState(SHEET_RATIO);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!sheet.current) return;
    const watcher = new IntersectionObserver(
      entries => setNear(entries.some(entry => entry.isIntersecting)),
      { root, rootMargin: NEAR }
    );
    watcher.observe(sheet.current);
    return () => watcher.disconnect();
  }, [root]);

  useEffect(() => {
    if (!near || width === 0 || !picture.current || !words.current) return;
    const drawing = pdf.draw(number, { canvas: picture.current, words: words.current }, width);
    drawing.done.then(
      drawn => {
        if (drawn !== null) setRatio(drawn);
      },
      () => setFailed(true)
    );
    return () => drawing.stop();
  }, [near, width, pdf, number]);

  return (
    <div
      ref={sheet}
      role="group"
      aria-label={t('workbench.files.pdf_page', { number })}
      className="relative mx-auto bg-white shadow-sm"
      style={{ width, height: Math.round(width * ratio) }}
    >
      <canvas ref={picture} aria-hidden="true" className="block h-full w-full" />
      <div ref={words} className="textLayer" />
      {failed && (
        <p className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-black">
          {t('workbench.files.page_failed')}
        </p>
      )}
    </div>
  );
}

export function PdfViewer({ lng, data, name, className }: PdfViewerProps) {
  const { t } = useTranslation(lng);
  const [opened, setOpened] = useState<{
    data: Blob;
    pdf: PdfDocument | null;
    locked: boolean;
  } | null>(null);
  const [step, setStep] = useState(OPENING_STEP);
  const [space, setSpace] = useState(0);
  const [pages, setPages] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    let current = true;
    let held: PdfDocument | null = null;
    openPdf(data).then(
      pdf => {
        if (!current) {
          pdf.close();
          return;
        }
        held = pdf;
        setOpened({ data, pdf, locked: false });
      },
      (error: unknown) => {
        if (current) setOpened({ data, pdf: null, locked: isLockedPdf(error) });
      }
    );
    return () => {
      current = false;
      held?.close();
    };
  }, [data]);

  useEffect(() => {
    if (!pages) return;
    const measure = new ResizeObserver(([entry]) => {
      if (entry) setSpace(Math.floor(entry.contentRect.width));
    });
    measure.observe(pages);
    return () => measure.disconnect();
  }, [pages]);

  if (opened?.data !== data) return <Skeleton className={className} />;
  if (!opened.pdf) {
    const reason = opened.locked ? 'workbench.files.pdf_locked' : 'workbench.files.reading_failed';
    return <p className="text-sm">{t(reason)}</p>;
  }
  const { pdf } = opened;
  const zoom = ZOOMS[step] ?? 1;
  return (
    <div className="min-w-0 space-y-1">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{t('workbench.files.pdf_pages', { count: pdf.pages })}</span>
        <span className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('workbench.files.zoom_out')}
            aria-disabled={step === 0 || undefined}
            onClick={() => setStep(current => Math.max(current - 1, 0))}
          >
            <Minus className="h-4 w-4" aria-hidden="true" />
          </Button>
          <span className="w-10 text-center tabular-nums">{`${Math.round(zoom * 100)} %`}</span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('workbench.files.zoom_in')}
            aria-disabled={step === ZOOMS.length - 1 || undefined}
            onClick={() => setStep(current => Math.min(current + 1, ZOOMS.length - 1))}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </Button>
        </span>
      </div>
      <div
        ref={setPages}
        tabIndex={0}
        role="region"
        aria-label={name}
        className={cn('space-y-3 overflow-auto rounded-md border bg-muted/40 p-2', className)}
      >
        {Array.from({ length: pdf.pages }, (_, index) => (
          <PdfPage
            key={index}
            lng={lng}
            pdf={pdf}
            number={index + 1}
            width={Math.floor(space * zoom)}
            root={pages}
          />
        ))}
      </div>
    </div>
  );
}
