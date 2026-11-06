'use client';

/**
 * WordViewer — a Word file as its author laid it out (ADR-369, lot 14).
 *
 * `wordHtml` lays it out and `AuthoredHtmlFrame` shows it: nothing of the file reaches the page.
 * A file the library cannot read says so, and its download stays beside it.
 */
import { useEffect, useState } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { wordHtml } from '@/lib/workbench/word-html';

import { AuthoredHtmlFrame } from '../AuthoredHtmlFrame';

export interface WordViewerProps {
  lng: Language;
  data: Blob;
  /** The document's name: what the frame is called. */
  name: string;
  /** Its height. */
  className?: string;
}

export function WordViewer({ lng, data, name, className }: WordViewerProps) {
  const { t } = useTranslation(lng);
  const [laidOut, setLaidOut] = useState<{ data: Blob; html: string | null } | null>(null);

  useEffect(() => {
    let current = true;
    wordHtml(data).then(
      html => {
        if (current) setLaidOut({ data, html });
      },
      () => {
        if (current) setLaidOut({ data, html: null });
      }
    );
    return () => {
      current = false;
    };
  }, [data]);

  if (laidOut?.data !== data) return <Skeleton className={className} />;
  if (laidOut.html === null)
    return <p className="text-sm">{t('workbench.files.reading_failed')}</p>;
  return <AuthoredHtmlFrame lng={lng} html={laidOut.html} title={name} className={className} />;
}
