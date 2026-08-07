'use client';

/**
 * LIA's synthetic rich reply, rendered by the PRODUCTION pipeline.
 *
 * The HTML string comes from `response-html.ts` (code-owned markup + locale
 * text) and goes through the exact chat renderer — `MarkdownContent` with
 * rehypeRaw → rehypeSanitize — so the /demo reply looks precisely like a
 * real HTML-mode answer. The renderer is dynamic-imported (bundle
 * discipline: /demo must not pay for Prism/KaTeX up front).
 *
 * Honesty: the header names LIA and carries the "composed locally" chip —
 * a synthetic reply is never presented as model output.
 */

import dynamic from 'next/dynamic';
import { Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MarkdownContent = dynamic(
  () => import('@/components/chat/MarkdownContent').then((m) => m.MarkdownContent),
  {
    ssr: false,
    loading: () => (
      <div
        aria-hidden="true"
        className="h-24 animate-pulse rounded-xl bg-muted/40"
      />
    ),
  }
);

export interface ShowroomRichResponseProps {
  html: string;
}

export function ShowroomRichResponse({ html }: ShowroomRichResponseProps) {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t('showroom.response.title')}
      data-testid="showroom-rich-response"
      className="rounded-2xl border border-border/60 bg-card/70 p-4 backdrop-blur-sm"
    >
      <p className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold text-foreground">
        <Bot className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('showroom.response.title')}
        <span className="text-xs font-normal text-muted-foreground">
          {t('showroom.response.synthetic')}
        </span>
      </p>
      <MarkdownContent content={html} />
    </section>
  );
}
