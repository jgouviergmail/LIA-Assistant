'use client';

import { useEffect, useRef, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { documentTypeIcon } from '@/components/chat/document-card-icon';
import { documentPreviewUrl, fetchDocumentPreview } from '@/lib/document-preview';
import { apiImageProps } from '@/lib/utils/api-resource-url';
import type { GeneratedAsset } from '@/types/generated-assets';

const EXCERPTS = new Set(['csv', 'txt', 'md', 'docx', 'pptx', 'xlsx']);
const DEFAULT_ICON = documentTypeIcon('');
const DOCUMENT_ICONS: Record<string, LucideIcon> = Object.fromEntries(
  [...EXCERPTS, 'pdf'].map(type => [type, documentTypeIcon(type)])
);

/** Noninteractive preview: the gallery's stretched title link remains its only door. */
export function AssetDocumentPreview({ asset, label }: { asset: GeneratedAsset; label: string }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [failed, setFailed] = useState(false);
  const [text, setText] = useState<string>();
  const type = asset.original_filename.split('.').pop()?.toLowerCase() ?? '';
  const Icon = DOCUMENT_ICONS[type] ?? DEFAULT_ICON;
  const wire = documentPreviewUrl(`/api/v1/attachments/${asset.id}`);

  useEffect(() => {
    if (!box.current || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '100px' }
    );
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || !wire || !EXCERPTS.has(type)) return;
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
    let active = true;
    void fetchDocumentPreview(wire, signal)
      .then(value => {
        if (active) setText(value.text.slice(0, 4096));
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [visible, wire, type]);

  return (
    <div
      ref={box}
      className="flex h-36 w-full flex-col overflow-hidden rounded-lg border border-border bg-muted/40"
    >
      {visible && wire && type === 'pdf' && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element -- authenticated private API thumbnail.
        <img
          {...apiImageProps(wire)}
          alt={t('chat.document_card.first_page', { name: label })}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-36 w-full object-contain"
        />
      ) : text && !failed ? (
        <>
          <p className="px-3 pt-2 text-xs text-muted-foreground">
            {t('chat.document_card.excerpt')}
          </p>
          <pre className="overflow-hidden whitespace-pre-wrap break-words px-3 py-2 text-xs">
            {text}
          </pre>
        </>
      ) : (
        <div
          data-testid="generated-asset-typemark"
          className="flex flex-1 items-center justify-center"
        >
          <Icon className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
        </div>
      )}
    </div>
  );
}
