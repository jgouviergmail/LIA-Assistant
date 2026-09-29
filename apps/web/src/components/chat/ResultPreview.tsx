'use client';

import { ListFilter } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { QualifiedCollection } from '@/types/result-preview';

const prefix = 'chat.result_preview.';

function PreviewItems({ items }: { items: QualifiedCollection['items'] }) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-3">
      {items.map(item => (
        <li key={item.id} className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
          <p className="font-medium">{item.title}</p>
          <p className="text-xs text-muted-foreground">{t(prefix + item.verdict)}</p>
          <p className="whitespace-pre-wrap text-sm">{item.excerpt}</p>
        </li>
      ))}
    </ul>
  );
}

/** Display source text safely; tentative exclusions remain available by keyboard. */
export function ResultPreview({
  collections,
  hidden = false,
}: {
  collections: QualifiedCollection[];
  hidden?: boolean;
}) {
  const { t } = useTranslation();
  if (hidden || !collections.length) return null;
  return (
    <aside
      className="mb-4 ml-auto w-full max-w-2xl space-y-4 rounded-lg border bg-card/60 p-4"
      aria-label={t(prefix + 'title')}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <ListFilter aria-hidden="true" className="size-4 text-primary" />
        {t(prefix + 'title')}
      </h3>
      <p className="text-xs text-muted-foreground">{t(prefix + 'temporary')}</p>
      {collections.map(collection => (
        <section
          key={collection.kind}
          className="space-y-3"
          aria-label={t(prefix + 'kinds.' + collection.kind)}
        >
          <p className="text-xs text-muted-foreground">
            {t(prefix + 'scope', {
              kind: t(prefix + 'kinds.' + collection.kind),
              evaluated: collection.evaluated_count,
              total: collection.candidate_count,
              omitted: collection.omitted_count,
            })}
          </p>
          <PreviewItems items={collection.items.filter(item => item.verdict !== 'non_match')} />
          {collection.items.some(item => item.verdict === 'non_match') && (
            <details>
              <summary className="cursor-pointer py-2 text-sm focus-visible:outline focus-visible:outline-ring">
                {t(prefix + 'non_match')}
              </summary>
              <PreviewItems items={collection.items.filter(item => item.verdict === 'non_match')} />
            </details>
          )}
        </section>
      ))}
    </aside>
  );
}
